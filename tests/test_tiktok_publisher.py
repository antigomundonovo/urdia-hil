"""TikTok Content Posting API tests. All HTTP is mocked; nothing is posted."""

from pathlib import Path

import httpx
import pytest

from packages.providers import tiktok as tiktok_module
from packages.providers.tiktok import TikTokPublisher, TikTokPublishError


def _response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=body,
        headers={"content-type": "application/json"},
    )


def _ok(body: dict) -> httpx.Response:
    return _response(200, body)


def test_validate_rejects_missing_privacy_and_media(tmp_path: Path):
    publisher = TikTokPublisher(token="token")
    with pytest.raises(TikTokPublishError, match="privacy_level"):
        publisher.validate_payload({"format": "VIDEO", "caption": "x"})
    with pytest.raises(TikTokPublishError, match="video_path or video_url"):
        publisher.validate_payload(
            {"format": "VIDEO", "caption": "x", "privacy_level": "SELF_ONLY"}
        )


def test_validate_rejects_missing_local_file():
    publisher = TikTokPublisher(token="token")
    with pytest.raises(TikTokPublishError, match="does not exist"):
        publisher.validate_payload(
            {
                "format": "VIDEO",
                "caption": "x",
                "privacy_level": "SELF_ONLY",
                "video_path": "C:/does/not/exist.mp4",
            }
        )


def test_publish_file_upload_queries_creator_and_uploads_chunks(monkeypatch, tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"a" * (10 * 1024 * 1024 + 123))
    post_calls: list[tuple[str, dict]] = []
    put_calls: list[tuple[str, dict, int]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        post_calls.append((url, dict(json or {})))
        if url.endswith("creator_info/query/"):
            return _ok(
                {
                    "data": {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]},
                    "error": {"code": "ok"},
                }
            )
        return _ok(
            {
                "data": {
                    "publish_id": "v_pub_file~test-1",
                    "upload_url": "https://upload.test/video?token=abc",
                },
                "error": {"code": "ok"},
            }
        )

    def fake_put(url, content=None, headers=None, timeout=None):
        put_calls.append((url, dict(headers or {}), len(content or b"")))
        status = 201 if len(put_calls) == 2 else 206
        return _response(status, {"ok": True})

    monkeypatch.setattr(tiktok_module.httpx, "post", fake_post)
    monkeypatch.setattr(tiktok_module.httpx, "put", fake_put)

    result = TikTokPublisher(token="TOKEN-DE-TESTE").publish(
        {
            "format": "VIDEO",
            "caption": "URDIA",
            "privacy_level": "SELF_ONLY",
            "video_path": str(video),
            "is_aigc": True,
        },
        idempotency_key="workspace:package:tiktok:v1",
    )

    assert result.publish_id == "v_pub_file~test-1"
    assert result.status == "PROCESSING_UPLOAD"
    assert len(post_calls) == 2
    assert post_calls[0][0].endswith("creator_info/query/")
    init = post_calls[1][1]
    assert init["source_info"]["source"] == "FILE_UPLOAD"
    # sandbox validated pattern: single chunk sized exactly like the video
    assert init["source_info"]["chunk_size"] == init["source_info"]["video_size"]
    assert init["source_info"]["total_chunk_count"] == 1
    assert init["post_info"]["is_aigc"] is True
    assert len(put_calls) == 1  # single-chunk upload (sandbox validated pattern)
    assert put_calls[0][1]["Content-Range"] == "bytes 0-10485882/10485883"


def test_publish_url_uses_pull_from_url(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(dict(json or {}))
        if url.endswith("creator_info/query/"):
            return _ok(
                {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE"]}, "error": {"code": "ok"}}
            )
        return _ok({"data": {"publish_id": "url-pub-1"}, "error": {"code": "ok"}})

    monkeypatch.setattr(tiktok_module.httpx, "post", fake_post)
    result = TikTokPublisher(token="token").publish(
        {
            "format": "VIDEO",
            "caption": "x",
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "video_url": "https://assets.example/video.mp4",
        },
        idempotency_key="k",
    )
    assert result.publish_id == "url-pub-1"
    assert result.status == "PROCESSING_DOWNLOAD"
    assert calls[1]["source_info"] == {
        "source": "PULL_FROM_URL",
        "video_url": "https://assets.example/video.mp4",
    }


def test_status_normalizes_tiktok_state(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("status/fetch/")
        assert json == {"publish_id": "pub-1"}
        return _ok(
            {
                "data": {
                    "status": "PUBLISH_COMPLETE",
                    "publicaly_available_post_id": [123456789],
                },
                "error": {"code": "ok"},
            }
        )

    monkeypatch.setattr(tiktok_module.httpx, "post", fake_post)
    result = TikTokPublisher(token="token").status("pub-1")
    assert result["status"] == "PUBLISH_COMPLETE"
    assert result["post_ids"] == [123456789]


def test_errors_never_expose_token(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(tiktok_module.httpx, "post", boom)
    with pytest.raises(TikTokPublishError) as exc_info:
        TikTokPublisher(token="SEGREDO-TIKTOK").creator_info()
    assert "SEGREDO-TIKTOK" not in str(exc_info.value)
