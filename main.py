import json
import os
import socket
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from multiprocessing import Process
from pathlib import Path
from urllib.parse import parse_qs
from copy import deepcopy

from pymongo import MongoClient


APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "3000"))

SOCKET_HOST = os.getenv("SOCKET_HOST", "0.0.0.0")
SOCKET_PORT = int(os.getenv("SOCKET_PORT", "5000"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "goit")
MONGO_COL = os.getenv("MONGO_COLLECTION", "messages")

ROOT_DIR = Path(__file__).parent.resolve()
STATIC = {
    "/": ROOT_DIR / "index.html",
    "/index.html": ROOT_DIR / "index.html",
    "/message.html": ROOT_DIR / "message.html",
    "/style.css": ROOT_DIR / "style.css",
    "/logo.png": ROOT_DIR / "logo.png",
}
ERROR_404 = ROOT_DIR / "error.html"

STORAGE_DIR = ROOT_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = STORAGE_DIR / "app.log"
JSON_DUMP = STORAGE_DIR / "data.json"


# HTTP SERVER
class SimpleHandler(BaseHTTPRequestHandler):
    server_version = "GoITPlainHTTP/1.0"

    def _content_type(self, path: Path) -> str:
        if path.suffix == ".html":
            return "text/html; charset=utf-8"
        if path.suffix == ".css":
            return "text/css; charset=utf-8"
        if path.suffix == ".png":
            return "image/png"
        return "application/octet-stream"

    def _serve_file(self, path: Path, code: int = 200):
        try:
            data = path.read_bytes()
            self.send_response(code)
            self.send_header("Content-Type", self._content_type(path))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._serve_404()

    def _serve_404(self):
        data = ERROR_404.read_bytes() if ERROR_404.exists() else b"404 Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        target = STATIC.get(self.path)
        if target and target.exists():
            self._serve_file(target, 200)
        else:
            self._serve_404()

    def do_POST(self):
        if self.path != "/message":
            self._serve_404()
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="ignore")
        form = parse_qs(body)

        username = (form.get("username") or [""]).pop().strip()
        message = (form.get("message") or [""]).pop().strip()

        if not username or not message:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h3>Bad Request: username and message are required</h3>")
            return

        payload = {"username": username, "message": message}

        # лог у файл
        LOG_FILE.write_text(
            f"{datetime.now().isoformat()} | {username}: {message}\n",
            encoding="utf-8",
        ) if LOG_FILE.exists() else LOG_FILE.write_text(
            f"{datetime.now().isoformat()} | {username}: {message}\n",
            encoding="utf-8",
        )

        # відправити на socket-сервер (UDP)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(json.dumps(payload).encode("utf-8"), (SOCKET_HOST, SOCKET_PORT))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h3>Socket error: {e}</h3>".encode("utf-8"))
            return

        self.send_response(302)
        self.send_header("Location", "/")
        self.end_headers()


def run_http():
    httpd = HTTPServer((APP_HOST, APP_PORT), SimpleHandler)
    print(f"[HTTP] listening on http://{APP_HOST}:{APP_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# SOCKET SERVER
def run_socket():
    # підключення до Mongo
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    col = db[MONGO_COL]

    if not JSON_DUMP.exists():
        JSON_DUMP.write_text("[]", encoding="utf-8")

    # UDP сервер
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as srv:
        srv.bind((SOCKET_HOST, SOCKET_PORT))
        print(f"[SOCKET] UDP listening on {SOCKET_HOST}:{SOCKET_PORT}")
        while True:
            data, addr = srv.recvfrom(64 * 1024)
            try:
                doc = json.loads(data.decode("utf-8"))
                doc["date"] = datetime.now().isoformat()

                col.insert_one(doc)

                safe_doc = deepcopy(doc)
                if "_id" in safe_doc:
                    safe_doc["_id"] = str(safe_doc["_id"])

                try:
                    current = json.loads(JSON_DUMP.read_text(encoding="utf-8"))
                    if not isinstance(current, list):
                        current = []
                except Exception:
                    current = []

                current.append(safe_doc)
                JSON_DUMP.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

                print(f"[SOCKET] saved from {addr}: {safe_doc}")
            except Exception as e:
                print(f"[SOCKET] error: {e}", file=sys.stderr)


# ENTRYPOINT
if __name__ == "__main__":
    p_http = Process(target=run_http, daemon=False)
    p_sock = Process(target=run_socket, daemon=False)
    p_sock.start()
    p_http.start()
    p_sock.join()
    p_http.join()
