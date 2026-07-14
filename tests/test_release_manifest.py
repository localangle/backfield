from __future__ import annotations

import hashlib
import importlib.util
import json
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
canonical_version = release_manifest.canonical_version
package_directory = release_manifest.package_directory
sha256_file = release_manifest.sha256_file
validate_release_version = release_manifest.validate_release_version
scan_image_id = release_manifest._scan_image_id
publish_manifest = release_manifest.publish_manifest


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
