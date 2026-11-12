from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import ValidationError

from .deps import ctx
from ..errors import UserError
from ..validation import SettingsPatch

router = APIRouter(prefix="/api")


@router.get("/settings")
def get_settings(request: Request):
    return ctx(request).settings.get().model_dump()


@router.patch("/settings")
def patch_settings(patch: SettingsPatch, request: Request):
    c = ctx(request)
    try:
        updated = c.settings.update(patch.model_dump(exclude_unset=True))
    except ValidationError as exc:
        first = exc.errors()[0]
        raise UserError(f"Invalid setting “{first['loc'][-1]}”: {first['msg']}") from exc
    return updated.model_dump()
