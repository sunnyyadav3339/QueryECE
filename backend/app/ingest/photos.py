"""Local copies of faculty photos.

The faculty pages link photos on channeli.in, which is reachable only from the
IIT Roorkee network. Saving them under data/photos/ lets the app show photos
anywhere (off campus, or once deployed). Run on the campus network or VPN:

    python -m app.ingest.photos
"""

import io
import json
import logging

import httpx
from PIL import Image, ImageOps

from app.config import PHOTOS_DIR
from app.db.database import SessionLocal
from app.db.models import Faculty
from app.ingest.crawler import USER_AGENT

log = logging.getLogger(__name__)

MANIFEST = PHOTOS_DIR / "manifest.json"  # {faculty_id: source url}, to refetch only changed photos
MAX_BYTES = 10_000_000  # source size limit; saved copies are small thumbnails
THUMB_PX = 400  # shown at <=96 CSS px, so 400 px stays sharp on high-DPI screens
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def photo_path(faculty_id: int):
    """The saved photo for a faculty member, or None."""
    # .jpg first: every saved photo is a JPEG thumbnail now, so this is usually one
    # file check (each check costs ~90 ms on a Docker-on-Windows bind mount).
    for ext in (".jpg", ".png", ".webp", ".gif"):
        p = PHOTOS_DIR / f"{faculty_id}{ext}"
        if p.exists():
            return p
    return None


def local_photo_url(faculty_id: int) -> str | None:
    """API path of the saved photo (versioned by file time so browsers refetch changes), or None."""
    p = photo_path(faculty_id)
    return f"/api/faculty/{faculty_id}/photo?v={int(p.stat().st_mtime)}" if p else None


def _sniff(data: bytes) -> str | None:
    """File extension from the image's magic bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def _thumbnail(data: bytes) -> bytes:
    """Shrink to a JPEG thumbnail; originals are up to ~1 MB for a 96 px avatar."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    img.thumbnail((THUMB_PX, THUMB_PX))
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def _load_manifest() -> dict[str, str]:
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return {}


def sync_photos(faculty: list[Faculty]) -> dict:
    """Download photos that are missing or whose source URL changed.

    Off campus channeli.in doesn't answer, so the first connection failure
    stops the run instead of waiting on every photo; saved photos are kept.
    """
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    stats = {"downloaded": 0, "kept": 0, "failed": 0, "unreachable": False}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(15, connect=6),
                      follow_redirects=True) as client:
        for f in faculty:
            if not f.image_url:
                continue
            if manifest.get(str(f.id)) == f.image_url and photo_path(f.id):
                stats["kept"] += 1
                continue
            try:
                resp = client.get(f.image_url)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                log.warning("photo host unreachable (needs the IITR network); keeping saved photos")
                stats["unreachable"] = True
                break
            except httpx.HTTPError as exc:
                log.warning("photo for %s failed: %s", f.name, exc)
                stats["failed"] += 1
                continue
            # channeli serves extension-less files as application/octet-stream, so
            # trust the file's signature first and the header second.
            ext = _sniff(resp.content) or EXTENSIONS.get(resp.headers.get("content-type", "").split(";")[0].strip())
            if resp.status_code != 200 or not ext or not 0 < len(resp.content) <= MAX_BYTES:
                stats["failed"] += 1
                continue
            try:
                thumb = _thumbnail(resp.content)
            except OSError:  # not a decodable image
                stats["failed"] += 1
                continue
            old = photo_path(f.id)
            if old:
                old.unlink()
            (PHOTOS_DIR / f"{f.id}.jpg").write_bytes(thumb)
            manifest[str(f.id)] = f.image_url
            stats["downloaded"] += 1
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    log.info("faculty photos: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        print(sync_photos(db.query(Faculty).all()))
