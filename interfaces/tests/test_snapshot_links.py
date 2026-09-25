"""Tests for interfaces/api/snapshot_links.py, using a fake S3 client (no network, no AWS)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.api import snapshot_links

_ID_OLD = "sha256:" + "a" * 64
_ID_NEW = "sha256:" + "b" * 64
_TOKEN = "s3cret-token"


class _FakePaginator:
    def __init__(self, objects: list[dict[str, Any]]) -> None:
        self._objects = objects

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        return [{"Contents": [o for o in self._objects if o["Key"].startswith(Prefix)]}]


class _FakeS3:
    def __init__(self, objects: list[dict[str, Any]]) -> None:
        self.objects = objects
        self.signed: list[dict[str, Any]] = []

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == "list_objects_v2"
        return _FakePaginator(self.objects)

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if not any(o["Key"] == Key for o in self.objects):
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {}

    def generate_presigned_url(self, op: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self.signed.append({"op": op, "params": Params, "expires": ExpiresIn})
        return f"https://signed.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


def _obj(key: str, day: int, size: int = 100) -> dict[str, Any]:
    return {"Key": key, "Size": size, "LastModified": datetime(2026, 9, day, tzinfo=UTC)}


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> _FakeS3:
    fake = _FakeS3(
        [
            _obj("snapshots/current.json", 25),
            _obj(f"snapshots/history/{_ID_OLD}.json", 24),
            _obj(f"snapshots/history/{_ID_NEW}.json", 25),
            _obj("snapshots/history/not-a-snapshot.txt", 26),
            _obj("snapshots/history/sha256:short.json", 26),
        ]
    )
    monkeypatch.setattr(snapshot_links, "_client", lambda: fake)
    monkeypatch.setenv("SNAPSHOT_S3_BUCKET", "bucket")
    monkeypatch.setenv("SNAPSHOT_LINKS_TOKEN", _TOKEN)
    monkeypatch.delenv("SNAPSHOT_URL_EXPIRY_SECONDS", raising=False)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    snapshot_links.register_snapshot_link_routes(app)
    return TestClient(app)


_AUTH = {"X-Suraksha-Token": _TOKEN}


def test_refuses_without_storage_or_token_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, s3: _FakeS3
) -> None:
    monkeypatch.delenv("SNAPSHOT_LINKS_TOKEN")
    assert client.get("/snapshots", headers=_AUTH).status_code == 403  # secure by default

    monkeypatch.delenv("SNAPSHOT_S3_BUCKET")
    assert client.get("/snapshots", headers=_AUTH).status_code == 503


def test_rejects_missing_or_wrong_token(client: TestClient, s3: _FakeS3) -> None:
    assert client.get("/snapshots").status_code == 401
    assert client.get("/snapshots", headers={"X-Suraksha-Token": "nope"}).status_code == 401
    assert client.get(f"/snapshots/{_ID_NEW}/download-url").status_code == 401
    assert s3.signed == []


def test_lists_only_real_snapshots_newest_first(client: TestClient, s3: _FakeS3) -> None:
    body = client.get("/snapshots", headers=_AUTH).json()

    assert [item["snapshot_id"] for item in body["snapshots"]] == [_ID_NEW, _ID_OLD]
    assert body["snapshots"][0]["size_bytes"] == 100


def test_signs_a_history_snapshot_and_current(client: TestClient, s3: _FakeS3) -> None:
    body = client.get(f"/snapshots/{_ID_NEW}/download-url", headers=_AUTH).json()
    assert body["expires_in_seconds"] == snapshot_links.DEFAULT_EXPIRY_SECONDS
    assert body["url"].startswith(f"https://signed.example/snapshots/history/{_ID_NEW}.json")
    assert s3.signed[0]["params"]["ResponseContentType"] == "application/json"

    current = client.get("/snapshots/current/download-url", headers=_AUTH).json()
    assert "snapshots/current.json" in current["url"]


@pytest.mark.parametrize(("configured", "expected"), [("10", 30), ("99999", 3600), ("120", 120)])
def test_expiry_is_clamped(
    client: TestClient,
    s3: _FakeS3,
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
    expected: int,
) -> None:
    monkeypatch.setenv("SNAPSHOT_URL_EXPIRY_SECONDS", configured)
    body = client.get(f"/snapshots/{_ID_NEW}/download-url", headers=_AUTH).json()
    assert body["expires_in_seconds"] == expected


def test_invalid_and_unknown_ids(client: TestClient, s3: _FakeS3) -> None:
    assert client.get("/snapshots/sha256:zzz/download-url", headers=_AUTH).status_code == 400
    # A bare word is a legal path value for {snapshot_id}, so it is rejected as invalid.
    assert client.get("/snapshots/history/download-url", headers=_AUTH).status_code == 400
    missing = "sha256:" + "c" * 64
    assert client.get(f"/snapshots/{missing}/download-url", headers=_AUTH).status_code == 404
    assert s3.signed == []


@pytest.mark.parametrize(
    "bad", ["../secret", "sha256:" + "A" * 64, "sha256:" + "a" * 63, "current.json", "history/x"]
)
def test_key_for_never_builds_a_key_from_arbitrary_input(bad: str) -> None:
    with pytest.raises(ValueError):
        snapshot_links.key_for(bad, "snapshots/")


def test_key_for_maps_only_the_two_allowed_shapes() -> None:
    assert snapshot_links.key_for("current", "snapshots/") == "snapshots/current.json"
    assert snapshot_links.key_for(_ID_OLD, "snapshots/") == f"snapshots/history/{_ID_OLD}.json"
