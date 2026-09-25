"""Tests for interfaces/api/snapshot_sync.py, using a fake S3 client (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interfaces.api import snapshot_sync


class _FakePaginator:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return [{"Contents": [{"Key": key} for key in self._keys if key.startswith(Prefix)]}]


class _FakeS3:
    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = objects
        self.downloaded: list[str] = []

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "list_objects_v2"
        return _FakePaginator(list(self.objects))

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self.downloaded.append(key)
        Path(filename).write_text(self.objects[key])


_OBJECTS = {
    "snapshots/current.json": '{"snapshot_id": "sha256:new"}',
    "snapshots/history/sha256-old.json": '{"snapshot_id": "sha256:old"}',
    "snapshots/history/sha256-new.json": '{"snapshot_id": "sha256:new"}',
}


def test_downloads_history_first_and_current_last(tmp_path: Path) -> None:
    s3 = _FakeS3(dict(_OBJECTS))

    count = snapshot_sync.sync_once("bucket", "snapshots/", tmp_path, client=s3)

    assert count == 3
    assert s3.downloaded[-1] == "snapshots/current.json"
    assert (tmp_path / "history" / "sha256-old.json").exists()
    assert (tmp_path / "current.json").read_text() == '{"snapshot_id": "sha256:new"}'
    assert not list(tmp_path.rglob("*.part"))


def test_history_is_immutable_but_current_is_refreshed(tmp_path: Path) -> None:
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "sha256-old.json").write_text("LOCAL-KEEP")
    (tmp_path / "current.json").write_text("stale")
    s3 = _FakeS3(dict(_OBJECTS))

    snapshot_sync.sync_once("bucket", "snapshots/", tmp_path, client=s3)

    assert (tmp_path / "history" / "sha256-old.json").read_text() == "LOCAL-KEEP"
    assert "snapshots/history/sha256-old.json" not in s3.downloaded
    assert (tmp_path / "current.json").read_text() == '{"snapshot_id": "sha256:new"}'


def test_key_escaping_the_store_is_refused(tmp_path: Path) -> None:
    s3 = _FakeS3({"snapshots/../evil.json": "x"})
    with pytest.raises(ValueError, match="outside the snapshot store"):
        snapshot_sync.sync_once("bucket", "snapshots/", tmp_path / "store", client=s3)
    assert not (tmp_path / "evil.json").exists()


def test_disabled_without_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNAPSHOT_S3_BUCKET", raising=False)
    assert snapshot_sync.configure_from_env() is False


def test_failed_first_sync_is_recorded_not_raised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SNAPSHOT_S3_BUCKET", "bucket")
    monkeypatch.setenv("SNAPSHOT_STORE_PATH", str(tmp_path))

    def boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("no credentials")

    class _NoThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def start(self) -> None: ...

    monkeypatch.setattr(snapshot_sync, "sync_once", boom)
    monkeypatch.setattr("interfaces.api.snapshot_sync.threading.Thread", _NoThread)

    assert snapshot_sync.configure_from_env() is True
    status = snapshot_sync.sync_status()
    assert status["enabled"] is True
    assert "no credentials" in status["last_error"]
