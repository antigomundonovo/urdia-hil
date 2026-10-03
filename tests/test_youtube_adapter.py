"""YouTubeAdapter tests — yt_dlp and network are mocked; no real calls."""

import sys
import types
from types import SimpleNamespace

import pytest

from packages.research.adapters import (
    AdapterError,
    YouTubeAdapter,
    _vtt_to_text,
    get_adapter,
)
from packages.research.fetcher import SafeFetcher


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL; returns the canned info dict."""

    last_opts: dict | None = None

    def __init__(self, opts):
        _FakeYDL.last_opts = dict(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return _FakeYDL.info


class _FakeFetcher:
    """SafeFetcher stand-in serving a canned caption file."""

    def __init__(self, body: bytes = b"", status_code: int = 200):
        self.body = body
        self.status_code = status_code
        self.fetched: list[str] = []

    def fetch(self, url):
        self.fetched.append(url)
        return SimpleNamespace(
            status_code=self.status_code, content=self.body, url=url
        )


def _install_fake_ydl(monkeypatch, info: dict):
    _FakeYDL.info = info
    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = _FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)


VTT = (
    "WEBVTT\nKind: captions\nLanguage: pt-BR\n\n"
    "00:00:01.000 --> 00:00:03.000\nO bondinho\n< c >do Pão de Açúcar</c>\n\n"
    "00:00:03.000 --> 00:00:05.000\ncomeçou a operar em 1911.\n"
).encode()


def _video_info(**over):
    info = {
        "id": "abc123",
        "title": "Bondinho histórico",
        "description": "Documentário sobre o bondinho de 1911.",
        "upload_date": "20240115",
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "subtitles": {
            "pt-BR": [{"ext": "vtt", "url": "https://captions.test/pt.vtt"}]
        },
        "automatic_captions": {},
    }
    info.update(over)
    return info


def test_vtt_flattens_to_transcript():
    assert _vtt_to_text(VTT.decode()) == (
        "O bondinho do Pão de Açúcar começou a operar em 1911."
    )


def test_single_video_yields_transcript_item(monkeypatch):
    fetcher = _FakeFetcher(body=VTT)
    _install_fake_ydl(monkeypatch, _video_info())
    items = YouTubeAdapter(fetcher).fetch_items(
        "https://www.youtube.com/watch?v=abc123"
    )
    assert len(items) == 1
    item = items[0]
    assert item.url == "https://www.youtube.com/watch?v=abc123"
    assert item.title == "Bondinho histórico"
    assert item.published_at == "2024-01-15"
    assert "começou a operar em 1911" in (item.summary or "")
    # transcript (not raw vtt) became the summary
    assert "WEBVTT" not in (item.summary or "")


def test_playlist_yields_metadata_items(monkeypatch):
    playlist = {
        "_type": "playlist",
        "entries": [
            {"id": "v1", "title": "Vídeo 1", "upload_date": "20240102"},
            {"id": "v2", "title": "Vídeo 2", "description": "desc v2"},
            None,  # skipped
        ],
    }
    _install_fake_ydl(monkeypatch, playlist)
    items = YouTubeAdapter(_FakeFetcher()).fetch_items(
        "https://www.youtube.com/@canal"
    )
    assert [i.url for i in items] == [
        "https://www.youtube.com/watch?v=v1",
        "https://www.youtube.com/watch?v=v2",
    ]
    assert items[0].published_at == "2024-01-02"
    assert items[1].summary == "desc v2"


def test_fetch_failure_wraps_as_adapter_error(monkeypatch):
    def boom(self, url, download=False):
        raise RuntimeError("DownloadError: sign in to confirm you're not a bot")

    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = type("YDL", (), {"__init__": boom, "__enter__": boom})
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    with pytest.raises(AdapterError, match="youtube fetch failed"):
        YouTubeAdapter(_FakeFetcher()).fetch_items("https://youtu.be/x")


def test_cookies_from_settings_are_injected(monkeypatch):
    _install_fake_ydl(monkeypatch, _video_info())
    monkeypatch.setattr(
        "packages.shared.settings.get_settings",
        lambda: SimpleNamespace(
            yt_dlp_cookies_from_browser="chrome", yt_dlp_cookies_file=None
        ),
    )
    YouTubeAdapter(_FakeFetcher()).fetch_items("https://youtu.be/abc123")
    assert _FakeYDL.last_opts.get("cookiesfrombrowser") == ("chrome",)


def test_caption_fetch_requires_http_200(monkeypatch):
    fetcher = _FakeFetcher(body=VTT, status_code=403)
    _install_fake_ydl(monkeypatch, _video_info())
    items = YouTubeAdapter(fetcher).fetch_items("https://youtu.be/abc123")
    # caption rejected -> falls back to description
    assert items[0].summary == "Documentário sobre o bondinho de 1911."


def test_registered_in_adapter_factory():

    adapter = get_adapter("youtube", SafeFetcher())
    assert adapter.source_type == "youtube"
