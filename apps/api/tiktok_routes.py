"""TikTok OAuth endpoints (contract §9/§14): connect the operator's own
TikTok account so the Content Posting API can publish on its behalf.

Flow (desktop-first, no public backend): the dashboard opens the authorize
URL; TikTok redirects to the public callback page
(https://antigomundonovo.github.io/tiktok-callback.html) which shows the
authorization code; the operator pastes it into the dashboard, which calls
/exchange. The resulting access token is stored locally in `.env`
(local-first; never logged/repr'd — Doc 08). Nothing is published by this
flow — publishing still goes through the human gate routes.
"""

from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from packages.domain.models import User
from packages.shared.db import get_session

router = APIRouter(prefix="/api/v1/social/tiktok")

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CALLBACK_URL = "https://antigomundonovo.github.io/tiktok-callback.html"
SCOPES = "user.info.basic,video.publish,video.upload"


def _settings():
    from packages.shared.settings import get_settings

    return get_settings()


def _persist_env_var(key: str, value: str) -> None:
    """Local-first credential storage: upsert one var in the operator's
    local .env (protected by .gitignore)."""
    from pathlib import Path

    path = Path(".env")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replaced = False
    out: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


@router.get("/authorize")
def authorize(user: User = Depends(get_current_user)) -> dict:
    """Return the TikTok consent URL for the operator to open."""
    s = _settings()
    if not s.tiktok_client_key:
        raise HTTPException(
            status_code=409,
            detail="tiktok: TIKTOK_CLIENT_KEY is not configured in .env",
        )
    state = uuid4().hex
    from urllib.parse import urlencode

    authorize_url = (
        f"{AUTHORIZE_URL}?"
        + urlencode(
            {
                "client_key": s.tiktok_client_key,
                "scope": SCOPES,
                "response_type": "code",
                "redirect_uri": CALLBACK_URL,
                "state": state,
            }
        )
    )
    return {"authorize_url": authorize_url, "state": state, "callback": CALLBACK_URL}


class ExchangeBody(BaseModel):
    code: str = Field(min_length=1, max_length=512)


@router.post("/exchange")
def exchange_code(
    body: ExchangeBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Trade the authorization code (shown on the callback page) for the
    operator's access token, and store it locally. Never exposes the
    client secret; never logs tokens."""
    s = _settings()
    if not s.tiktok_client_key or not s.tiktok_client_secret:
        raise HTTPException(
            status_code=409,
            detail="tiktok: TIKTOK_CLIENT_KEY/SECRET are not configured in .env",
        )
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_key": s.tiktok_client_key,
                "client_secret": s.tiktok_client_secret,
                "code": body.code,
                "grant_type": "authorization_code",
                "redirect_uri": CALLBACK_URL,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"tiktok: network error {exc.__class__.__name__}"
        ) from exc
    data = r.json() if r.status_code == 200 else {}
    if r.status_code != 200 or not data.get("access_token"):
        try:
            error_body = r.json()
        except Exception:
            error_body = {}
        message = (
            error_body.get("error_description")
            or error_body.get("error")
            or error_body.get("message")
            or f"HTTP {r.status_code}"
        )
        raise HTTPException(status_code=409, detail=f"tiktok exchange failed: {message}")

    _persist_env_var("TIKTOK_ACCESS_TOKEN", str(data["access_token"]))
    open_id = str(data.get("open_id", ""))
    if open_id:
        _persist_env_var("TIKTOK_OPEN_ID", open_id)
    return {
        "status": "connected",
        "open_id": open_id,
        "scope": data.get("scope"),
        "expires_in": data.get("expires_in"),
        "stored": "TIKTOK_ACCESS_TOKEN written to local .env",
    }


@router.get("/connection")
def connection_status(user: User = Depends(get_current_user)) -> dict:
    s = _settings()
    return {
        "connected": bool(s.tiktok_access_token),
        "open_id": getattr(s, "tiktok_open_id", None),
        "platform": "tiktok",
        "publish_method": "API (sandbox until app review approves)",
    }


@router.get("/callback")
def callback_exchange(code: str = "", state: str = "") -> dict:
    """No session required: this is the OAuth redirect landing on the
    operator's own machine — the short-lived single-use code IS the
    authorization (local-first desktop pattern)."""
    """Direct landing for the operator: paste- or click-through the code from
    the public callback page and connect in one step (demo-friendly)."""
    if not code:
        raise HTTPException(status_code=422, detail="missing ?code=")
    s = _settings()
    if not s.tiktok_client_key or not s.tiktok_client_secret:
        raise HTTPException(
            status_code=409,
            detail="tiktok: TIKTOK_CLIENT_KEY/SECRET are not configured in .env",
        )
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_key": s.tiktok_client_key,
                "client_secret": s.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": CALLBACK_URL,
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"tiktok: network error {exc.__class__.__name__}"
        ) from exc
    data = r.json() if r.status_code == 200 else {}
    if r.status_code != 200 or not data.get("access_token"):
        try:
            error_body = r.json()
        except Exception:
            error_body = {}
        message = (
            error_body.get("error_description")
            or error_body.get("error")
            or error_body.get("message")
            or f"HTTP {r.status_code}"
        )
        raise HTTPException(status_code=409, detail=f"tiktok exchange failed: {message}")
    _persist_env_var("TIKTOK_ACCESS_TOKEN", str(data["access_token"]))
    open_id = str(data.get("open_id", ""))
    if open_id:
        _persist_env_var("TIKTOK_OPEN_ID", open_id)
    return {
        "status": "connected",
        "open_id": open_id,
        "scope": data.get("scope"),
        "note": "TikTok connected — sandbox posts stay private until app review approves",
    }
