from __future__ import annotations

import asyncio
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import JOBS_DIR, ZIP_TTL_MINUTES, ensure_dirs
from app.images import overlay_logo


@dataclass
class Job:
    id: str
    session_id: str
    status: str = "queued"  # queued | running | done | error
    message: str = ""
    total: int = 0
    done: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    zip_path: Path | None = None
    zip_expires_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "total": self.total,
            "done": self.done,
            "error": self.error,
            "download_ready": self.status == "done" and self.zip_path is not None,
            "zip_expires_at": self.zip_expires_at,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._busy = False
        self._cleanup_task: asyncio.Task | None = None

    def start_cleanup_loop(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                self.cleanup_expired()
            except Exception:
                pass
            await asyncio.sleep(60)

    def cleanup_expired(self) -> None:
        ensure_dirs()
        now = time.time()
        ttl_seconds = ZIP_TTL_MINUTES * 60

        expired_ids: list[str] = []
        for job_id, job in list(self._jobs.items()):
            if job.zip_expires_at and now >= job.zip_expires_at:
                self._remove_job_dir(job_id)
                expired_ids.append(job_id)
            elif job.status == "error" and (now - job.created_at) > ttl_seconds:
                self._remove_job_dir(job_id)
                expired_ids.append(job_id)
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)

        if JOBS_DIR.exists():
            for path in JOBS_DIR.iterdir():
                if not path.is_dir():
                    continue
                job_id = path.name
                if job_id in self._jobs:
                    continue
                zip_file = path / "result.zip"
                ref = zip_file if zip_file.exists() else path
                age = now - ref.stat().st_mtime
                if age > ttl_seconds:
                    shutil.rmtree(path, ignore_errors=True)

    def _remove_job_dir(self, job_id: str) -> None:
        path = JOBS_DIR / job_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def is_busy(self) -> bool:
        return self._busy

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    async def release(self) -> None:
        async with self._lock:
            self._busy = False

    def register_and_run(
        self,
        *,
        job_id: str,
        session_id: str,
        logo_path: Path,
        photos: list[Path],
        input_dir: Path,
        output_dir: Path,
        job_dir: Path,
    ) -> Job:
        """Caller must have already acquired the busy lock via try_acquire()."""
        output_dir.mkdir(parents=True, exist_ok=True)
        job = Job(
            id=job_id,
            session_id=session_id,
            status="running",
            message="Обработка…",
            total=len(photos),
            done=0,
        )
        self._jobs[job_id] = job
        asyncio.create_task(
            self._run_job(
                job=job,
                logo_path=logo_path,
                photos=photos,
                input_dir=input_dir,
                output_dir=output_dir,
                job_dir=job_dir,
            )
        )
        return job

    async def _run_job(
        self,
        *,
        job: Job,
        logo_path: Path,
        photos: list[Path],
        input_dir: Path,
        output_dir: Path,
        job_dir: Path,
    ) -> None:
        try:
            for i, photo in enumerate(photos):
                out_name = photo.name
                out_path = output_dir / out_name
                if out_path.exists():
                    out_path = output_dir / f"{photo.stem}_{i}{photo.suffix}"

                await asyncio.to_thread(
                    overlay_logo,
                    photo,
                    logo_path,
                    out_path,
                )
                job.done = i + 1
                job.message = f"Обработано {job.done} из {job.total}"

            zip_path = job_dir / "result.zip"
            await asyncio.to_thread(self._make_zip, output_dir, zip_path)

            # Delete user uploads and intermediate outputs immediately
            for folder in (input_dir, output_dir):
                if folder.exists():
                    shutil.rmtree(folder, ignore_errors=True)

            job.zip_path = zip_path
            job.zip_expires_at = time.time() + ZIP_TTL_MINUTES * 60
            job.status = "done"
            job.finished_at = time.time()
            job.message = "Готово"
        except Exception as exc:
            job.status = "error"
            job.error = str(exc)
            job.message = f"Ошибка: {exc}"
            job.finished_at = time.time()
            if input_dir.exists():
                shutil.rmtree(input_dir, ignore_errors=True)
        finally:
            await self.release()

    @staticmethod
    def _make_zip(output_dir: Path, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(output_dir.iterdir()):
                if file.is_file():
                    zf.write(file, arcname=file.name)


job_manager = JobManager()
