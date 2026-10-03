"""Backup / restore / verify (Doc 07: "Provide scripts: backup_database,
restore_database, backup_assets, verify_backup").

Usage:
    python -m scripts.backup database            # pg_dump via docker container
    python -m scripts.backup assets              # zip originals + derived
    python -m scripts.backup restore FILE.sql    # restore database from file
    python -m scripts.backup verify FILE         # sanity-check a backup

Backups include database and essential assets, never secrets (Doc 00 §25).
Files land in ./backups/ (gitignored).
"""

import argparse
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = "urdia-postgres"
BACKUP_DIR = Path("backups")
ASSET_ROOTS = ("assets/originals", "assets/derived")


def backup_database() -> int:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"db-{stamp}.sql"
    try:
        dump = subprocess.run(
            ["docker", "exec", CONTAINER, "pg_dump", "-U", "urdia", "urdia"],
            capture_output=True, check=True,
        )
    except FileNotFoundError:
        print("docker não encontrado — ligue o Docker Desktop", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"pg_dump falhou: {exc.stderr.decode(errors='replace')[:300]}", file=sys.stderr)
        return 1
    target.write_bytes(dump.stdout)
    print(f"backup do banco: {target} ({len(dump.stdout)} bytes)")
    return 0


def backup_assets() -> int:
    BACKUP_DIR.mkdir(exist_ok=True, parents=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"assets-{stamp}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for root in ASSET_ROOTS:
            base = Path(root)
            if not base.exists():
                continue
            for file in sorted(base.rglob("*")):
                if file.is_file():
                    arcname = file.relative_to(Path.cwd()).as_posix()
                    archive.write(file, arcname)
                    count += 1
    print(f"backup de assets: {target} ({count} arquivos)")
    return 0


def restore_database(file: str) -> int:
    path = Path(file)
    if not path.exists():
        print(f"arquivo não encontrado: {path}", file=sys.stderr)
        return 1
    print(f"restaurando {path} no container {CONTAINER}…")
    print("ATENÇÃO: isso aplica o SQL por cima do banco atual (Doc 07: stop workers → backup → restore).")
    try:
        result = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", "urdia", "-d", "urdia", "-q"],
            stdin=path.open("rb"), capture_output=True,
        )
    except FileNotFoundError:
        print("docker não encontrado — ligue o Docker Desktop", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(result.stderr.decode(errors="replace")[:500], file=sys.stderr)
        return 1
    print("restaurado. Rode `alembic upgrade head` e um health check (Doc 07 recovery).")
    return 0


def verify_backup(file: str) -> int:
    path = Path(file)
    if not path.exists() or path.stat().st_size == 0:
        print(f"FALHA: {path} não existe ou está vazio", file=sys.stderr)
        return 1
    if path.suffix == ".sql":
        head = path.read_text(errors="replace")[:20000]
        ok = any(marker in head for marker in ("PostgreSQL database dump", "CREATE TABLE", "COPY ", "-- Dumped"))
        print(f"{'OK' if ok else 'FALHA'}: dump SQL {'contém' if ok else 'NÃO contém'} estrutura esperada")
        return 0 if ok else 1
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            members = archive.namelist()
        ok = bad is None and bool(members)
        print(f"{'OK' if ok else 'FALHA'}: zip {'integridade ok' if ok else f'com defeito: {bad}'}")
        return 0 if ok else 1
    print("tipo de backup desconhecido", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="URDIA HIL backups (Doc 07)")
    parser.add_argument("command", choices=["database", "assets", "restore", "verify"])
    parser.add_argument("file", nargs="?", help="arquivo para restore/verify")
    args = parser.parse_args()
    if args.command == "database":
        return backup_database()
    if args.command == "assets":
        return backup_assets()
    if args.command == "restore":
        if not args.file:
            parser.error("restore precisa do arquivo")
        return restore_database(args.file)
    if not args.file:
        parser.error("verify precisa do arquivo")
    return verify_backup(args.file)


if __name__ == "__main__":
    sys.exit(main())
