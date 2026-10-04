"""Asset host público via Supabase Storage (contrato §6 — "HIL pode usar
Supabase atrás de sua boundary de persistência").

A API do Instagram exige a imagem em URL PUBLICA; arquivos locais não são
buscados. Este módulo sobe a mídia já exportada (kit de exportação) para um
bucket público do Supabase e devolve as URLs — o pedaço que faltava para a
publicação Instagram de ponta a ponta.

A service key vive só em Settings (`.env`, nunca versionada/logada/repr —
Doc 08). Erros seguem o padrão dos providers: indisponibilidade transitória
vs. conteúdo inutilizável (falha fechada).
"""

from __future__ import annotations

from pathlib import Path

import httpx

MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


class SupabaseError(Exception):
    """Falha fechada (configuração/pedido inválido)."""


class SupabaseUnavailable(Exception):
    """Transiente (rede/5xx/429) — o caller decide o retry."""


class SupabaseAssetHost:
    key = "supabase-storage"

    def __init__(
        self,
        *,
        url: str,
        service_key: str,
        bucket: str = "urdia-assets",
        timeout: float = 60.0,
    ) -> None:
        if not url:
            raise SupabaseError("supabase: no project URL configured")
        if not service_key:
            raise SupabaseError("supabase: no service key configured")
        self._url = url.rstrip("/")
        self._key = service_key
        self._bucket = bucket
        self._timeout = timeout

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Projetos novos usam chaves sb_secret_* que o Storage exige no
        header `apikey`; os legados JWT funcionam nos dois formatos."""
        headers = {"apikey": self._key, "Authorization": f"Bearer {self._key}"}
        if extra:
            headers.update(extra)
        return headers

    def public_url(self, remote_path: str) -> str:
        return (
            f"{self._url}/storage/v1/object/public/{self._bucket}/{remote_path}"
        )

    def ensure_bucket(self) -> None:
        """Cria o bucket público se não existir (idempotente)."""
        try:
            response = httpx.get(
                f"{self._url}/storage/v1/bucket/{self._bucket}",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SupabaseUnavailable(
                f"supabase: network error {exc.__class__.__name__}"
            ) from exc
        if response.status_code == 200:
            data = response.json()
            if not data.get("public"):
                raise SupabaseError(
                    f"supabase: bucket {self._bucket!r} exists but is not public"
                )
            return
        if response.status_code in (429,) or response.status_code >= 500:
            raise SupabaseUnavailable(f"supabase: HTTP {response.status_code}")
        if self._is_missing_bucket(response):
            # Particularidade da Storage API: bucket inexistente volta
            # HTTP 400 com statusCode/code de "não encontrado" no corpo.
            create = httpx.post(
                f"{self._url}/storage/v1/bucket",
                headers=self._headers(),
                json={"name": self._bucket, "public": True},
                timeout=self._timeout,
            )
            if create.status_code not in (200, 201):
                raise SupabaseError(
                    f"supabase: bucket creation failed (HTTP {create.status_code})"
                )
            return
        if response.status_code in (401, 403):
            raise SupabaseUnavailable(
                f"supabase: credential rejected ({response.status_code})"
            )
        raise SupabaseError(f"supabase: HTTP {response.status_code}")

    @staticmethod
    def _is_missing_bucket(response: httpx.Response) -> bool:
        if response.status_code == 404:
            return True
        if response.status_code != 400:
            return False
        try:
            body = response.json()
        except ValueError:
            return False
        return body.get("code") == "NoSuchBucket" or body.get("statusCode") == 404

    def upload_file(self, local_path: Path, remote_path: str | None = None) -> str:
        """Sobe um arquivo e devolve a URL pública. Idempotente por
        remote_path (mesmo caminho = mesmo objeto sobrescrito)."""
        path = Path(local_path)
        suffix = path.suffix.lower()
        mime = MIME_BY_SUFFIX.get(suffix)
        if mime is None:
            raise SupabaseError(f"supabase: unsupported asset type {suffix!r}")
        remote = remote_path or path.name
        try:
            response = httpx.post(
                f"{self._url}/storage/v1/object/{self._bucket}/{remote}",
                headers=self._headers(
                    {"Content-Type": mime, "x-upsert": "true"}
                ),
                content=path.read_bytes(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise SupabaseUnavailable("supabase: upload timeout") from exc
        except httpx.HTTPError as exc:
            raise SupabaseUnavailable(
                f"supabase: network error {exc.__class__.__name__}"
            ) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise SupabaseUnavailable(f"supabase: HTTP {response.status_code}")
        if response.status_code in (401, 403):
            raise SupabaseUnavailable(
                f"supabase: credential rejected ({response.status_code})"
            )
        if response.status_code not in (200, 201):
            detail = ""
            try:
                detail = str((response.json() or {}).get("message", ""))[:200]
            except ValueError:
                pass
            raise SupabaseError(f"supabase: upload failed (HTTP {response.status_code}) {detail}")
        return self.public_url(remote)


def find_export_kit_images(export_root: Path, package_id: str) -> list[Path]:
    """Imagens publicáveis do kit de exportação de um pacote
    (`post-*-{short8}/image/*`). O RENDER final (`render-*`) é a peça
    publicável — se existir, só ele vai; sem render, os assets brutos."""
    short_id = str(package_id)[:8]
    if not export_root.is_dir():
        return []
    kits = sorted(export_root.glob(f"post-*-{short_id}"))
    if not kits:
        return []
    image_dir = kits[-1] / "image"
    if not image_dir.is_dir():
        return []
    images = sorted(
        p for p in image_dir.iterdir()
        if p.suffix.lower() in MIME_BY_SUFFIX and p.is_file()
    )
    renders = [p for p in images if p.name.startswith("render-")]
    return renders or images
