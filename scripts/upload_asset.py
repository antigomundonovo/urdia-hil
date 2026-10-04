"""Smoke do asset host Supabase (contrato §6): cria o bucket público se
necessário e sobe um arquivo, imprimindo a URL pública.

Uso (após SUPABASE_URL + SUPABASE_SERVICE_KEY no .env):
    python -m scripts.upload_asset assets/exports/post-*/image/exemplo.jpg
"""

import sys

sys.path.insert(0, ".")

from pathlib import Path  # noqa: E402

from packages.providers.supabase_storage import (  # noqa: E402
    SupabaseAssetHost,
    SupabaseError,
    SupabaseUnavailable,
)
from packages.shared.settings import get_settings  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.upload_asset <arquivo> [caminho/remoto]")
        return 2
    local = Path(sys.argv[1])
    remote = sys.argv[2] if len(sys.argv) > 2 else None

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        print("SUPABASE_URL/SUPABASE_SERVICE_KEY ausentes no .env")
        return 1

    host = SupabaseAssetHost(
        url=settings.supabase_url,
        service_key=settings.supabase_service_key,
        bucket=settings.supabase_bucket,
    )
    try:
        host.ensure_bucket()
        url = host.upload_file(local, remote_path=remote)
    except SupabaseUnavailable as exc:
        print(f"INDISPONÍVEL: {exc}")
        return 1
    except SupabaseError as exc:
        print(f"ERRO: {exc}")
        return 1
    print(f"OK: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
