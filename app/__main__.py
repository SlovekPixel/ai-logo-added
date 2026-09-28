"""Entry point: `python -m app` or `python -m app unlock`."""

from __future__ import annotations

import os
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "unlock":
        from app.auth import unlock
        from app.config import ensure_dirs

        ensure_dirs()
        unlock()
        print("Сайт разблокирован. Счётчик ошибок сброшен.")
        return

    import uvicorn

    from app.auth import validate_access_code_config
    from app.config import ensure_dirs

    ensure_dirs()
    err = validate_access_code_config()
    if err:
        print(f"WARNING: {err}")
        print("Скопируйте .env.example в .env и задайте ACCESS_CODE (30 символов).")

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        # Large folder uploads
        timeout_keep_alive=75,
    )


if __name__ == "__main__":
    main()
