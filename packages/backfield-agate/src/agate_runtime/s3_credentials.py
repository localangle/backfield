"""Flow S3 clients: static keys, or AssumeRole when a role ARN is configured."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import boto3
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session

# Not AWS_ROLE_ARN: that name selects the SDK web-identity credential provider.
S3_ROLE_ARN_ENV = "BACKFIELD_S3_ROLE_ARN"
ROLE_SESSION_NAME = "backfield-s3"


def s3_client_from_env(*, missing_credentials_message: str) -> Any:
    """S3 client for flow input, output, and batch listing.

    When ``BACKFIELD_S3_ROLE_ARN`` is set, assume that role with the long-lived
    access key and secret. A stored session token is not part of that source
    identity. Temporary credentials stay on the returned client.
    """
    access_key = _env("AWS_ACCESS_KEY_ID")
    secret_key = _env("AWS_SECRET_ACCESS_KEY")
    session_token = _env("AWS_SESSION_TOKEN")
    role_arn = _env(S3_ROLE_ARN_ENV)

    if role_arn:
        if not access_key or not secret_key:
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set "
                f"to assume {S3_ROLE_ARN_ENV}."
            )
        return _s3_client_for_assumed_role(
            access_key=access_key,
            secret_key=secret_key,
            role_arn=role_arn,
        )

    if not access_key or not secret_key:
        raise ValueError(missing_credentials_message)
    client_kwargs: dict[str, str] = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }
    if session_token:
        client_kwargs["aws_session_token"] = session_token
    return boto3.client("s3", **client_kwargs)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _assume_role_metadata(
    *,
    access_key: str,
    secret_key: str,
    role_arn: str,
) -> dict[str, str]:
    # Explicit keys only. Do not forward AWS_SESSION_TOKEN: that value is either
    # unrelated temporary credentials or empty when the role is what mints them.
    sts = boto3.client(
        "sts",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    response = sts.assume_role(RoleArn=role_arn, RoleSessionName=ROLE_SESSION_NAME)
    credentials = response["Credentials"]
    expiry = credentials["Expiration"]
    expiry_time = expiry.isoformat() if isinstance(expiry, datetime) else str(expiry)
    return {
        "access_key": str(credentials["AccessKeyId"]),
        "secret_key": str(credentials["SecretAccessKey"]),
        "token": str(credentials["SessionToken"]),
        "expiry_time": expiry_time,
    }


def _s3_client_for_assumed_role(*, access_key: str, secret_key: str, role_arn: str) -> Any:
    def refresh() -> dict[str, str]:
        return _assume_role_metadata(
            access_key=access_key,
            secret_key=secret_key,
            role_arn=role_arn,
        )

    # botocore has no public setter for a refreshable credential provider.
    session = get_session()
    session._credentials = RefreshableCredentials.create_from_metadata(
        metadata=refresh(),
        refresh_using=refresh,
        method="sts-assume-role",
    )
    return boto3.Session(botocore_session=session).client("s3")
