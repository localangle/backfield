"""Org-admin async full stylebook export/import (ZIP bundles on S3-compatible storage)."""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3
from backfield_auth.gate import require_org_admin
from backfield_db import BackfieldProject, Stylebook, StylebookBundleJob
from backfield_stylebook.full_bundle import DEFAULT_MAX_ZIP_BYTES, read_manifest_from_zip
from celery import Celery
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1/organizations", tags=["stylebook-bundles"])


def _require_org_scope(auth: dict[str, Any], org_id: int) -> None:
    if auth["type"] == "service":
        return
    if int(auth["organization_id"]) != org_id:
        raise HTTPException(status_code=403, detail="Wrong organization")


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth["type"] != "session":
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


def _stylebook_bundle_bucket() -> str:
    bucket = os.environ.get("STYLEBOOK_BUNDLE_S3_BUCKET", "").strip()
    if not bucket:
        raise HTTPException(
            status_code=503,
            detail="Stylebook bundle transfers are not configured. Set STYLEBOOK_BUNDLE_S3_BUCKET.",
        )
    return bucket


def _bundle_key_prefix() -> str:
    return os.environ.get("STYLEBOOK_BUNDLE_S3_PREFIX", "stylebook-bundles").strip().strip("/")


def _bundle_object_key(org_id: int, job_id: str) -> str:
    prefix = _bundle_key_prefix()
    return f"{prefix}/{org_id}/{job_id}.zip" if prefix else f"{org_id}/{job_id}.zip"


def _s3_client_bundles() -> Any:
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_access_key or not aws_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Object storage credentials are not configured for bundle links.",
        )
    session_kwargs: dict[str, str] = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
    }
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token
    endpoint = os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")
    if endpoint:
        return boto3.client("s3", endpoint_url=endpoint, **session_kwargs)
    return boto3.client("s3", **session_kwargs)


celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def _celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


class BundleJobOut(BaseModel):
    id: str
    organization_id: int
    kind: str
    status: str
    source_stylebook_id: int | None
    result_stylebook_id: int | None
    s3_bucket: str | None
    s3_key: str | None
    download_url: str | None = None
    upload_url: str | None = None
    progress_json: dict[str, Any] | list[Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(
        cls,
        row: StylebookBundleJob,
        *,
        download_url: str | None = None,
        upload_url: str | None = None,
    ) -> BundleJobOut:
        prog = row.progress_json
        if prog is not None and not isinstance(prog, (dict, list)):
            prog = None
        return cls(
            id=str(row.id),
            organization_id=int(row.organization_id),
            kind=str(row.kind),
            status=str(row.status),
            source_stylebook_id=int(row.source_stylebook_id) if row.source_stylebook_id else None,
            result_stylebook_id=int(row.result_stylebook_id) if row.result_stylebook_id else None,
            s3_bucket=row.s3_bucket,
            s3_key=row.s3_key,
            download_url=download_url,
            upload_url=upload_url,
            progress_json=prog,  # type: ignore[arg-type]
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _presigned_get_url(*, bucket: str, key: str) -> str:
    client = _s3_client_bundles()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,
    )


def _presigned_put_url(*, bucket: str, key: str) -> str:
    client = _s3_client_bundles()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": "application/zip",
        },
        ExpiresIn=3600,
    )


@router.post(
    "/{org_id}/stylebooks/{stylebook_id}/bundle-export-jobs",
    response_model=BundleJobOut,
)
def create_bundle_export_job(
    org_id: int,
    stylebook_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> BundleJobOut:
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    bucket = _stylebook_bundle_bucket()
    job_id = str(uuid.uuid4())
    key = _bundle_object_key(org_id, job_id)
    job = StylebookBundleJob(
        id=job_id,
        organization_id=org_id,
        kind="export",
        status="queued",
        created_by_user_id=_created_by_user_id(auth),
        source_stylebook_id=stylebook_id,
        s3_bucket=bucket,
        s3_key=key,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    celery_app.send_task(
        "worker.tasks.export_stylebook_bundle",
        args=[job_id],
        queue=_celery_queue(),
    )
    return BundleJobOut.from_row(job)


class StylebookBundleImportCreate(BaseModel):
    new_stylebook_name: str = Field(min_length=1)
    project_mappings: dict[str, int] = Field(default_factory=dict)


@router.post("/{org_id}/stylebook-bundle-import-jobs", response_model=BundleJobOut)
def create_bundle_import_job(
    org_id: int,
    body: StylebookBundleImportCreate,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> BundleJobOut:
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    for _slug, pid in body.project_mappings.items():
        p = session.get(BackfieldProject, int(pid))
        if p is None or int(p.organization_id) != org_id:
            raise HTTPException(status_code=400, detail="Invalid project in project mappings.")

    bucket = _stylebook_bundle_bucket()
    job_id = str(uuid.uuid4())
    key = _bundle_object_key(org_id, job_id)
    job = StylebookBundleJob(
        id=job_id,
        organization_id=org_id,
        kind="import",
        status="awaiting_upload",
        created_by_user_id=_created_by_user_id(auth),
        source_stylebook_id=None,
        s3_bucket=bucket,
        s3_key=key,
        import_request_json={
            "new_stylebook_name": body.new_stylebook_name.strip(),
            "project_mappings": {str(k): int(v) for k, v in body.project_mappings.items()},
        },
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    upload_url = _presigned_put_url(bucket=bucket, key=key)
    return BundleJobOut.from_row(job, upload_url=upload_url)


@router.post("/{org_id}/stylebook-bundle-jobs/{job_id}/upload", response_model=BundleJobOut)
async def upload_bundle_zip_for_import(
    org_id: int,
    job_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
    bundle: UploadFile = File(...),
) -> BundleJobOut:
    """Stream the ZIP to the staging bucket via the API (avoids browser CORS on direct S3 PUT)."""
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    job = session.get(StylebookBundleJob, job_id)
    if job is None or int(job.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind != "import":
        raise HTTPException(status_code=400, detail="Not an import job.")
    if job.status != "awaiting_upload":
        raise HTTPException(status_code=400, detail="This job is not waiting for an upload.")
    bucket = job.s3_bucket
    key = job.s3_key
    if not bucket or not key:
        raise HTTPException(status_code=500, detail="Job is missing staging object location.")

    buf = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    total = 0
    try:
        while chunk := await bundle.read(1024 * 1024):
            total += len(chunk)
            if total > DEFAULT_MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="File is too large.")
            buf.write(chunk)
        buf.seek(0)
        client = _s3_client_bundles()
        client.upload_fileobj(
            buf,
            bucket,
            key,
            ExtraArgs={"ContentType": "application/zip"},
        )
    finally:
        buf.close()

    job.updated_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    session.refresh(job)
    return BundleJobOut.from_row(job)


@router.post("/{org_id}/stylebook-bundle-jobs/{job_id}/finalize", response_model=BundleJobOut)
def finalize_bundle_import_job(
    org_id: int,
    job_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> BundleJobOut:
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    job = session.get(StylebookBundleJob, job_id)
    if job is None or int(job.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind != "import":
        raise HTTPException(status_code=400, detail="Not an import job.")
    if job.status != "awaiting_upload":
        raise HTTPException(status_code=400, detail="This job is not waiting for an upload.")
    job.status = "queued"
    job.updated_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    celery_app.send_task(
        "worker.tasks.import_stylebook_bundle",
        args=[job_id],
        queue=_celery_queue(),
    )
    return BundleJobOut.from_row(job)


@router.get("/{org_id}/stylebook-bundle-jobs/{job_id}", response_model=BundleJobOut)
def get_bundle_job(
    org_id: int,
    job_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> BundleJobOut:
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    job = session.get(StylebookBundleJob, job_id)
    if job is None or int(job.organization_id) != org_id:
        raise HTTPException(status_code=404, detail="Job not found")
    dl: str | None = None
    ul: str | None = None
    if job.kind == "export" and job.status == "succeeded" and job.s3_bucket and job.s3_key:
        dl = _presigned_get_url(bucket=job.s3_bucket, key=job.s3_key)
    if job.kind == "import" and job.status == "awaiting_upload" and job.s3_bucket and job.s3_key:
        ul = _presigned_put_url(bucket=job.s3_bucket, key=job.s3_key)
    return BundleJobOut.from_row(job, download_url=dl, upload_url=ul)


class ManifestPreviewOut(BaseModel):
    schema_version: int | None
    source_stylebook: dict[str, Any] | None = None
    project_slices: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/{org_id}/stylebook-bundles/manifest-preview", response_model=ManifestPreviewOut)
async def preview_bundle_manifest(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
    bundle: UploadFile = File(...),
) -> ManifestPreviewOut:
    """Read ``manifest.json`` from an uploaded ZIP (does not start an import job)."""
    require_org_admin(session, auth, org_id)
    _require_org_scope(auth, org_id)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp_path = tf.name
            total = 0
            while chunk := await bundle.read(1024 * 1024):
                total += len(chunk)
                if total > DEFAULT_MAX_ZIP_BYTES:
                    raise HTTPException(status_code=413, detail="File is too large.")
                tf.write(chunk)
        assert tmp_path is not None
        try:
            man = read_manifest_from_zip(tmp_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        slices = man.get("project_slices")
        if not isinstance(slices, list):
            slices = []
        src = man.get("source_stylebook")
        if src is not None and not isinstance(src, dict):
            src = None
        ver = man.get("schema_version")
        return ManifestPreviewOut(
            schema_version=int(ver) if isinstance(ver, int) else None,
            source_stylebook=src,
            project_slices=[s for s in slices if isinstance(s, dict)],
        )
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)
