from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .deps import ctx
from ..errors import NotFoundError, UserError
from ..validation import ENGINE_ID_RE, VOICE_ID_RE

router = APIRouter(prefix="/api")
_PREVIEW_RE = re.compile(r"^[a-z0-9_-]{1,32}-[a-z]{2}_[a-z0-9]{1,30}\.wav$")


@router.get("/voices")
def list_voices(request: Request):
    return ctx(request).voices.catalogue()


@router.post("/voices/{engine_id}/{voice_id}/preview")
def make_preview(engine_id: str, voice_id: str, request: Request):
    if not ENGINE_ID_RE.match(engine_id) or not VOICE_ID_RE.match(voice_id):
        raise UserError("Invalid voice.")
    name = ctx(request).voices.preview(engine_id, voice_id)
    return {"url": f"/api/previews/{name}"}


@router.get("/previews/{name}")
def get_preview(name: str, request: Request):
    if not _PREVIEW_RE.match(name):
        raise NotFoundError("Preview not found.")
    path = ctx(request).paths.preview_cache / name
    if not path.is_file():
        raise NotFoundError("Preview not found.")
    return FileResponse(path, media_type="audio/wav")
