"""Short-lived STS credentials restricted to one opaque workspace namespace."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

import boto3

from bridge.workspace_sync import NAMESPACE_RE

logger = logging.getLogger("agentcore.credentials")


class ScopedCredentials:
    """Refresh an STS session policy that cannot cross workspace prefixes."""

    REFRESH_INTERVAL = 2700

    def __init__(self, namespace: str, *, sts_client: Any | None = None) -> None:
        if not isinstance(namespace, str) or not NAMESPACE_RE.fullmatch(namespace):
            raise ValueError("invalid workspace namespace")
        self.namespace = namespace
        self.bucket = os.environ["S3_BUCKET"]
        self.role_arn = os.environ["EXECUTION_ROLE_ARN"]
        self._sts = sts_client or boto3.client(
            "sts",
            region_name=os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
            or "us-east-1",
        )
        self._credentials: dict[str, str] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def get(self) -> dict[str, str]:
        with self._lock:
            if self._credentials is None:
                self._refresh()
            return self._credentials  # type: ignore[return-value]

    def start_refresh_loop(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self.REFRESH_INTERVAL):
                try:
                    with self._lock:
                        self._refresh()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Credential refresh failed (%s)", type(exc).__name__)

        threading.Thread(target=loop, daemon=True, name="credential-refresh").start()
        logger.info("Scoped credential refresh loop started")

    def stop(self) -> None:
        self._stop.set()

    def _refresh(self) -> None:
        prefix = f"{self.namespace}/*"
        session_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "WorkspaceObjectsOnly",
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    "Resource": [f"arn:aws:s3:::{self.bucket}/{prefix}"],
                },
                {
                    "Sid": "WorkspacePrefixListingOnly",
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{self.bucket}"],
                    "Condition": {"StringLike": {"s3:prefix": [prefix]}},
                },
            ],
        }
        response = self._sts.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName=f"hermes-{self.namespace[3:19]}",
            Policy=json.dumps(session_policy),
            DurationSeconds=3600,
        )
        credentials = response["Credentials"]
        self._credentials = {
            "aws_access_key_id": credentials["AccessKeyId"],
            "aws_secret_access_key": credentials["SecretAccessKey"],
            "aws_session_token": credentials["SessionToken"],
        }
