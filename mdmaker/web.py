"""Local browser UI for EbaratNeshan. Binds to 127.0.0.1 only; no internet."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .cli import convert_one
from .settings import ROOT, SUPPORTED_SUFFIXES, load_config

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_UPLOAD = 80 * 1024 * 1024
WEBAPP = Path(__file__).resolve().parent / "webapp"
UPLOADS = ROOT / "_uploads"
SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\u0600-\u06FF ]+")
CONVERT_LOCK = threading.Lock()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EbaratNeshan local web page")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    port = _free_port(args.port)
    server = ThreadingHTTPServer((HOST, port), Handler)
    url = f"http://{HOST}:{port}/"
    print(f"EbaratNeshan page: {url}", flush=True)
    print("Leave this window open. Close it to stop the page.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
    return 0


def _free_port(preferred: int) -> int:
    import socket

    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free local port found")


class Handler(BaseHTTPRequestHandler):
    server_version = "EbaratNeshanWeb/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(WEBAPP / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/health":
            self._json({"ok": True})
            return
        self._send_status(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/convert":
            self._convert()
            return
        if parsed.path == "/api/open-folder":
            self._open_folder()
            return
        self._send_status(404, "Not found")

    def _convert(self) -> None:
        try:
            fields, files = _parse_multipart(self)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)
            return
        upload = files.get("file")
        if not upload:
            self._json({"ok": False, "error": "Choose a PDF or DOCX file."}, status=400)
            return
        filename, payload = upload
        name = _safe_filename(filename)
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            self._json({"ok": False, "error": "Only .pdf and .docx are supported."}, status=400)
            return
        if len(payload) > MAX_UPLOAD:
            self._json({"ok": False, "error": "File is larger than 80 MB."}, status=400)
            return
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dest = _unique_path(UPLOADS / name)
        dest.write_bytes(payload)

        cfg = load_config()
        purpose = (fields.get("purpose") or "llm").strip().lower()
        if purpose not in {"llm", "reading", "all"}:
            purpose = "llm"
        cfg["purpose"] = purpose
        cfg["purposes"] = ("llm", "reading") if purpose == "all" else (purpose,)
        cfg["overwrite"] = _flag(fields.get("overwrite"), False)
        cfg["table_images"] = _flag(fields.get("table_images"), True)
        cfg["figure_images"] = _flag(fields.get("figure_images"), True)
        cfg["persian_digits"] = _flag(fields.get("persian_digits"), False)
        cfg["split_llm"] = _flag(fields.get("split_llm"), False)

        try:
            with CONVERT_LOCK:
                result = convert_one(dest, cfg, cfg["purposes"], quiet=True)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, status=500)
            return
        self._json({"ok": True, "file": dest.name, **result})

    def _open_folder(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body.decode("utf-8") or "{}")
            folder = Path(str(data.get("folder") or ""))
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "error": "Bad request."}, status=400)
            return
        if not _is_under(folder, Path(load_config()["output_root"])):
            self._json({"ok": False, "error": "Folder is outside output."}, status=400)
            return
        if not folder.is_dir():
            self._json({"ok": False, "error": "Folder not found."}, status=404)
            return
        _reveal_folder(folder)
        self._json({"ok": True})

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_status(404, "Not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_status(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _parse_multipart(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("Expected a file upload.")
    match = re.search(r'boundary=("?)([^";]+)\1', content_type, re.I)
    if not match:
        raise ValueError("Missing upload boundary.")
    boundary = match.group(2).encode("ascii", errors="replace")
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        raise ValueError("Empty upload.")
    if length > MAX_UPLOAD + 1024 * 1024:
        raise ValueError("File is larger than 80 MB.")
    body = handler.rfile.read(length)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for raw in body.split(b"--" + boundary):
        if not raw or raw in {b"--", b"--\r\n", b"--\n"}:
            continue
        if raw.startswith(b"--"):
            continue
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        elif raw.startswith(b"\n"):
            raw = raw[1:]
        header_blob, sep, payload = raw.partition(b"\r\n\r\n")
        if not sep:
            header_blob, sep, payload = raw.partition(b"\n\n")
        if not sep:
            continue
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        elif payload.endswith(b"\n"):
            payload = payload[:-1]
        headers = {}
        for line in header_blob.decode("utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        disp = headers.get("content-disposition", "")
        name_m = re.search(r'name="([^"]+)"', disp)
        file_m = re.search(r'filename="([^"]*)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        if file_m and file_m.group(1):
            files[name] = (file_m.group(1), payload)
        else:
            fields[name] = payload.decode("utf-8", errors="replace")
    return fields, files


def _safe_filename(name: str) -> str:
    raw = Path(name.replace("\\", "/")).name
    cleaned = SAFE_NAME.sub("_", raw).strip(" .")
    return cleaned or "document.pdf"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.with_name(f"{stem}({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _reveal_folder(folder: Path) -> None:
    folder = str(folder.resolve())
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", folder])
        return
    subprocess.Popen(["xdg-open", folder])


if __name__ == "__main__":
    raise SystemExit(main())
