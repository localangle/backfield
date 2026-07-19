from __future__ import annotations

import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

_SCRIPT = Path(__file__).parents[1] / "scripts" / "release_manifest.py"
_SPEC = importlib.util.spec_from_file_location("release_manifest", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
release_manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_manifest)

alias_ecr_image = release_manifest.alias_ecr_image
build_manifest = release_manifest.build_manifest
canonical_version = release_manifest.canonical_version
create_release_alias = release_manifest.create_release_alias
package_directory = release_manifest.package_directory
sha256_file = release_manifest.sha256_file
validate_manifest_inventory = release_manifest.validate_manifest_inventory
validate_release_version = release_manifest.validate_release_version
scan_image_id = release_manifest._scan_image_id
publish_manifest = release_manifest.publish_manifest
CURRENT_SCHEMA_VERSION = release_manifest.CURRENT_SCHEMA_VERSION
REPOSITORIES = release_manifest.REPOSITORIES
UI_NAMES_V1 = release_manifest.UI_NAMES_V1
UI_NAMES_V2 = release_manifest.UI_NAMES_V2


def test_canonical_version() -> None:
    assert canonical_version("a" * 40) == f"main-{'a' * 12}-amd64"
    with pytest.raises(ValueError, match="git SHA"):
        canonical_version("not-a-sha")


def test_release_version_validation() -> None:
    assert validate_release_version("v1.2.3") == "v1.2.3"
    with pytest.raises(ValueError, match="SemVer"):
        validate_release_version("release-1")
    with pytest.raises(ValueError, match="SemVer"):
        validate_release_version("v01.2.3")


def test_ui_archive_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "dist"
    source.mkdir()
    (source / "index.html").write_text("<h1>hello</h1>")
    assets = source / "assets"
    assets.mkdir()
    (assets / "app.abc.js").write_text("console.log('ok')")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    package_directory(source, first)
    package_directory(source, second)

    assert sha256_file(first) == sha256_file(second)
    assert hashlib.sha256(first.read_bytes()).hexdigest() == sha256_file(first)

    with tarfile.open(first, mode="r:gz") as archive:
        names = set(archive.getnames())
    assert "index.html" in names
    assert "LICENSE.md" in names


class FakeIndexEcr:
    def batch_get_image(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "images": [
                {
                    "imageManifest": json.dumps(
                        {
                            "manifests": [
                                {
                                    "digest": "sha256:attestation",
                                    "platform": {"os": "unknown", "architecture": "unknown"},
                                },
                                {
                                    "digest": "sha256:amd64",
                                    "platform": {"os": "linux", "architecture": "amd64"},
                                },
                            ]
                        }
                    )
                }
            ]
        }


def test_scan_resolves_linux_amd64_child_from_oci_index() -> None:
    assert scan_image_id(FakeIndexEcr(), "backfield-worker", "main-abc-amd64") == {
        "imageDigest": "sha256:amd64"
    }


class FakeBody:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value


class FakeManifestS3:
    def __init__(self, existing: bytes | None) -> None:
        self.existing = existing
        self.put_calls: list[dict[str, Any]] = []

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.existing is None:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": FakeBody(self.existing)}

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)
        self.existing = kwargs["Body"]


def _minimal_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "version": "main-0123456789ab-amd64",
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
    }


def test_manifest_publish_is_idempotent_and_conditional() -> None:
    value = _minimal_manifest()
    encoded = json.dumps(value, indent=2, sort_keys=True).encode()
    existing = FakeManifestS3(encoded)
    assert publish_manifest(existing, "artifacts", value).endswith(".json")
    assert existing.put_calls == []

    missing = FakeManifestS3(None)
    publish_manifest(missing, "artifacts", value)
    assert missing.put_calls[0]["IfNoneMatch"] == "*"


def test_manifest_publish_rejects_immutable_conflict() -> None:
    with pytest.raises(RuntimeError, match="immutable manifest conflict"):
        publish_manifest(FakeManifestS3(b"{}"), "artifacts", _minimal_manifest())


class FakeEcr:
    def __init__(self, *, alias_digest: str | None = None) -> None:
        self.alias_digest = alias_digest
        self.put_calls: list[dict[str, Any]] = []

    def batch_get_image(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "images": [
                {
                    "imageId": {"imageDigest": "sha256:canonical"},
                    "imageManifest": '{"schemaVersion":2}',
                    "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json",
                }
            ]
        }

    def describe_images(self, **kwargs: Any) -> dict[str, Any]:
        if self.alias_digest is None:
            return {"imageDetails": []}
        return {"imageDetails": [{"imageDigest": self.alias_digest}]}

    def put_image(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        return {"image": {"imageId": {"imageDigest": "sha256:canonical"}}}


def test_release_alias_puts_existing_manifest_without_rebuild() -> None:
    ecr = FakeEcr()
    digest = alias_ecr_image(ecr, "backfield-worker", "main-abc-amd64", "v1.2.3")
    assert digest == "sha256:canonical"
    assert ecr.put_calls[0]["imageTag"] == "v1.2.3"


def test_release_alias_is_idempotent() -> None:
    ecr = FakeEcr(alias_digest="sha256:canonical")
    digest = alias_ecr_image(ecr, "backfield-worker", "main-abc-amd64", "v1.2.3")
    assert digest == "sha256:canonical"
    assert ecr.put_calls == []


def test_release_alias_conflict_fails() -> None:
    ecr = FakeEcr(alias_digest="sha256:other")
    with pytest.raises(RuntimeError, match="immutable alias conflict"):
        alias_ecr_image(ecr, "backfield-worker", "main-abc-amd64", "v1.2.3")


def _ui_record(name: str, version: str = "main-0123456789ab-amd64") -> dict[str, Any]:
    return {
        "object_key": f"versions/{version}/ui/{name}.tar.gz",
        "sha256": "a" * 64,
        "size": 12,
    }


def _image_record(tag: str = "main-0123456789ab-amd64") -> dict[str, Any]:
    return {
        "tag": tag,
        "digest": "sha256:canonical",
        "uri": f"123.dkr.ecr.us-east-1.amazonaws.com/backfield-worker:{tag}",
        "scan_findings": {},
    }


def _complete_manifest(*, schema_version: int) -> dict[str, Any]:
    ui_names = UI_NAMES_V2 if schema_version == CURRENT_SCHEMA_VERSION else UI_NAMES_V1
    return {
        "schema_version": schema_version,
        "version": "main-0123456789ab-amd64",
        "source_version": None,
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "build_time": "2026-01-01T00:00:00Z",
        "architecture": "linux/amd64",
        "images": {name: _image_record() for name in REPOSITORIES},
        "ui": {name: _ui_record(name) for name in ui_names},
    }


def test_validate_manifest_inventory_accepts_schema_v1_and_v2() -> None:
    validate_manifest_inventory(_complete_manifest(schema_version=1))
    validate_manifest_inventory(_complete_manifest(schema_version=CURRENT_SCHEMA_VERSION))


def test_validate_manifest_inventory_rejects_incomplete_schema_v2() -> None:
    incomplete = _complete_manifest(schema_version=CURRENT_SCHEMA_VERSION)
    del incomplete["ui"]["api-playground"]
    with pytest.raises(ValueError, match="missing=\\['api-playground'\\]"):
        validate_manifest_inventory(incomplete)


def test_validate_manifest_inventory_rejects_unknown_schema() -> None:
    with pytest.raises(ValueError, match="unsupported manifest schema_version"):
        validate_manifest_inventory({"schema_version": 99, "images": {}, "ui": {}})


class FakePublishEcr:
    def describe_images(self, **kwargs: Any) -> dict[str, Any]:
        return {"imageDetails": [{"imageDigest": "sha256:canonical"}]}

    def describe_repositories(self, **kwargs: Any) -> dict[str, Any]:
        name = kwargs["repositoryNames"][0]
        return {
            "repositories": [
                {"repositoryUri": f"123.dkr.ecr.us-east-1.amazonaws.com/{name}"}
            ]
        }


class FakePublishS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return self.objects[key]["head"]

    def put_object(self, **kwargs: Any) -> None:
        body = kwargs["Body"]
        self.objects[kwargs["Key"]] = {
            "body": body,
            "head": {
                "ContentLength": len(body),
                "Metadata": kwargs.get("Metadata", {}),
            },
        }


def test_build_manifest_requires_api_playground_and_emits_schema_v2(tmp_path: Path) -> None:
    archives = {
        "agate-ui": tmp_path / "agate-ui.tar.gz",
        "stylebook-ui": tmp_path / "stylebook-ui.tar.gz",
        "api-playground": tmp_path / "api-playground.tar.gz",
    }
    for path in archives.values():
        path.write_bytes(b"archive")

    source_sha = "0123456789abcdef0123456789abcdef01234567"
    version = canonical_version(source_sha)
    s3 = FakePublishS3()
    manifest = build_manifest(
        version=version,
        source_sha=source_sha,
        build_time="2026-01-01T00:00:00Z",
        artifact_bucket="artifacts",
        ui_archives=archives,
        ecr=FakePublishEcr(),
        s3=s3,
        enforce_scans=False,
    )

    assert manifest["schema_version"] == CURRENT_SCHEMA_VERSION
    assert set(manifest["ui"]) == set(UI_NAMES_V2)
    playground = manifest["ui"]["api-playground"]
    assert playground["object_key"] == f"versions/{version}/ui/api-playground.tar.gz"
    assert playground["sha256"] == sha256_file(archives["api-playground"])
    assert playground["size"] == archives["api-playground"].stat().st_size
    assert f"versions/{version}/ui/api-playground.tar.gz" in s3.objects

    with pytest.raises(ValueError, match="missing=\\['api-playground'\\]"):
        build_manifest(
            version=version,
            source_sha=source_sha,
            build_time="2026-01-01T00:00:00Z",
            artifact_bucket="artifacts",
            ui_archives={
                "agate-ui": archives["agate-ui"],
                "stylebook-ui": archives["stylebook-ui"],
            },
            ecr=FakePublishEcr(),
            s3=FakePublishS3(),
            enforce_scans=False,
        )


def test_release_alias_preserves_ui_object_keys_for_schema_v1_and_v2() -> None:
    for schema_version in (1, CURRENT_SCHEMA_VERSION):
        source = _complete_manifest(schema_version=schema_version)
        alias = create_release_alias(
            source_manifest=source,
            release_version="v1.2.3",
            ecr=FakeEcr(),
        )
        assert alias["version"] == "v1.2.3"
        assert alias["source_version"] == source["version"]
        assert alias["ui"] == source["ui"]
        assert alias["schema_version"] == schema_version


def test_release_alias_rejects_incomplete_source_manifest() -> None:
    incomplete = _complete_manifest(schema_version=CURRENT_SCHEMA_VERSION)
    del incomplete["ui"]["api-playground"]
    with pytest.raises(ValueError, match="missing=\\['api-playground'\\]"):
        create_release_alias(
            source_manifest=incomplete,
            release_version="v1.2.3",
            ecr=FakeEcr(),
        )
