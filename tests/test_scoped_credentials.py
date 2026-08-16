"""Tests for namespace-scoped temporary S3 credentials."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from bridge.workspace_sync import WorkspaceSync


NAMESPACE = WorkspaceSync.namespace_for_runtime_session("web-session-" + "a" * 64)


def test_session_policy_separates_list_and_object_permissions() -> None:
    sts = MagicMock()
    sts.assume_role.return_value = {"Credentials": {
        "AccessKeyId": "a", "SecretAccessKey": "b", "SessionToken": "c",
    }}
    with patch.dict(os.environ, {"S3_BUCKET": "workspace-bucket", "EXECUTION_ROLE_ARN": "arn:aws:iam::1:role/runtime"}), \
         patch("boto3.client", return_value=sts):
        from bridge.scoped_credentials import ScopedCredentials

        credentials = ScopedCredentials(NAMESPACE)
        credentials.get()

    policy = json.loads(sts.assume_role.call_args.kwargs["Policy"])
    object_statement = next(statement for statement in policy["Statement"] if "s3:GetObject" in statement["Action"])
    list_statement = next(statement for statement in policy["Statement"] if statement["Action"] == ["s3:ListBucket"])
    assert object_statement["Resource"] == [f"arn:aws:s3:::workspace-bucket/{NAMESPACE}/*"]
    assert list_statement["Resource"] == ["arn:aws:s3:::workspace-bucket"]
    assert list_statement["Condition"]["StringLike"]["s3:prefix"] == [f"{NAMESPACE}/*"]


def test_scoped_credentials_rejects_non_opaque_namespace() -> None:
    with patch.dict(os.environ, {"S3_BUCKET": "workspace-bucket", "EXECUTION_ROLE_ARN": "arn:aws:iam::1:role/runtime"}):
        from bridge.scoped_credentials import ScopedCredentials

        with pytest.raises(ValueError):
            ScopedCredentials("../../secret")
