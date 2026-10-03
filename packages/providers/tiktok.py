"""TikTok Content Posting API adapter.

Implements the current Direct Post video flow with FILE_UPLOAD. The adapter is
credential-injected and never logs access tokens. Publishing is asynchronous:
TikTok returns a publish_id, which must be polled before a publication can be
marked complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

API = "https://open.tiktokapis.com/v2"
CREATOR_INFO_PATH = "post/publish/creator_info/query/"
INIT_VIDEO_PATH = "post/publish/video/init/"
STATUS_PATH = "post/publish/status/fetch/"
CAPTION_MAX = 2200
MIN_CHUNK_SIZE = 5 * 1024 * 1024
MAX_CHUNK_SIZE = 64 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024


@dataclass(frozen=True)
class TikTokPublishResult:
    publish_id: str
    status: str = "PROCESSING_UPLOAD"
    post_id: int | None = None


class TikTokPublishError(Exception):
    """Normalized TikTok failure that never exposes credentials."""


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


def credentials_available() -> bool:
    return bool(getattr(_settings(), "tiktok_access_token", ""))


class TikTokPublisher:
    key = "tiktok"
    publication_method = "API"

    def __init__(self, *, token: str | None = None, timeout: float = 60.0) -> None:
        self._token = (
            token if token is not None else getattr(_settings(), "tiktok_access_token", "")
        )
        self._timeout = timeout
        self._last_http_status: int | None = None

    def validate_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("format") not in {"VIDEO", "SHORT_VIDEO", "REEL"}:
            raise TikTokPublishError("TikTok requires a video publication format")
        caption = str(payload.get("caption", ""))
        if len(caption) > CAPTION_MAX:
            raise TikTokPublishError(
                f"caption exceeds TikTok limit ({len(caption)} > {CAPTION_MAX})"
            )
        privacy = str(payload.get("privacy_level", "")).strip()
        if not privacy:
            raise TikTokPublishError("privacy_level is required from creator_info")
        source = payload.get("video_path") or payload.get("video_url")
        if not source:
            raise TikTokPublishError("video_path or video_url is required")
        if payload.get("video_path") and not Path(str(payload["video_path"])).is_file():
            raise TikTokPublishError("video_path does not exist")
        if payload.get("video_url") and not str(payload["video_url"]).startswith(
            ("http://", "https://")
        ):
            raise TikTokPublishError("video_url must be an absolute HTTP(S) URL")

    def creator_info(self) -> dict[str, Any]:
        body = self._post_json(CREATOR_INFO_PATH, {})
        data = body.get("data") or {}
        privacy_options = data.get("privacy_level_options") or []
        if not isinstance(privacy_options, list) or not privacy_options:
            raise TikTokPublishError("TikTok returned no privacy options")
        return data

    def publish(self, payload: dict[str, Any], *, idempotency_key: str) -> TikTokPublishResult:
        del idempotency_key  # TikTok has no idempotency key field in this API flow.
        self.validate_payload(payload)
        if not self._token:
            raise TikTokPublishError("tiktok: no access token configured")

        creator = self.creator_info()
        privacy = str(payload["privacy_level"])
        options = {str(v) for v in creator.get("privacy_level_options", [])}
        if privacy not in options:
            raise TikTokPublishError("privacy_level is not available for this creator")

        title = str(payload.get("caption", ""))
        post_info: dict[str, Any] = {
            "privacy_level": privacy,
            "title": title,
            "disable_duet": bool(payload.get("disable_duet", False)),
            "disable_comment": bool(payload.get("disable_comment", False)),
            "disable_stitch": bool(payload.get("disable_stitch", False)),
        }
        if payload.get("is_aigc") is not None:
            post_info["is_aigc"] = bool(payload["is_aigc"])
        if payload.get("brand_content_toggle") is not None:
            post_info["brand_content_toggle"] = bool(payload["brand_content_toggle"])
        if payload.get("brand_organic_toggle") is not None:
            post_info["brand_organic_toggle"] = bool(payload["brand_organic_toggle"])
        if payload.get("video_cover_timestamp_ms") is not None:
            post_info["video_cover_timestamp_ms"] = int(payload["video_cover_timestamp_ms"])

        video_path = payload.get("video_path")
        if video_path:
            path = Path(str(video_path))
            size = path.stat().st_size
            chunk_size = self._chunk_size(size)
            total_chunks = (size + chunk_size - 1) // chunk_size
            init = self._post_json(
                INIT_VIDEO_PATH,
                {
                    "post_info": post_info,
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": size,
                        "chunk_size": chunk_size,
                        "total_chunk_count": total_chunks,
                    },
                },
            )
            publish_id = self._require_publish_id(init)
            upload_url = (init.get("data") or {}).get("upload_url")
            if not upload_url:
                raise TikTokPublishError("TikTok did not return an upload URL")
            self._upload_file(upload_url, path, size, chunk_size)
            return TikTokPublishResult(publish_id=publish_id)

        video_url = str(payload["video_url"])
        init = self._post_json(
            INIT_VIDEO_PATH,
            {
                "post_info": post_info,
                "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
            },
        )
        return TikTokPublishResult(
            publish_id=self._require_publish_id(init), status="PROCESSING_DOWNLOAD"
        )

    def status(self, publish_id: str) -> dict[str, Any]:
        if not publish_id or len(publish_id) > 64:
            raise TikTokPublishError("invalid publish_id")
        body = self._post_json(STATUS_PATH, {"publish_id": publish_id})
        data = body.get("data") or {}
        status = str(data.get("status", ""))
        if not status:
            raise TikTokPublishError("TikTok returned no publication status")
        return {
            "publish_id": publish_id,
            "status": status,
            "fail_reason": data.get("fail_reason"),
            "post_ids": data.get("publicaly_available_post_id") or [],
            "uploaded_bytes": data.get("uploaded_bytes"),
            "downloaded_bytes": data.get("downloaded_bytes"),
        }

    def _chunk_size(self, size: int) -> int:
        if size <= 0:
            raise TikTokPublishError("video file is empty")
        if size < MIN_CHUNK_SIZE:
            return size
        return min(DEFAULT_CHUNK_SIZE, MAX_CHUNK_SIZE)

    def _upload_file(self, upload_url: str, path: Path, total_size: int, chunk_size: int) -> None:
        start = 0
        try:
            with path.open("rb") as fh:
                while start < total_size:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        raise TikTokPublishError("video file ended before expected size")
                    end = start + len(chunk) - 1
                    headers = {
                        "Content-Type": self._mime_type(path),
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total_size}",
                    }
                    response = httpx.put(
                        upload_url, content=chunk, headers=headers, timeout=self._timeout
                    )
                    self._last_http_status = response.status_code
                    if response.status_code not in {201, 206}:
                        raise TikTokPublishError(
                            f"tiktok: upload failed (HTTP {response.status_code})"
                        )
                    start = end + 1
        except httpx.TimeoutException as exc:
            raise TikTokPublishError("tiktok: upload timeout") from exc
        except httpx.HTTPError as exc:
            raise TikTokPublishError(f"tiktok: network error {exc.__class__.__name__}") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """TikTok v2 requires the token in the Authorization header — an
        access_token query param is rejected as invalid_params."""
        try:
            r = httpx.post(
                f"{API}/{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout,
            )
            self._last_http_status = r.status_code
            body = r.json()
        except httpx.HTTPError as exc:
            raise TikTokPublishError(
                f"tiktok: network error {exc.__class__.__name__}"
            ) from exc
        error = body.get("error") or {}
        if r.status_code != 200 or error.get("code") not in ("ok", None):
            message = error.get("message") or f"HTTP {r.status_code}"
            raise TikTokPublishError(f"tiktok: {message[:200]}")
        return body

    def _require_publish_id(body: dict[str, Any]) -> str:
        publish_id = (body.get("data") or {}).get("publish_id")
        if not publish_id:
            raise TikTokPublishError("TikTok did not return a publish_id")
        return publish_id

    def _mime_type(path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
        }.get(suffix, "video/mp4")
    def _mime_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".mov":
            return "video/quicktime"
        if suffix == ".webm":
            return "video/webm"
        return "video/mp4"
