"""Supabase asset host (contrato §6): mockado, sem rede. Prova o contrato —
bucket público garantido, upload idempotente, erros classificados, e o
mapeamento do kit de exportação para URLs públicas."""

from types import SimpleNamespace

import pytest

from packages.providers import supabase_storage as mod
from packages.providers.supabase_storage import (
    SupabaseAssetHost,
    SupabaseError,
    SupabaseUnavailable,
    find_export_kit_images,
)


def _response(status=200, body=None):
    return SimpleNamespace(status_code=status, json=lambda: body or {})


def _host():
    return SupabaseAssetHost(
        url="https://ref.supabase.co", service_key="sk", bucket="urdia-assets"
    )


def test_missing_config_fails_closed():
    with pytest.raises(SupabaseError):
        SupabaseAssetHost(url="", service_key="sk")
    with pytest.raises(SupabaseError):
        SupabaseAssetHost(url="https://ref.supabase.co", service_key="")


def test_public_url_shape():
    assert _host().public_url("pkg/img.jpg") == (
        "https://ref.supabase.co/storage/v1/object/public/urdia-assets/pkg/img.jpg"
    )


def test_ensure_bucket_is_noop_when_public(monkeypatch):
    monkeypatch.setattr(
        mod.httpx, "get", lambda *a, **kw: _response(200, {"public": True})
    )
    _host().ensure_bucket()  # não deve criar nada


def test_ensure_bucket_creates_when_missing(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        # Particularidade real da Storage API: 400 + NoSuchBucket no corpo.
        return _response(400, {"statusCode": "404", "code": "NoSuchBucket"})

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _response(201)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    monkeypatch.setattr(mod.httpx, "post", fake_post)
    _host().ensure_bucket()
    assert calls == [{"name": "urdia-assets", "public": True}]


def test_ensure_bucket_also_handles_plain_404(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        return _response(404)

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _response(201)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    monkeypatch.setattr(mod.httpx, "post", fake_post)
    _host().ensure_bucket()
    assert calls == [{"name": "urdia-assets", "public": True}]


def test_ensure_bucket_rejects_private(monkeypatch):
    monkeypatch.setattr(
        mod.httpx, "get", lambda *a, **kw: _response(200, {"public": False})
    )
    with pytest.raises(SupabaseError, match="not public"):
        _host().ensure_bucket()


def test_5xx_is_transient(monkeypatch):
    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: _response(503))
    with pytest.raises(SupabaseUnavailable):
        _host().ensure_bucket()


def test_upload_returns_public_url(monkeypatch, tmp_path):
    captured = {}
    image = tmp_path / "img.jpg"
    image.write_bytes(b"\xff\xd8fakejpeg")

    def fake_post(url, headers=None, content=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _response(200)

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    url = _host().upload_file(image, remote_path="pkg/img.jpg")
    assert url.endswith("/object/public/urdia-assets/pkg/img.jpg")
    assert captured["url"].endswith("/object/urdia-assets/pkg/img.jpg")
    assert captured["headers"]["Content-Type"] == "image/jpeg"
    assert captured["headers"]["x-upsert"] == "true"


def test_upload_rejects_unsupported_type(tmp_path):
    file = tmp_path / "img.gif"
    file.write_bytes(b"gif")
    with pytest.raises(SupabaseError, match="unsupported"):
        _host().upload_file(file)


def test_find_export_kit_images(tmp_path):
    kit = tmp_path / "post-2026-10-04-2f4e8c48"
    (kit / "image").mkdir(parents=True)
    (kit / "image" / "a.jpg").write_bytes(b"x")
    (kit / "image" / "b.json").write_text("{}", encoding="utf-8")
    (kit / "image" / "c.png").write_bytes(b"x")
    images = find_export_kit_images(tmp_path, "2f4e8c48-0000-0000-0000-000000000000")
    assert [i.name for i in images] == ["a.jpg", "c.png"]
    assert find_export_kit_images(tmp_path, "sem-kit") == []


def test_find_export_kit_prefers_render(tmp_path):
    kit = tmp_path / "post-2026-10-04-2f4e8c48"
    (kit / "image").mkdir(parents=True)
    (kit / "image" / "asset.jpg").write_bytes(b"x")
    (kit / "image" / "render-photo-post.png").write_bytes(b"x")
    images = find_export_kit_images(tmp_path, "2f4e8c48-0000-0000-0000-000000000000")
    assert [i.name for i in images] == ["render-photo-post.png"]
