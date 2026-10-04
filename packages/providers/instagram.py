"""Instagram publisher — first LIVE platform adapter (Doc 14, contract §9).

Flow (Instagram Content Publishing via graph.instagram.com):
  photo:     POST /media {image_url, caption} -> creation_id
             POST /media_publish {creation_id}  -> {id}
  carousel:  POST /media {image_url, is_carousel_item=true} per child
             POST /media {media_type=CAROUSEL, children, caption}
             POST /media_publish -> {id}

HARD REQUIREMENT: the Instagram API fetches the image itself, so
``image_url`` must be PUBLICLY reachable. The HIL runs local-first — a
local file path is rejected by validate_payload with guidance to supply
a public URL (asset host) or fall back to the manual kit.

Human gate (Emenda 007): publish() is only ever called AFTER the human
triggers the publish route on a PENDING publication. Nothing publishes
by itself.

Credentials come from Settings only (never logged/repr'd — Doc 08).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

GRAPH = "https://graph.instagram.com/v21.0"

CAPTION_MAX = 2200  # Instagram caption limit
CAROUSEL_MAX_ITEMS = 10


@dataclass(frozen=True)
class PublishResult:
    remote_id: str
    permalink: str | None = None


class InstagramPublishError(Exception):
    """Conteúdo/configuração inutilizável — falha fechada."""


class InstagramPublishUnavailable(Exception):
    """Transiente (rede/timeout) — o caller decide o retry (Doc 03)."""
    """Normalized failure (never exposes credentials/raw response)."""


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


def credentials_available() -> bool:
    s = _settings()
    return bool(getattr(s, "meta_app_id", "")) and bool(
        getattr(s, "meta_instagram_token", "")
    )


class InstagramPublisher:
    """PlatformAdapter for Instagram (photo/carousel)."""

    key = "instagram"
    publication_method = "API"

    def __init__(self, *, token: str | None = None) -> None:
        if token is None:
            self._token = _settings().meta_instagram_token
        else:
            self._token = token
        self._last_http_status: int | None = None

    # --- PlatformAdapter ---------------------------------------------------

    def validate_payload(self, payload: dict[str, Any]) -> None:
        kind = payload.get("format")
        caption = str(payload.get("caption", ""))
        image_urls = payload.get("image_urls") or []
        if kind not in ("PHOTO_POST", "CAROUSEL"):
            raise InstagramPublishError(
                f"unsupported format for Instagram publish: {kind}"
            )
        if not caption.strip():
            raise InstagramPublishError("empty caption")
        if len(caption) > CAPTION_MAX:
            raise InstagramPublishError(
                f"caption exceeds Instagram limit ({len(caption)} > {CAPTION_MAX})"
            )
        if not isinstance(image_urls, list) or not image_urls:
            raise InstagramPublishError(
                "no image_urls provided — the Instagram API requires a PUBLIC "
                "image URL (it fetches the image itself); configure an asset "
                "host or use the manual kit"
            )
        if kind == "PHOTO_POST" and len(image_urls) != 1:
            raise InstagramPublishError("PHOTO_POST requires exactly 1 image")
        if kind == "CAROUSEL" and not (2 <= len(image_urls) <= CAROUSEL_MAX_ITEMS):
            raise InstagramPublishError(
                f"CAROUSEL requires 2-{CAROUSEL_MAX_ITEMS} images (got {len(image_urls)})"
            )
        for url in image_urls:
            if not str(url).startswith(("http://", "https://")):
                raise InstagramPublishError(
                    f"image url is not public: {str(url)[:60]}… — local paths "
                    "cannot be fetched by Instagram; host the asset publicly "
                    "or use the manual kit"
                )

    def publish(
        self, payload: dict[str, Any], *, idempotency_key: str
    ) -> PublishResult:
        self.validate_payload(payload)
        if not self._token:
            raise InstagramPublishError("instagram: no access token configured")

        kind = payload["format"]
        caption = str(payload["caption"])
        image_urls = [str(u) for u in payload["image_urls"]]

        if kind == "PHOTO_POST":
            creation_id = self._create_container(
                {"image_url": image_urls[0], "caption": caption}
            )
            remote_id = self._publish_container(creation_id)
        else:
            children = [
                self._create_container({"image_url": u, "is_carousel_item": "true"})
                for u in image_urls
            ]
            container_id = self._create_container(
                {
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": caption,
                }
            )
            remote_id = self._publish_container(container_id)

        return PublishResult(remote_id=remote_id, permalink=self._permalink(remote_id))

    def collect_analytics(self, remote_id: str) -> dict[str, Any]:
        # Doc 15 metrics for Instagram live posts land with the analytics
        # milestone; this stub keeps the adapter contract complete.
        raise InstagramPublishError("instagram analytics collection not wired yet")

    def revoke_account(self, credential_ref: str) -> bool:
        """Best-effort revoke (AMENDMENT-008 logout rule). Never raises."""
        try:
            url = f"{GRAPH}/{credential_ref}/permissions"
            r = httpx.delete(url, params={"access_token": self._token}, timeout=30)
            self._last_http_status = r.status_code
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    # --- token lifecycle -----------------------------------------------------

    def refresh_long_lived(self) -> dict[str, Any]:
        """Renew a valid long-lived token (>=24h old) for another 60 days."""
        if not self._token:
            raise InstagramPublishError("instagram: no access token configured")
        try:
            r = httpx.get(
                f"{GRAPH}/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": self._token,
                },
                timeout=30,
            )
            self._last_http_status = r.status_code
            data = r.json()
        except httpx.HTTPError as exc:
            raise InstagramPublishError(
                f"instagram: network error {exc.__class__.__name__}"
            ) from exc
        if self._last_http_status != 200 or "access_token" not in data:
            raise InstagramPublishError(
                f"instagram: refresh failed (HTTP {self._last_http_status})"
            )
        expires_in = int(data.get("expires_in", 0))
        return {
            "access_token": data["access_token"],
            "expires_in": expires_in,
            "expires_at": (
                datetime.now(UTC) + timedelta(seconds=expires_in)
            ).date().isoformat(),
        }

    # --- internals ----------------------------------------------------------

    def _post(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        data = {**data, "access_token": self._token}
        try:
            r = httpx.post(f"{GRAPH}/{path}", data=data, timeout=60)
            self._last_http_status = r.status_code
            body = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else {}
            )
        except httpx.TimeoutException as exc:
            raise InstagramPublishError("instagram: timeout") from exc
        except httpx.HTTPError as exc:
            raise InstagramPublishError(
                f"instagram: network error {exc.__class__.__name__}"
            ) from exc
        if self._last_http_status != 200 or "id" not in body:
            message = body.get("error", {}).get(
                "message", f"HTTP {self._last_http_status}"
            )
            raise InstagramPublishError(f"instagram: {message[:200]}")
        return body

    def _get(self, path: str, fields: str) -> dict[str, Any]:
        try:
            r = httpx.get(
                f"{GRAPH}/{path}",
                params={"fields": fields, "access_token": self._token},
                timeout=30,
            )
            self._last_http_status = r.status_code
            body = r.json() if r.status_code == 200 else {}
        except httpx.HTTPError as exc:
            raise InstagramPublishError(
                f"instagram: network error {exc.__class__.__name__}"
            ) from exc
        if self._last_http_status != 200:
            raise InstagramPublishError(
                f"instagram: fetch failed (HTTP {self._last_http_status})"
            )
        return body

    def _create_container(self, data: dict[str, str]) -> str:
        # /me/media — sem o objeto usuário a API interpreta "media" como
        # ID de objeto e devolve "Object with ID 'media' does not exist".
        return self._post("me/media", data)["id"]

    def _wait_container_ready(self, creation_id: str, *, timeout_s: float = 60.0) -> None:
        """Sonda status_code do container até FINISHED (a API rejeita
        media_publish de container ainda processando: 'Media ID is not
        available'). Falha fechada em ERROR; timeout é transiente."""
        import time as _time

        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            body = self._get(creation_id, "status_code")
            status = str(body.get("status_code", ""))
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramPublishError(
                    "instagram: container processing failed (status ERROR)"
                )
            if status != "IN_PROGRESS":
                raise InstagramPublishError(
                    f"instagram: unexpected container status {status!r}"
                )
            _time.sleep(3.0)
        raise InstagramPublishUnavailable(
            "instagram: container still processing after timeout"
        )

    def _publish_container(self, creation_id: str) -> str:
        self._wait_container_ready(creation_id)
        return self._post("me/media_publish", {"creation_id": creation_id})["id"]

    def _permalink(self, remote_id: str) -> str | None:
        try:
            return self._get(remote_id, "permalink").get("permalink")
        except InstagramPublishError:
            return None  # permalink is cosmetic; publish already succeeded
