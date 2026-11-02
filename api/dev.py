"""One local launcher for Vite + FastAPI, with independent API stop/start."""
import argparse
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from api.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


def port_available(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class LocalProcess:
    def __init__(self, settings):
        self.settings = settings
        self.process = None

    def spawn(self, command, **kwargs):
        self.process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        start_new_session=os.name != "nt", **kwargs)

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            try:
                if os.name == "nt":
                    self.process.terminate()
                else:
                    os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    self.process.kill()
                else:
                    os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
            except ProcessLookupError:
                pass
        self.process = None


class APIProcess(LocalProcess):
    def start(self):
        if self.process is not None and self.process.poll() is None:
            print("API đang chạy.", flush=True)
            return True
        if not port_available(self.settings.api_port):
            print(f"Không thể bật API: cổng {self.settings.api_port} đang được sử dụng.", flush=True)
            return False
        command = [sys.executable, "-m", "api.main", "--port", str(self.settings.api_port),
                   "--app-port", str(self.settings.app_port)]
        if self.settings.verification_enabled:
            command.append("--verification")
        if self.settings.data_dir:command.extend(['--data-dir',str(self.settings.data_dir)])
        self.spawn(command)
        for _ in range(60):
            if self.process.poll() is not None:
                break
            try:
                with urlopen(f"http://127.0.0.1:{self.settings.api_port}/api/v1/health", timeout=.2) as response:
                    if json.load(response).get("service") == "novel2voice-api":
                        print("API đã sẵn sàng.", flush=True)
                        return True
            except (OSError, ValueError):
                time.sleep(.1)
        self.stop()
        print("API không khởi động được; xem lỗi phía trên. App vẫn mở được.", flush=True)
        return False


class WorkerProcess(LocalProcess):
    def start(self):
        command=[sys.executable,'-m','api.worker']
        if self.settings.verification_enabled:command.append('--verification')
        if self.settings.data_dir:command.extend(['--data-dir',str(self.settings.data_dir)])
        self.spawn(command)


class AppProcess(LocalProcess):
    def start(self):
        environment = os.environ.copy()
        environment.update(NOVEL2VOICE_APP_PORT=str(self.settings.app_port),
                           NOVEL2VOICE_API_PORT=str(self.settings.api_port),
                           VITE_API_ORIGIN=f"http://127.0.0.1:{self.settings.api_port}",
                           NOVEL2VOICE_VERIFICATION="1" if self.settings.verification_enabled else "0")
        self.spawn([shutil.which("pnpm"), "--dir", str(ROOT / "app"), "run", "dev"], env=environment)
        for _ in range(150):
            if self.process.poll() is not None:
                break
            try:
                with urlopen(f"http://127.0.0.1:{self.settings.app_port}", timeout=.2) as response:
                    if 'id="app"' in response.read().decode():
                        return True
            except (OSError, ValueError):
                time.sleep(.1)
        self.stop()
        return False


def main():
    parser = argparse.ArgumentParser(description="Mở Vue/Vite app và FastAPI trên máy local.")
    parser.add_argument("--app-port", type=int, default=8000)
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--verification", action="store_true", help="Bật chế độ nghiệm thu offline T02.")
    parser.add_argument("--data-dir", type=Path, help="Kho riêng, không thay kho mặc định.")
    args = parser.parse_args()
    missing = [name for name in ("fastapi", "uvicorn") if importlib.util.find_spec(name) is None]
    if missing:
        print("Thiếu thư viện API. Chạy: uv sync --project api --frozen", file=sys.stderr)
        return 1
    if not shutil.which("pnpm"):
        print("Chưa có pnpm trong PATH. Cài pnpm trước khi chạy web app.", file=sys.stderr)
        return 1
    if not (ROOT / "app" / "node_modules" / "vite" / "package.json").is_file():
        print("Chưa cài frontend. Chạy: pnpm --dir app install --frozen-lockfile", file=sys.stderr)
        return 1
    try:
        settings = Settings(args.app_port, args.api_port, verification_enabled=args.verification,data_dir=args.data_dir.resolve() if args.data_dir else None)
        for label, port in (("App", settings.app_port), ("API", settings.api_port)):
            if not port_available(port):
                raise ValueError(f"Cổng {label} {port} đang được sử dụng. Chọn cặp cổng khác hoặc dừng launcher cũ.")
    except ValueError as error:
        print(f"Không thể khởi động: {error}", file=sys.stderr)
        return 1
    api, app, worker = APIProcess(settings), AppProcess(settings), WorkerProcess(settings)
    shutdown = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())

    def commands():
        for command in sys.stdin:
            command = command.strip().lower()
            if shutdown.is_set():
                return
            if command == "api stop":
                api.stop()
                print("API đã dừng; app vẫn mở. Dùng api start để bật lại.", flush=True)
            elif command == "api start":
                api.start()
            elif command in {"quit", "exit"}:
                shutdown.set()
                return
            elif command:
                print("Lệnh hỗ trợ: api stop | api start | quit", flush=True)
    try:
        if settings.verification_enabled:
            print("CHẾ ĐỘ KIỂM THỬ — provider/translator giả lập, không gọi dịch vụ thật.", flush=True)
        api.start()
        worker.start()
        if not app.start():
            print("Vite không khởi động được. Kiểm tra lỗi frontend phía trên.", file=sys.stderr)
            return 1
        print(f"\nApp: http://127.0.0.1:{settings.app_port}\n"
              f"Swagger: http://127.0.0.1:{settings.api_port}/docs\n"
              "Kiểm tra T01: api stop | api start | quit\n"
              "Dừng toàn bộ: Ctrl+C. Worker chạy riêng; không nạp model khi mở trang.\n", flush=True)
        threading.Thread(target=commands, daemon=True).start()
        shutdown.wait()
    finally:
        app.stop()
        api.stop()
        worker.stop()
        print("Đã dừng app, API và worker.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
