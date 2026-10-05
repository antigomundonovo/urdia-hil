"""Tests for the backup verification helpers."""

import zipfile
from pathlib import Path

from scripts.backup import verify_backup


def test_verify_backup_accepts_pg_dump_sql(tmp_path: Path):
    dump = tmp_path / "db.sql"
    dump.write_text(
        "-- Dumped from PostgreSQL\nCREATE TABLE public.example (id integer);\n",
        encoding="utf-8",
    )

    assert verify_backup(str(dump)) == 0


def test_verify_backup_accepts_non_empty_zip(tmp_path: Path):
    archive_path = tmp_path / "assets.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("assets/originals/sample.txt", "hello world")

    assert verify_backup(str(archive_path)) == 0


def test_verify_backup_rejects_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.sql"
    empty.write_text("", encoding="utf-8")

    assert verify_backup(str(empty)) == 1
