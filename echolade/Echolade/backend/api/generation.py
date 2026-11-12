from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .deps import ctx
from ..engines.base import EngineError
from ..errors import NotFoundError, UserError
from ..validation import ID_RE, JobRequest, RenameRequest, safe_filename

router = APIRouter(prefix="/api")


def _job_id(value: str) -> str:
    if not ID_RE.match(value):
        raise NotFoundError("That job no longer exists.")
    return value


@router.post("/jobs", status_code=202)
def create_job(req: JobRequest, request: Request):
    c = ctx(request)
    try:
        engine = c.engines.get(req.engine)
    except EngineError as exc:
        raise UserError(str(exc)) from exc
    ok, reason = engine.availability()
    if not ok:
        raise UserError(reason or "The speech engine is not available.")
    if req.delivery.voice not in {v.id for v in engine.list_voices()}:
        raise UserError("Choose a voice from the voice list.")
    job = c.jobs.submit(req, c.runtime())
    c.settings.remember_voice(req.delivery.voice)
    return job.to_public()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    return ctx(request).jobs.get(_job_id(job_id)).to_public()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    return ctx(request).jobs.cancel(_job_id(job_id)).to_public()


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, request: Request):
    return ctx(request).jobs.retry(_job_id(job_id)).to_public()


@router.post("/jobs/{job_id}/finalize")
def finalize_job(job_id: str, request: Request):
    return ctx(request).jobs.finalize(_job_id(job_id)).to_public()


@router.get("/jobs/{job_id}/segments/{index}")
def get_segment(job_id: str, index: int, request: Request):
    job = ctx(request).jobs.get(_job_id(job_id))
    with job.lock:
        ok = 0 <= index < len(job.chunks) and job.chunks[index].status == "done"
    path = job.chunk_path(index) if ok else None
    if not ok or not path.is_file():
        raise NotFoundError("That segment is not ready.")
    return FileResponse(path, media_type="audio/wav")


# ---------------------------------------------------------------- history
@router.get("/history")
def list_history(request: Request):
    return {"items": ctx(request).history.list()}


@router.patch("/history/{entry_id}")
def rename_history(entry_id: str, body: RenameRequest, request: Request):
    entry = ctx(request).history.rename(_job_id(entry_id), body.name)
    if not entry:
        raise NotFoundError("That item no longer exists.")
    return entry


@router.delete("/history/{entry_id}")
def delete_history(entry_id: str, request: Request):
    if not ctx(request).history.delete(_job_id(entry_id)):
        raise NotFoundError("That item no longer exists.")
    return {"ok": True}


def _file_response(entry_id: str, request: Request, attachment: bool):
    c = ctx(request)
    entry = c.history.get(_job_id(entry_id))
    if not entry:
        raise NotFoundError("That item no longer exists.")
    path = c.history.file_path(entry)
    if not path or not path.is_file():
        raise NotFoundError("The audio file is no longer on disk.")
    media = "audio/mpeg" if entry["format"] == "mp3" else "audio/wav"
    download_name = f"{safe_filename(entry['name'])}.{entry['format']}"
    return FileResponse(path, media_type=media, filename=download_name,
                        content_disposition_type="attachment" if attachment else "inline")


@router.get("/history/{entry_id}/audio")
def stream_history(entry_id: str, request: Request):
    return _file_response(entry_id, request, attachment=False)


@router.get("/history/{entry_id}/download")
def download_history(entry_id: str, request: Request):
    return _file_response(entry_id, request, attachment=True)


