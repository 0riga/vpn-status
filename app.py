import http.client
import http.server
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

API_TOKEN = os.environ.get("API_TOKEN")
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "30"))
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("BIND_PORT", "8080"))
DOCKER_SOCK = "/var/run/docker.sock"

if not API_TOKEN:
    raise SystemExit("API_TOKEN обязателен — задайте случайный токен через env")

# Подстроки в имени контейнера ИЛИ имени образа, по которым узнаём протокол.
PROTOCOL_PATTERNS = {
    "l2tp/ipsec": ["hwdsl2/ipsec-vpn-server", "ipsec-vpn-server", "ipsec"],
    "pptp": ["mobtitude/vpn-pptp", "vpn-pptp", "pptp"],
}


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection поверх unix-сокета — http.client сам разберёт
    Content-Length/chunked encoding, ручной парсинг не нужен."""

    def __init__(self, path, timeout=5):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_socket_path)
        self.sock = sock


def docker_containers():
    conn = UnixHTTPConnection(DOCKER_SOCK)
    try:
        conn.request("GET", "/containers/json?all=true", headers={"Host": "localhost"})
        resp = conn.getresponse()
        body = resp.read()
    finally:
        conn.close()
    return json.loads(body)


def detect_protocol(container):
    names = " ".join(container.get("Names", [])).lower()
    image = container.get("Image", "").lower()
    haystack = f"{names} {image}"
    for proto, patterns in PROTOCOL_PATTERNS.items():
        if any(p in haystack for p in patterns):
            return proto
    return None


# Однажды увиденные VPN-контейнеры: имя -> протокол. Нужно, чтобы если
# контейнер не просто остановлен, а полностью удалён из Docker (и Docker
# API о нём больше ничего не знает), он всё равно не пропадал молча из
# ответа, а был явно помечен как недоступный.
known_services = {}


def collect_status():
    current = {}
    for container in docker_containers():
        proto = detect_protocol(container)
        if not proto:
            continue
        name = container.get("Names", ["?"])[0].lstrip("/")
        current[name] = {
            "protocol": proto,
            "container": name,
            "docker_status": container.get("State"),  # running / exited / restarting ...
            "up": container.get("State") == "running",
        }

    for name, info in current.items():
        known_services[name] = info["protocol"]

    results = []
    for name, proto in known_services.items():
        if name in current:
            results.append(current[name])
        else:
            results.append({
                "protocol": proto,
                "container": name,
                "docker_status": "removed",  # контейнера больше нет в Docker вообще
                "up": False,
            })
    return results


state_lock = threading.Lock()
state = {"updated_at": None, "services": []}


def worker():
    while True:
        try:
            services = collect_status()
            with state_lock:
                state["services"] = services
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
                state.pop("error", None)
        except Exception as e:
            with state_lock:
                state["error"] = str(e)
        time.sleep(INTERVAL)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # не пишем access-лог на каждый запрос — экономим I/O

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        if self.path != "/status":
            self._send_json(404, {"error": "not found"})
            return
        if self.headers.get("X-API-Token") != API_TOKEN:
            self._send_json(401, {"error": "unauthorized"})
            return
        with state_lock:
            self._send_json(200, state)

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    server = http.server.ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    server.serve_forever()
