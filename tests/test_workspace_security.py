"""Security and restart tests for authenticated workspace persistence."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bridge.workspace_sync import (
    NamespaceBindingError,
    WorkspaceSync,
    load_skill_instructions,
)


SESSION = "web-session-" + "a" * 64
NAMESPACE = WorkspaceSync.namespace_for_runtime_session(SESSION)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / ".hermes"
    (root / "skills").mkdir(parents=True)
    return root


def _sync(workspace: Path, s3: MagicMock, *, bucket: str = "workspace-bucket") -> WorkspaceSync:
    return WorkspaceSync(
        workspace=workspace,
        bucket=bucket,
        runtime_session_id=SESSION,
        s3_client=s3,
    )


def test_namespace_is_opaque_and_bound_to_the_runtime_session() -> None:
    assert NAMESPACE.startswith("ws-")
    assert len(NAMESPACE) == 67
    assert WorkspaceSync.validate_namespace(NAMESPACE, SESSION) == NAMESPACE

    for value in ("", "user@example.com", "../secret", "/absolute", "ws-" + "b" * 63):
        with pytest.raises(NamespaceBindingError):
            WorkspaceSync.validate_namespace(value, SESSION)

    with pytest.raises(NamespaceBindingError):
        WorkspaceSync.validate_namespace(NAMESPACE, "other-session-" + "b" * 40)


def test_configured_persistence_requires_a_bound_namespace(workspace: Path) -> None:
    sync = WorkspaceSync(
        workspace=workspace,
        bucket="workspace-bucket",
        runtime_session_id=SESSION,
        s3_client=MagicMock(),
    )

    with pytest.raises(NamespaceBindingError):
        sync.restore("")


def test_unconfigured_persistence_is_explicitly_ephemeral(workspace: Path, caplog: pytest.LogCaptureFixture) -> None:
    s3 = MagicMock()
    with caplog.at_level(logging.INFO):
        sync = WorkspaceSync(workspace=workspace, bucket="", runtime_session_id=None, s3_client=s3)
        sync.restore("")
        sync.save("")

    s3.get_paginator.assert_not_called()
    assert "persistence disabled" in caplog.text.lower()


def test_restore_rejects_traversal_absolute_paths_symlinks_and_non_skill_files(workspace: Path) -> None:
    s3 = MagicMock()
    prefix = f"{NAMESPACE}/.hermes/"
    outside = workspace.parent / "outside.txt"
    outside.write_text("must stay outside", encoding="utf-8")
    s3.get_paginator.return_value.paginate.return_value = [{
        "Contents": [
            {"Key": f"{prefix}MEMORY.md"},
            {"Key": f"{prefix}../outside.txt"},
            {"Key": f"{prefix}/absolute.txt"},
            {"Key": f"{prefix}skills/demo/SKILL.md"},
            {"Key": f"{prefix}skills/demo/run.py"},
        ],
    }]
    s3.download_file.side_effect = lambda bucket, key, target: Path(target).write_text(
        "# safe skill" if key.endswith("SKILL.md") else "not safe", encoding="utf-8"
    )

    _sync(workspace, s3).restore(NAMESPACE)

    assert (workspace / "MEMORY.md").exists()
    assert (workspace / "skills" / "demo" / "SKILL.md").exists()
    assert not (workspace / "skills" / "demo" / "run.py").exists()
    assert outside.read_text(encoding="utf-8") == "must stay outside"


def test_save_skips_symlinks_and_forbidden_skill_files(workspace: Path) -> None:
    s3 = MagicMock()
    (workspace / "MEMORY.md").write_text("memory", encoding="utf-8")
    skill_dir = workspace / "skills" / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# instructions", encoding="utf-8")
    (skill_dir / "tool.py").write_text("print('no')", encoding="utf-8")
    outside = workspace.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (workspace / "link.txt").symlink_to(outside)

    _sync(workspace, s3).save(NAMESPACE)

    keys = [call.args[2] for call in s3.upload_file.call_args_list]
    assert any(key.endswith("MEMORY.md") for key in keys)
    assert any(key.endswith("skills/demo/SKILL.md") for key in keys)
    assert not any(key.endswith("tool.py") for key in keys)
    assert not any(key.endswith("link.txt") for key in keys)


def test_skill_loader_returns_only_bounded_utf8_markdown(workspace: Path) -> None:
    safe = workspace / "skills" / "safe"
    safe.mkdir()
    (safe / "SKILL.md").write_text("# Do this\nUse the tool.", encoding="utf-8")
    (safe / "helper.py").write_text("raise SystemExit", encoding="utf-8")
    bad = workspace / "skills" / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_bytes(b"\x00binary")

    instructions = load_skill_instructions(workspace)

    assert instructions == ["# Do this\nUse the tool."]


def test_restore_does_not_materialize_invalid_skill_content(workspace: Path) -> None:
    s3 = MagicMock()
    prefix = f"{NAMESPACE}/.hermes/"
    s3.get_paginator.return_value.paginate.return_value = [{
        "Contents": [
            {"Key": f"{prefix}skills/too-large/SKILL.md", "Size": 65 * 1024},
            {"Key": f"{prefix}skills/binary/SKILL.md", "Size": 7},
        ],
    }]
    s3.download_file.side_effect = lambda bucket, key, target: Path(target).write_bytes(
        b"\x00binary" if key.endswith("binary/SKILL.md") else b"# too large"
    )

    _sync(workspace, s3).restore(NAMESPACE)

    assert not (workspace / "skills" / "too-large").exists()
    assert not (workspace / "skills" / "binary").exists()


def test_restart_round_trip_restores_skill_as_instruction(workspace: Path) -> None:
    source_s3 = MagicMock()
    skill = workspace / "skills" / "restart"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Restarted skill\nRemember this rule.", encoding="utf-8")
    uploaded: dict[str, bytes] = {}

    def upload(filename: str, bucket: str, key: str) -> None:
        uploaded[key] = Path(filename).read_bytes()

    source_s3.upload_file.side_effect = upload
    _sync(workspace, source_s3).save(NAMESPACE)

    restored = workspace.parent / "new" / ".hermes"
    restored.mkdir(parents=True)
    (restored / "skills").mkdir()
    target_s3 = MagicMock()
    target_s3.get_paginator.return_value.paginate.return_value = [{
        "Contents": [{"Key": key} for key in uploaded],
    }]
    target_s3.download_file.side_effect = lambda bucket, key, target: Path(target).write_bytes(uploaded[key])
    _sync(restored, target_s3).restore(NAMESPACE)

    assert load_skill_instructions(restored) == ["# Restarted skill\nRemember this rule."]


def test_partial_s3_failures_continue_and_leave_no_temp_files(workspace: Path, caplog: pytest.LogCaptureFixture) -> None:
    s3 = MagicMock()
    (workspace / "one.txt").write_text("one", encoding="utf-8")
    (workspace / "two.txt").write_text("two", encoding="utf-8")
    s3.upload_file.side_effect = [RuntimeError("upload failed"), None]

    with caplog.at_level(logging.WARNING):
        _sync(workspace, s3).save(NAMESPACE)

    assert s3.upload_file.call_count == 2
    assert not list(workspace.rglob("*.s3tmp"))
    assert "one" not in caplog.text
    assert "two" not in caplog.text


def test_partial_restore_failure_does_not_block_other_objects(workspace: Path) -> None:
    s3 = MagicMock()
    prefix = f"{NAMESPACE}/.hermes/"
    s3.get_paginator.return_value.paginate.return_value = [{
        "Contents": [
            {"Key": f"{prefix}broken.txt"},
            {"Key": f"{prefix}survives.txt"},
        ],
    }]

    def download(bucket: str, key: str, target: str) -> None:
        if key.endswith("broken.txt"):
            raise RuntimeError("network failure")
        Path(target).write_text("survived", encoding="utf-8")

    s3.download_file.side_effect = download
    _sync(workspace, s3).restore(NAMESPACE)

    assert not (workspace / "broken.txt").exists()
    assert (workspace / "survives.txt").read_text(encoding="utf-8") == "survived"
    assert not list(workspace.rglob(".restore-*.s3tmp"))
