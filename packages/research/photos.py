"""Photo story + visual intelligence (Doc 17 step 19; Doc 10).

Pipeline: import → file validation → SHA-256 → perceptual hash → metadata →
story. Identity rule (Doc 10): visual similarity never proves identity —
hashes are used for DUPLICATE detection and origin LEADS, nothing more.

Upload security (Doc 08): type allowlist, size limit, magic bytes check,
system-generated storage paths (never user filenames), non-executable
storage, never executing downloaded files.
"""

import hashlib
import uuid as uuidlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.assets import Asset
from packages.domain.enums import VisualClassification
from packages.governance.audit import append_audit
from packages.shared.execution_context import ExecutionContext

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
MAX_UPLOAD_BYTES = 25_000_000

# magic bytes per allowed type (Doc 08: MIME + magic bytes)
MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # RIFF....WEBP checked below
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)


class UploadRejected(Exception):
    """Fail closed: any validation failure rejects the file outright."""


@dataclass
class PhotoImport:
    asset: Asset
    file_hash: str
    perceptual_hash: str | None
    duplicate_of: uuidlib.UUID | None
    mime: str


def detect_mime(content: bytes) -> str | None:
    for prefix, mime in MAGIC:
        if content.startswith(prefix):
            if mime == "image/webp":
                return "image/webp" if content[8:12] == b"WEBP" else None
            return mime
    return None


def perceptual_hash(content: bytes, size: int = 16) -> str | None:
    """Average hash (aHash) via Pillow — 64-bit hex. Deterministic, standard
    algorithm; catches re-encodings/resizes that exact SHA-256 misses. If the
    bytes cannot be decoded as an image, returns None (never invents a hash)."""
    import io

    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            gray = image.convert("L").resize((size, size))
        pixels = list(gray.getdata())
        average = sum(pixels) / len(pixels)
        bits = "".join("1" if p > average else "0" for p in pixels)
        return f"{int(bits, 2):016x}"
    except Exception:
        return None


class PhotoService:
    def __init__(self, session: Session, asset_root: Path) -> None:
        self.session = session
        self.asset_root = Path(asset_root)
        (self.asset_root / "originals").mkdir(parents=True, exist_ok=True)
        (self.asset_root / "temp").mkdir(parents=True, exist_ok=True)

    def import_photo(
        self,
        ctx: ExecutionContext,
        *,
        content: bytes,
        original_filename: str | None = None,
        page_url: str | None = None,
        institution: str | None = None,
        creator: str | None = None,
        creation_date: str | None = None,
    ) -> PhotoImport:
        # 1. file validation (Doc 08): size, extension allowlist, magic bytes
        if not content:
            raise UploadRejected("empty file")
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadRejected("file exceeds size limit")
        ext = Path(original_filename or "").suffix.lower()
        if original_filename and ext not in ALLOWED_EXTENSIONS:
            raise UploadRejected(f"extension not allowed: {ext}")
        mime = detect_mime(content)
        if mime not in ALLOWED_MIME:
            raise UploadRejected("content is not an allowed image type")

        # 2. hashes
        file_hash = hashlib.sha256(content).hexdigest()
        phash = perceptual_hash(content)

        # 3. duplicate detection (Doc 10: file hash first — exact copies)
        existing = self.session.scalars(
            select(Asset)
            .where(
                Asset.workspace_id == ctx.workspace_id,
                Asset.file_hash == file_hash,
                Asset.status == "ACTIVE",
            )
            .limit(1)
        ).first()
        duplicate_of = existing.id if existing is not None else None

        # 4. persist under a system-generated path (never the user filename)
        asset_id = uuidlib.uuid4()
        relative = f"originals/{ctx.workspace_id}/{asset_id}{ext or '.bin'}"
        target = self.asset_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        asset = Asset(
            id=asset_id,
            workspace_id=ctx.workspace_id,
            profile_id=ctx.profile_id,
            asset_type="PHOTO",
            page_url=page_url,
            institution=institution,
            creator=creator,
            creation_date=creation_date,
            retrieval_date=datetime.now(UTC),
            file_hash=file_hash,
            perceptual_hash=phash,
            visual_classification=VisualClassification.ORIGINAL_AS_RETRIEVED.value,
            status="ACTIVE",
            storage_path=relative,
        )
        self.session.add(asset)
        self.session.flush()

        append_audit(
            self.session,
            ctx=ctx,
            action="ASSET_IMPORTED",
            entity_type="asset",
            entity_id=asset.id,
            new_state="DUPLICATE" if duplicate_of else "IMPORTED",
            metadata={
                "mime": mime,
                "bytes": len(content),
                "duplicate_of": str(duplicate_of) if duplicate_of else None,
            },
        )
        return PhotoImport(asset, file_hash, phash, duplicate_of, mime)

    def find_similar(self, ctx: ExecutionContext, perceptual_hash: str) -> list[Asset]:
        """Origin LEADS only (Doc 10 identity rule) — similarity never proves
        identity; callers must confirm with provenance/context/evidence."""
        return list(
            self.session.scalars(
                select(Asset).where(
                    Asset.workspace_id == ctx.workspace_id,
                    Asset.perceptual_hash == perceptual_hash,
                    Asset.status == "ACTIVE",
                )
            )
        )

    def get_scoped(self, asset_id, workspace_id) -> Asset | None:
        asset = self.session.get(Asset, asset_id)
        if asset is None or asset.workspace_id != workspace_id:
            return None
        return asset
