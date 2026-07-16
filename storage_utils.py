"""
storage_utils.py — File storage abstraction layer.

When SUPABASE_URL + SUPABASE_KEY are set, files are stored in Supabase Storage.
Otherwise, files fall back to the local 'static/uploads/' directory (dev mode).

Bucket name: face-uploads  (must be PUBLIC in Supabase Storage)
"""

import os
import uuid
from pathlib import Path

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
BUCKET = 'face-uploads'

USE_SUPABASE_STORAGE = bool(SUPABASE_URL and SUPABASE_KEY)

# Local fallback directory
LOCAL_UPLOAD_DIR = Path(__file__).parent / 'static' / 'uploads'
LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_supabase_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_face_image(file_bytes: bytes, filename: str) -> str:
    """
    Upload a face image and return the accessible URL / path.

    - Supabase Storage: returns the public URL
    - Local fallback: saves to static/uploads/, returns the relative path
    """
    if USE_SUPABASE_STORAGE:
        client = _get_supabase_client()
        # Upsert so re-uploads for the same user overwrite the old file
        client.storage.from_(BUCKET).upload(
            filename,
            file_bytes,
            file_options={
                'content-type': 'image/jpeg',
                'upsert': 'true',
            }
        )
        # Return the public URL
        return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"
    else:
        # Local filesystem fallback
        dest = LOCAL_UPLOAD_DIR / filename
        dest.write_bytes(file_bytes)
        return str(dest)


def delete_face_image(path_or_url: str):
    """Delete a face image (best-effort — does not raise on failure)."""
    try:
        if USE_SUPABASE_STORAGE:
            # Extract the filename from the public URL
            prefix = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/"
            if path_or_url.startswith(prefix):
                filename = path_or_url[len(prefix):]
                _get_supabase_client().storage.from_(BUCKET).remove([filename])
        else:
            p = Path(path_or_url)
            if p.exists():
                p.unlink()
    except Exception as exc:
        print(f"[storage_utils] delete warning: {exc}")


def get_face_image_url(path_or_url: str) -> str:
    """
    Return a browser-accessible URL for a face image path/URL.
    - Already a URL (Supabase) → return as-is
    - Local path → convert to /static/uploads/<filename>
    """
    if path_or_url and path_or_url.startswith('http'):
        return path_or_url
    if path_or_url:
        filename = Path(path_or_url).name
        return f"/static/uploads/{filename}"
    return ''


def face_image_filename(user_id: int) -> str:
    """Return the standard filename for a user's face image."""
    return f"user_{user_id}_captured-face.jpg"
