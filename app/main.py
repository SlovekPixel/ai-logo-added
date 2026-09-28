from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import attempt_login, is_locked, load_state, verify_session_token
from app.config import (
    ALLOWED_EXTENSIONS,
    COOKIE_SECURE,
    JOBS_DIR,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ROOT,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    ensure_dirs,
)
from app.images import (
    REF_LEFT,
    REF_LOGO_H,
    REF_LOGO_W,
    REF_PHOTO_H,
    REF_TOP,
    SVG_PILL_X,
    default_logo_path,
)
from app.jobs import job_manager

app = FastAPI(title="Logo Overlay")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    ensure_dirs()
    job_manager.cleanup_expired()
    job_manager.start_cleanup_loop()


def get_session(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if verify_session_token(token):
        return token
    return None


def require_session(request: Request) -> str:
    token = get_session(request)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return token


@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if get_session(request) and not is_locked():
        return RedirectResponse("/app", status_code=302)
    state = load_state()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "locked": bool(state.get("locked")),
            "fail_count": int(state.get("fail_count", 0)),
        },
    )


@app.post("/api/login")
async def api_login(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str(body.get("code", "")).strip()

    result = attempt_login(code)
    response = JSONResponse(
        {
            "ok": result["ok"],
            "locked": result["locked"],
            "remaining": result["remaining"],
            "message": result["message"],
        }
    )
    if result["ok"] and result.get("token"):
        response.set_cookie(
            key=SESSION_COOKIE,
            value=result["token"],
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=SESSION_MAX_AGE,
            path="/",
        )
    return response


@app.post("/api/logout")
async def api_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request) -> HTMLResponse:
    if is_locked():
        return RedirectResponse("/", status_code=302)
    if not get_session(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "app.html")


@app.get("/api/logo-layout")
async def api_logo_layout(session: str = Depends(require_session)) -> JSONResponse:
    """Layout constants for the UI preview — single source: app/images.py."""
    return JSONResponse(
        {
            "refPhotoH": REF_PHOTO_H,
            "refLogoW": REF_LOGO_W,
            "refLogoH": REF_LOGO_H,
            "refTop": REF_TOP,
            "refLeft": REF_LEFT,
            "svgPillX": SVG_PILL_X,
        }
    )


def _safe_filename(name: str) -> str:
    return Path(name).name.replace("\x00", "")


def _is_allowed_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@app.post("/api/generate")
async def api_generate(
    request: Request,
    session: str = Depends(require_session),
    photos: list[UploadFile] = File(...),
) -> JSONResponse:
    if is_locked():
        raise HTTPException(status_code=403, detail="Сайт заблокирован")

    if job_manager.is_busy():
        return JSONResponse(
            {
                "ok": False,
                "busy": True,
                "message": "Сервер занят. Подождите, пока завершится текущая генерация.",
            },
            status_code=409,
        )

    try:
        logo_path = default_logo_path()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Дефолтный логотип недоступен: {exc}") from exc

    image_uploads = [
        f for f in photos if f.filename and _is_allowed_image(_safe_filename(f.filename))
    ]
    if not image_uploads:
        raise HTTPException(status_code=400, detail="Нет изображений в выбранной папке")
    if len(image_uploads) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Слишком много файлов (макс. {MAX_FILES})",
        )

    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    input_dir = job_dir / "input"
    photos_dir = input_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    saved_photos: list[Path] = []
    acquired = False

    try:
        used_names: set[str] = set()
        for idx, upload in enumerate(image_uploads):
            raw_name = _safe_filename(upload.filename or f"photo_{idx}.jpg")
            name = raw_name
            if name in used_names:
                stem = Path(raw_name).stem
                suffix = Path(raw_name).suffix
                name = f"{stem}_{idx}{suffix}"
            used_names.add(name)

            data = await upload.read()
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(status_code=400, detail=f"Файл {name} слишком большой")
            total_bytes += len(data)
            if total_bytes > MAX_TOTAL_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Суммарный размер превышает {MAX_TOTAL_BYTES // (1024 * 1024)} МБ",
                )
            dest = photos_dir / name
            dest.write_bytes(data)
            saved_photos.append(dest)

        acquired = await job_manager.try_acquire()
        if not acquired:
            shutil.rmtree(job_dir, ignore_errors=True)
            return JSONResponse(
                {
                    "ok": False,
                    "busy": True,
                    "message": "Сервер занят. Подождите, пока завершится текущая генерация.",
                },
                status_code=409,
            )

        job = job_manager.register_and_run(
            job_id=job_id,
            session_id=session,
            logo_path=logo_path,
            photos=saved_photos,
            input_dir=input_dir,
            output_dir=job_dir / "output",
            job_dir=job_dir,
        )
        return JSONResponse({"ok": True, "job_id": job.id})
    except HTTPException:
        if acquired:
            await job_manager.release()
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as exc:
        if acquired:
            await job_manager.release()
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}")
async def api_job_status(
    job_id: str,
    session: str = Depends(require_session),
) -> JSONResponse:
    job = job_manager.get(job_id)
    if not job or job.session_id != session:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return JSONResponse(job.to_dict())


@app.get("/api/jobs/{job_id}/download")
async def api_job_download(
    job_id: str,
    session: str = Depends(require_session),
) -> FileResponse:
    job = job_manager.get(job_id)
    if not job or job.session_id != session:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if job.status != "done" or not job.zip_path or not job.zip_path.exists():
        raise HTTPException(status_code=404, detail="Архив ещё не готов или удалён")
    return FileResponse(
        path=str(job.zip_path),
        filename="photos_with_logo.zip",
        media_type="application/zip",
    )


@app.get("/api/status")
async def api_status(request: Request) -> JSONResponse:
    state = load_state()
    return JSONResponse(
        {
            "locked": bool(state.get("locked")),
            "authenticated": bool(get_session(request)),
            "busy": job_manager.is_busy(),
        }
    )
