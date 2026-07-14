#!/usr/bin/env python3
"""Publish and alias complete Backfield artifact manifests.

The manifest is uploaded last and is the atomic "ready to deploy" marker.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
import tarfile
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

REPOSITORIES = (
    "backfield-agate-api",
    "backfield-core-api",
    "backfield-stylebook-api",
    "backfield-worker",
)
SEMVER_RE = re.compile(r"^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")


def canonical_version(sha: str) -> str:
    value = sha.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{12,40}", value):
        raise ValueError("git SHA must be 12–40 lowercase hexadecimal characters")
    return f"main-{value[:12]}-amd64"


def validate_release_version(version: str) -> str:
    if not SEMVER_RE.fullmatch(version):
        raise ValueError(f"release tag must be SemVer vX.Y.Z, got {version!r}")
    return version


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _not_found(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code", "")) in {
        "404",
        "NoSuchKey",
        "NotFound",
    }


def _publish_ui_archive(
    s3: Any,
    *,
    bucket: str,
    key: str,
    archive: Path,
    checksum: str,
    source_sha: str,
) -> None:
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if not _not_found(exc):
            raise
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=archive.read_bytes(),
                ContentType="application/gzip",
                Metadata={"sha256": checksum, "source-sha": source_sha},
                IfNoneMatch="*",
            )
        except ClientError as put_exc:
            if put_exc.response.get("Error", {}).get("Code") != "PreconditionFailed":
                raise
        head = s3.head_object(Bucket=bucket, Key=key)
    if int(head["ContentLength"]) != archive.stat().st_size:
        raise RuntimeError(f"immutable UI size conflict for s3://{bucket}/{key}")
    if head.get("Metadata", {}).get("sha256") != checksum:
        raise RuntimeError(f"immutable UI checksum conflict for s3://{bucket}/{key}")
    if head.get("Metadata", {}).get("source-sha") != source_sha:
        raise RuntimeError(f"immutable UI source conflict for s3://{bucket}/{key}")


def package_directory(source: Path, output: Path) -> None:
    """Create a deterministic gzip-compressed tar archive."""
    if not source.is_dir():
        raise ValueError(f"UI build directory not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for path in sorted(source.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(source)
                    info = archive.gettarinfo(str(path), arcname=relative.as_posix())
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def _image_detail(ecr: Any, repository: str, tag: str) -> dict[str, Any]:
    response = ecr.describe_images(
        repositoryName=repository,
        imageIds=[{"imageTag": tag}],
    )
    details = response.get("imageDetails") or []
    if not details:
        raise RuntimeError(f"missing ECR image {repository}:{tag}")
    return dict(details[0])


def _scan_image_id(ecr: Any, repository: str, tag: str) -> dict[str, str]:
    """Resolve an OCI index tag to its scan-enabled Linux/AMD64 child."""
    response = ecr.batch_get_image(
        repositoryName=repository,
        imageIds=[{"imageTag": tag}],
    )
    images = response.get("images") or []
    if not images:
        raise RuntimeError(f"cannot resolve image manifest for {repository}:{tag}")
    manifest = json.loads(images[0]["imageManifest"])
    children = manifest.get("manifests")
    if not children:
        return {"imageTag": tag}
    for child in children:
        platform = child.get("platform") or {}
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            return {"imageDigest": str(child["digest"])}
    raise RuntimeError(f"OCI index has no Linux/AMD64 image: {repository}:{tag}")


def _wait_for_scan(ecr: Any, repository: str, tag: str) -> dict[str, int]:
    image_id = _scan_image_id(ecr, repository, tag)
    for _ in range(60):
        try:
            response = ecr.describe_image_scan_findings(
                repositoryName=repository,
                imageId=image_id,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ScanNotFoundException":
                raise
            time.sleep(10)
            continue
        status = response.get("imageScanStatus", {}).get("status")
        if status == "COMPLETE":
            counts = response.get("imageScanFindings", {}).get(
                "findingSeverityCounts", {}
            )
            return {str(key): int(value) for key, value in counts.items()}
        if status in {"FAILED", "UNSUPPORTED_IMAGE"}:
            raise RuntimeError(
                f"ECR scan {status} for {repository}:{tag} ({image_id})"
            )
        time.sleep(10)
    raise RuntimeError(f"ECR scan timed out for {repository}:{tag} ({image_id})")


def build_manifest(
    *,
    version: str,
    source_sha: str,
    build_time: str,
    artifact_bucket: str,
    ui_archives: dict[str, Path],
    ecr: Any,
    s3: Any,
    enforce_scans: bool = True,
) -> dict[str, Any]:
    if version != canonical_version(source_sha):
        raise ValueError(f"version {version!r} does not match source SHA {source_sha}")

    images: dict[str, Any] = {}
    critical: list[str] = []
    for repository in REPOSITORIES:
        detail = _image_detail(ecr, repository, version)
        repo = ecr.describe_repositories(repositoryNames=[repository])["repositories"][0]
        scans = _wait_for_scan(ecr, repository, version) if enforce_scans else {}
        if scans.get("CRITICAL", 0):
            critical.append(f"{repository}: {scans['CRITICAL']} CRITICAL")
        images[repository] = {
            "tag": version,
            "digest": detail["imageDigest"],
            "uri": f"{repo['repositoryUri']}:{version}",
            "scan_findings": scans,
        }
    if critical:
        raise RuntimeError("critical ECR findings block publication: " + ", ".join(critical))

    ui: dict[str, Any] = {}
    for name, archive in ui_archives.items():
        checksum = sha256_file(archive)
        key = f"versions/{version}/ui/{name}.tar.gz"
        _publish_ui_archive(
            s3,
            bucket=artifact_bucket,
            key=key,
            archive=archive,
            checksum=checksum,
            source_sha=source_sha,
        )
        ui[name] = {
            "object_key": key,
            "sha256": checksum,
            "size": archive.stat().st_size,
        }

    return {
        "schema_version": 1,
        "version": version,
        "source_version": None,
        "source_sha": source_sha,
        "build_time": build_time,
        "architecture": "linux/amd64",
        "images": images,
        "ui": ui,
    }


def publish_manifest(s3: Any, bucket: str, manifest: dict[str, Any]) -> str:
    key = f"manifests/{manifest['version']}.json"
    body = json.dumps(manifest, indent=2, sort_keys=True).encode()
    try:
        existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        if not _not_found(exc):
            raise
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                Metadata={
                    "source-sha": str(manifest["source_sha"]),
                    "schema-version": str(manifest["schema_version"]),
                },
                IfNoneMatch="*",
            )
            return key
        except ClientError as put_exc:
            if put_exc.response.get("Error", {}).get("Code") != "PreconditionFailed":
                raise
            existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    if existing != body:
        raise RuntimeError(f"immutable manifest conflict for s3://{bucket}/{key}")
    return key


def load_manifest(s3: Any, bucket: str, version: str) -> dict[str, Any]:
    response = s3.get_object(Bucket=bucket, Key=f"manifests/{version}.json")
    value = json.loads(response["Body"].read())
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def alias_ecr_image(ecr: Any, repository: str, source_tag: str, alias_tag: str) -> str:
    source = ecr.batch_get_image(
        repositoryName=repository,
        imageIds=[{"imageTag": source_tag}],
    )
    images = source.get("images") or []
    if not images:
        raise RuntimeError(f"canonical ECR image missing: {repository}:{source_tag}")
    image = images[0]
    source_digest = str(image["imageId"]["imageDigest"])

    try:
        existing = _image_detail(ecr, repository, alias_tag)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ImageNotFoundException":
            raise
    except RuntimeError:
        existing = None
    else:
        existing_digest = str(existing["imageDigest"])
        if existing_digest != source_digest:
            raise RuntimeError(
                f"immutable alias conflict {repository}:{alias_tag}: "
                f"{existing_digest} != {source_digest}"
            )
        return source_digest

    put_args = {
        "repositoryName": repository,
        "imageManifest": image["imageManifest"],
        "imageTag": alias_tag,
    }
    if image.get("imageManifestMediaType"):
        put_args["imageManifestMediaType"] = image["imageManifestMediaType"]
    try:
        response = ecr.put_image(**put_args)
    except ClientError as exc:
        # A concurrent retry may have won; verify rather than blindly fail.
        if exc.response.get("Error", {}).get("Code") != "ImageTagAlreadyExistsException":
            raise
        existing = _image_detail(ecr, repository, alias_tag)
        if str(existing["imageDigest"]) != source_digest:
            raise RuntimeError(f"immutable alias conflict {repository}:{alias_tag}") from exc
        return source_digest
    return str(response["image"]["imageId"]["imageDigest"])


def create_release_alias(
    *,
    source_manifest: dict[str, Any],
    release_version: str,
    ecr: Any,
) -> dict[str, Any]:
    validate_release_version(release_version)
    source_version = str(source_manifest["version"])
    alias = copy.deepcopy(source_manifest)
    alias["version"] = release_version
    alias["source_version"] = source_version
    for repository, image in alias["images"].items():
        digest = alias_ecr_image(ecr, repository, source_version, release_version)
        if digest != image["digest"]:
            raise RuntimeError(f"digest mismatch while aliasing {repository}")
        image["tag"] = release_version
        image["uri"] = image["uri"].rsplit(":", 1)[0] + f":{release_version}"
    return alias


def _write_summary(manifest: dict[str, Any], manifest_key: str) -> None:
    print(f"VERSION={manifest['version']}")
    print(f"SOURCE_SHA={manifest['source_sha']}")
    print(f"MANIFEST={manifest_key}")
    for repository, image in manifest["images"].items():
        scans = image.get("scan_findings") or {}
        print(
            f"IMAGE {repository} {image['digest']} "
            f"HIGH={scans.get('HIGH', 0)} CRITICAL={scans.get('CRITICAL', 0)}"
        )
    for name, ui in manifest["ui"].items():
        print(f"UI {name} sha256={ui['sha256']} size={ui['size']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    version_cmd = sub.add_parser("version")
    version_cmd.add_argument("--sha", required=True)

    package_cmd = sub.add_parser("package-ui")
    package_cmd.add_argument("--source", type=Path, required=True)
    package_cmd.add_argument("--output", type=Path, required=True)

    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("--version", required=True)
    publish_cmd.add_argument("--source-sha", required=True)
    publish_cmd.add_argument("--build-time", required=True)
    publish_cmd.add_argument("--bucket", required=True)
    publish_cmd.add_argument("--agate-ui", type=Path, required=True)
    publish_cmd.add_argument("--stylebook-ui", type=Path, required=True)
    publish_cmd.add_argument("--skip-scan-gate", action="store_true")

    alias_cmd = sub.add_parser("alias")
    alias_cmd.add_argument("--source-version", required=True)
    alias_cmd.add_argument("--release-version", required=True)
    alias_cmd.add_argument("--source-sha", required=True)
    alias_cmd.add_argument("--bucket", required=True)

    args = parser.parse_args()
    if args.command == "version":
        print(canonical_version(args.sha))
        return 0
    if args.command == "package-ui":
        package_directory(args.source, args.output)
        print(f"{args.output} sha256={sha256_file(args.output)}")
        return 0

    ecr = boto3.client("ecr")
    s3 = boto3.client("s3")
    if args.command == "publish":
        manifest = build_manifest(
            version=args.version,
            source_sha=args.source_sha,
            build_time=args.build_time,
            artifact_bucket=args.bucket,
            ui_archives={
                "agate-ui": args.agate_ui,
                "stylebook-ui": args.stylebook_ui,
            },
            ecr=ecr,
            s3=s3,
            enforce_scans=not args.skip_scan_gate,
        )
    else:
        validate_release_version(args.release_version)
        expected = canonical_version(args.source_sha)
        if args.source_version != expected:
            raise ValueError(f"source version must be {expected}")
        source = load_manifest(s3, args.bucket, args.source_version)
        if source.get("source_sha") != args.source_sha:
            raise ValueError("canonical manifest source SHA does not match release tag commit")
        manifest = create_release_alias(
            source_manifest=source,
            release_version=args.release_version,
            ecr=ecr,
        )
    key = publish_manifest(s3, args.bucket, manifest)
    _write_summary(manifest, key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
