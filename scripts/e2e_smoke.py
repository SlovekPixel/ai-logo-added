"""Quick end-to-end smoke test against a running server."""
from __future__ import annotations

import io
import json
import time
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

from PIL import Image

from app.config import ACCESS_CODE

BASE = "http://127.0.0.1:8000"


def main() -> None:
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))

    assert opener.open(f"{BASE}/").status == 200

    req = Request(
        f"{BASE}/api/login",
        data=json.dumps({"code": "wrongwrongwrongwrongwrongwrong"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    print("wrong", json.loads(opener.open(req).read()))

    req = Request(
        f"{BASE}/api/login",
        data=json.dumps({"code": ACCESS_CODE}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(opener.open(req).read())
    print("login", resp)
    assert resp["ok"]

    assert opener.open(f"{BASE}/app").status == 200
    print("app page ok")

    boundary = "----BoundTest123"
    photos: list[tuple[str, bytes]] = []
    for i in range(3):
        b = io.BytesIO()
        Image.new("RGB", (150 + i * 10, 200 + i * 10), (30 * i, 50, 90)).save(
            b, format="JPEG", quality=90
        )
        photos.append((f"photo{i}.jpg", b.getvalue()))

    parts: list[bytes] = []

    def add_file(name: str, filename: str, data: bytes, ctype: str) -> None:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        parts.append(header + data + b"\r\n")

    for fn, data in photos:
        add_file("photos", fn, data, "image/jpeg")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()

    req = Request(
        f"{BASE}/api/generate",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = json.loads(opener.open(req).read())
    print("generate", resp)
    assert resp["ok"]
    job_id = resp["job_id"]

    for _ in range(40):
        st = json.loads(opener.open(f"{BASE}/api/jobs/{job_id}").read())
        print("status", st)
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise SystemExit(f"job error: {st}")
        time.sleep(0.3)
    else:
        raise SystemExit("timeout")

    data = opener.open(f"{BASE}/api/jobs/{job_id}/download").read()
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    print("zip", names, "size", len(data))
    assert len(names) == 3

    job_dir = Path("data/jobs") / job_id
    assert not (job_dir / "input").exists(), "input should be deleted"
    assert (job_dir / "result.zip").exists()
    print("E2E OK")


if __name__ == "__main__":
    main()
