"""Supabase Storage : envoi des previews / posters (bucket privé `previews`)."""

from __future__ import annotations

from pathlib import Path

import httpx

from ..config import Settings


def upload_preview(settings: Settings, path: Path, object_path: str, content_type: str) -> str:
    if settings.dry_run:
        return object_path
    url = f"{settings.supabase_url}/storage/v1/object/previews/{object_path}"
    r = httpx.post(
        url,
        content=path.read_bytes(),
        timeout=120,
        headers={
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )
    r.raise_for_status()
    return object_path
