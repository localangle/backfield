"""Flow S3 client: direct keys, or AssumeRole when a role ARN is set."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from agate_runtime.s3_credentials import ROLE_SESSION_NAME, s3_client_from_env

_MISSING = "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set."


def _clear_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "BACKFIELD_S3_ROLE_ARN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_direct_keys_skip_assume_role(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "tok")
    monkeypatch.setenv("BACKFIELD_S3_ROLE_ARN", "  ")

    fake_s3 = MagicMock()
    with patch("agate_runtime.s3_credentials.boto3.client", return_value=fake_s3) as client:
        result = s3_client_from_env(missing_credentials_message=_MISSING)

    assert result is fake_s3
    client.assert_called_once_with(
        "s3",
        aws_access_key_id="ak",
        aws_secret_access_key="sk",
        aws_session_token="tok",
    )


def test_role_arn_assumes_with_long_lived_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "stored-token")
    role_arn = "arn:aws:iam::123456789012:role/example-input-access"
    monkeypatch.setenv("BACKFIELD_S3_ROLE_ARN", role_arn)

    expiry = datetime(2099, 1, 1, tzinfo=UTC)
    fake_sts = MagicMock()
    fake_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIATEMP",
            "SecretAccessKey": "temp-secret",
            "SessionToken": "temp-token",
            "Expiration": expiry,
        }
    }
    fake_s3 = MagicMock()

    def client_side(service: str, **kwargs: str) -> MagicMock:
        assert service == "sts"
        assert kwargs["aws_access_key_id"] == "ak"
        assert kwargs["aws_secret_access_key"] == "sk"
        assert "aws_session_token" not in kwargs
        return fake_sts

    session_cls = MagicMock()
    session_cls.return_value.client.return_value = fake_s3
    with (
        patch("agate_runtime.s3_credentials.boto3.client", side_effect=client_side),
        patch("agate_runtime.s3_credentials.boto3.Session", session_cls),
    ):
        result = s3_client_from_env(missing_credentials_message=_MISSING)
        botocore_session = session_cls.call_args.kwargs["botocore_session"]
        credentials = botocore_session.get_credentials()
        assert credentials is not None
        frozen = credentials.get_frozen_credentials()
        assert frozen.access_key == "ASIATEMP"
        assert frozen.token == "temp-token"

    assert result is fake_s3
    fake_sts.assume_role.assert_called_once_with(
        RoleArn=role_arn,
        RoleSessionName=ROLE_SESSION_NAME,
    )


def test_role_arn_without_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("BACKFIELD_S3_ROLE_ARN", "arn:aws:iam::1:role/example")

    with pytest.raises(ValueError, match="BACKFIELD_S3_ROLE_ARN"):
        s3_client_from_env(missing_credentials_message=_MISSING)


def test_missing_keys_use_caller_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)

    with pytest.raises(ValueError, match="for S3Input"):
        s3_client_from_env(missing_credentials_message="keys required for S3Input")
