"""Safe S3 persistence for an authenticated AgentCore workspace.

The workspace is disposable session state. S3 is only a durable copy rooted
at an opaque namespace bound to the AgentCore runtime session. Persisted
skills are inert Markdown instructions; no skill file is imported or run.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import tempfile
import threading
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import boto3

logger = logging.getLogger("agentcore.workspace_sync")

SKIP_PATTERNS = [
    "__pycache__/*", "*.pyc", "*.pyo", "*.log", "*.tmp", "*.bak",
    "*.s3tmp", "*.sock", "node_modules/*", ".git/*", "*.db-journal",
    "*.db-wal", "*.db-shm",
]
NAMESPACE_RE = re.compile(r"^ws-[a-f0-9]{64}$")
RUNTIME_SESSION_RE = re.compile(r"^[A-Za-z0-9:_-]{33,256}$")
SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_SKILL_BYTES = 64 * 1024


class NamespaceBindingError(ValueError):
    """Namespace is missing, malformed, or bound to another session."""


class WorkspaceFilesystemError(ValueError):
    """A workspace path is unsafe or outside the approved root."""


def _valid_session(session: str) -> bool:
    return bool(
        isinstance(session, str)
        and RUNTIME_SESSION_RE.fullmatch(session)
        and ".." not in session
    )


def _namespace_for_session(session: str) -> str:
    if not _valid_session(session):
        raise NamespaceBindingError("invalid runtime session")
    return "ws-" + hashlib.sha256(session.encode("utf-8")).hexdigest()


def _validate_namespace(namespace: str, session: str) -> str:
    if not isinstance(namespace, str) or not NAMESPACE_RE.fullmatch(namespace):
        raise NamespaceBindingError("invalid workspace namespace")
    if namespace != _namespace_for_session(session):
        raise NamespaceBindingError("workspace namespace is not bound to this session")
    return namespace


def validate_workspace_namespace(namespace: str, runtime_session_id: str) -> str:
    """Validate the backend-issued namespace against AgentCore's session ID."""
    return _validate_namespace(namespace, runtime_session_id)


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise WorkspaceFilesystemError("invalid workspace path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WorkspaceFilesystemError("invalid workspace path")
    return path


def _is_skill(path: PurePosixPath) -> bool:
    return bool(path.parts and path.parts[0] == "skills")


def _is_approved_skill(path: PurePosixPath) -> bool:
    return (
        len(path.parts) == 3
        and path.parts[0] == "skills"
        and SKILL_NAME_RE.fullmatch(path.parts[1]) is not None
        and ".." not in path.parts[1]
        and path.parts[2] == "SKILL.md"
    )


def _read_markdown(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SKILL_BYTES:
            return None
        raw = path.read_bytes()
        if len(raw) > MAX_SKILL_BYTES or b"\x00" in raw:
            return None
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    if not text.strip() or any(
        (ord(char) < 9 or 13 < ord(char) < 32) and char not in "\n\r\t"
        for char in text
    ):
        return None
    return text


def load_skill_instructions(workspace: str | Path) -> list[str]:
    """Return only bounded, UTF-8 Markdown from approved skill paths."""
    try:
        raw_root = Path(workspace)
        if raw_root.is_symlink():
            return []
        root = raw_root.resolve(strict=False)
        skills = root / "skills"
        if skills.is_symlink() or not skills.is_dir():
            return []
        instructions: list[str] = []
        for directory in sorted(skills.iterdir(), key=lambda item: item.name):
            if (
                directory.is_symlink()
                or not directory.is_dir()
                or not SKILL_NAME_RE.fullmatch(directory.name)
                or ".." in directory.name
            ):
                continue
            text = _read_markdown(directory / "SKILL.md")
            if text is not None:
                instructions.append(text)
        return instructions
    except OSError:
        return []


class WorkspaceSync:
    """Restore/save safe workspace files under one authenticated S3 prefix."""

    def __init__(
        self,
        *,
        workspace: str | Path | None = None,
        bucket: str | None = None,
        runtime_session_id: str | None = None,
        sync_interval: int | None = None,
        s3_client: Any | None = None,
        s3_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        raw_workspace = workspace or os.environ.get("WORKSPACE_PATH", "/mnt/workspace/.hermes")
        self.workspace = self._prepare_workspace(Path(raw_workspace))
        self.bucket = bucket if bucket is not None else os.environ.get("S3_BUCKET", "").strip()
        self.runtime_session_id = runtime_session_id
        raw_interval = sync_interval if sync_interval is not None else int(os.environ.get("WORKSPACE_SYNC_INTERVAL", "300"))
        self.sync_interval = max(1, raw_interval)
        self._s3 = s3_client
        self._s3_client_factory = s3_client_factory
        if self._s3 is None and self._s3_client_factory is None and self.bucket:
            self._s3 = boto3.client(
                "s3",
                region_name=os.environ.get("AWS_DEFAULT_REGION")
                or os.environ.get("AWS_REGION")
                or "us-east-1",
            )
        self._stop = threading.Event()
        self._save_lock = threading.Lock()
        if not self.bucket:
            logger.info("Workspace persistence disabled; using ephemeral filesystem")

    @staticmethod
    def _prepare_workspace(workspace: Path) -> Path:
        try:
            if workspace.exists() and workspace.is_symlink():
                raise WorkspaceFilesystemError("workspace root is a symlink")
            workspace.mkdir(parents=True, exist_ok=True)
            root = workspace.resolve(strict=True)
            if not root.is_dir():
                raise WorkspaceFilesystemError("workspace root is not a directory")
            return root
        except OSError as exc:
            raise WorkspaceFilesystemError("workspace root is unavailable") from exc

    @staticmethod
    def namespace_for_runtime_session(runtime_session_id: str) -> str:
        return _namespace_for_session(runtime_session_id)

    @staticmethod
    def validate_namespace(namespace: str, runtime_session_id: str) -> str:
        return validate_workspace_namespace(namespace, runtime_session_id)

    def _validated_namespace(self, namespace: str) -> str:
        if not self.bucket:
            return namespace
        if not self.runtime_session_id:
            raise NamespaceBindingError("runtime session is required for persistence")
        return self.validate_namespace(namespace, self.runtime_session_id)

    def _client(self) -> Any:
        if self._s3_client_factory is not None:
            return self._s3_client_factory()
        if self._s3 is None:
            self._s3 = boto3.client(
                "s3",
                region_name=os.environ.get("AWS_DEFAULT_REGION")
                or os.environ.get("AWS_REGION")
                or "us-east-1",
            )
        return self._s3

    @staticmethod
    def _prefix(namespace: str) -> str:
        return f"{namespace}/.hermes/"

    def _local_path(self, relative: str) -> Path:
        safe = _safe_relative(relative)
        if _is_skill(safe) and not _is_approved_skill(safe):
            raise WorkspaceFilesystemError("unapproved skill path")
        candidate = self.workspace.joinpath(*safe.parts)
        current = self.workspace
        for part in candidate.relative_to(self.workspace).parts:
            current /= part
            if current.is_symlink():
                raise WorkspaceFilesystemError("workspace symlink is not allowed")
        try:
            candidate.resolve(strict=False).relative_to(self.workspace)
        except ValueError as exc:
            raise WorkspaceFilesystemError("workspace path escaped root") from exc
        return candidate

    @staticmethod
    def _should_skip(relative: str) -> bool:
        return any(fnmatch(relative, pattern) or fnmatch(relative, f"*/{pattern}") for pattern in SKIP_PATTERNS)

    def _should_sync(self, relative: str) -> bool:
        try:
            safe = _safe_relative(relative)
        except WorkspaceFilesystemError:
            return False
        return not self._should_skip(relative) and (not _is_skill(safe) or _is_approved_skill(safe))

    # Restore -----------------------------------------------------------

    def restore(self, namespace: str) -> None:
        if not self.bucket:
            return
        namespace = self._validated_namespace(namespace)
        prefix = self._prefix(namespace)
        count = 0
        try:
            pages = self._client().get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
            for page in pages:
                for item in page.get("Contents", []):
                    key = item.get("Key", "")
                    if not isinstance(key, str) or not key.startswith(prefix):
                        continue
                    relative = key[len(prefix):]
                    if not relative or not self._should_sync(relative):
                        continue
                    try:
                        if item.get("Size", 0) > MAX_SKILL_BYTES and _is_approved_skill(_safe_relative(relative)):
                            continue
                    except WorkspaceFilesystemError:
                        continue
                    destination = self.workspace
                    try:
                        destination = self._local_path(relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        self._download_atomically(
                            key,
                            destination,
                            validate_skill=_is_approved_skill(_safe_relative(relative)),
                        )
                        count += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Workspace restore item failed (%s)", type(exc).__name__)
                        current = destination.parent
                        while current != self.workspace:
                            try:
                                current.rmdir()
                            except OSError:
                                break
                            current = current.parent
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workspace restore failed (%s)", type(exc).__name__)
            return
        for database in self.workspace.rglob("*.db"):
            if not database.is_symlink() and database.is_file():
                self._verify_sqlite(database)
        logger.info("Workspace restore complete (%d files)", count)

    def _download_atomically(self, key: str, destination: Path, *, validate_skill: bool = False) -> None:
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".restore-", suffix=".s3tmp", delete=False) as handle:
                temporary = handle.name
            self._client().download_file(self.bucket, key, temporary)
            if validate_skill and _read_markdown(Path(temporary)) is None:
                raise WorkspaceFilesystemError("persisted skill is not valid Markdown")
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    # Save --------------------------------------------------------------

    def save(self, namespace: str) -> None:
        if not self.bucket:
            return
        namespace = self._validated_namespace(namespace)
        prefix = self._prefix(namespace)
        with self._save_lock:
            count = 0
            for database in sorted(self.workspace.rglob("*.db")):
                if database.is_symlink() or not database.is_file():
                    continue
                relative = database.relative_to(self.workspace).as_posix()
                if not self._should_sync(relative):
                    continue
                temporary: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(dir=database.parent, prefix=".backup-", suffix=".s3tmp", delete=False) as handle:
                        temporary = handle.name
                    self._sqlite_backup(database, Path(temporary))
                    self._client().upload_file(temporary, self.bucket, f"{prefix}{relative}")
                    count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Workspace database upload failed (%s)", type(exc).__name__)
                finally:
                    if temporary:
                        Path(temporary).unlink(missing_ok=True)
            for path in sorted(self.workspace.rglob("*")):
                if path.is_dir() or path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(self.workspace).as_posix()
                if path.suffix == ".db" or not self._should_sync(relative):
                    continue
                if _is_approved_skill(_safe_relative(relative)) and _read_markdown(path) is None:
                    continue
                try:
                    self._client().upload_file(str(path), self.bucket, f"{prefix}{relative}")
                    count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Workspace file upload failed (%s)", type(exc).__name__)
            logger.info("Workspace save complete (%d files)", count)

    def save_immediate(self, namespace: str) -> None:
        def run() -> None:
            try:
                self.save(namespace)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Workspace background save failed (%s)", type(exc).__name__)
        threading.Thread(target=run, daemon=True, name="workspace-save").start()

    def start_periodic_save(self, namespace: str) -> None:
        if not self.bucket:
            return
        self._validated_namespace(namespace)

        def loop() -> None:
            while not self._stop.wait(self.sync_interval):
                try:
                    self.save(namespace)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Workspace periodic save failed (%s)", type(exc).__name__)
        threading.Thread(target=loop, daemon=True, name="workspace-sync").start()
        logger.info("Periodic workspace sync started (interval=%ds)", self.sync_interval)

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _sqlite_backup(src: Path, dst: Path) -> None:
        source = sqlite3.connect(str(src))
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    @staticmethod
    def _verify_sqlite(path: Path) -> None:
        try:
            with sqlite3.connect(str(path)) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            path.unlink(missing_ok=True)
