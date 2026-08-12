"""`bobodan web` — single-process local Web server (P5G.1).

Serves the built React frontend and the FastAPI backend from one process.
This is the engine the Windows desktop app (P5G.2) will package as its
sidecar; running it directly is the developer / no-install path.

Production conventions (Windows):

- user config & registry:  %APPDATA%\\Bobodan   (BOBODAN_HOME)
- logs & cache:            %LOCALAPPDATA%\\Bobodan\\logs
- user libraries stay in the folder the user chose; never moved here.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _windows_appdata(env_name: str) -> str:
    """%APPDATA% / %LOCALAPPDATA% with a sane fallback to home."""
    value = os.getenv(env_name)
    if value:
        return value
    return str(Path.home() / f".{env_name.lower()}")


def resolve_home() -> str:
    """BOBODAN_HOME for production: %APPDATA%\\Bobodan on Windows."""
    configured = os.getenv("BOBODAN_HOME")
    if configured:
        return os.path.abspath(configured)
    if os.name == "nt":
        return os.path.join(_windows_appdata("APPDATA"), "Bobodan")
    return os.path.expanduser("~/.bobodan")


def resolve_log_dir() -> str:
    """Logs for production: %LOCALAPPDATA%\\Bobodan\\logs on Windows."""
    if os.name == "nt":
        return os.path.join(_windows_appdata("LOCALAPPDATA"), "Bobodan", "logs")
    return str(Path.home() / ".local" / "state" / "bobodan" / "logs")


def _port_free(host: str, port: int) -> bool:
    """True when we can bind the port (connect-testing is unreliable for
    sockets in LISTEN inside the same process)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(host: str, preferred: int) -> int:
    """Pick a usable port: preferred if free, else scan upward."""
    if preferred:
        if _port_free(host, preferred):
            return preferred
        print(f"端口 {preferred} 已被占用，正在尝试相邻端口…", file=sys.stderr)
    for port in range(preferred or 8000, (preferred or 8000) + 50):
        if _port_free(host, port):
            return port
    raise OSError("在 127.0.0.1 上找不到可用端口（已尝试 50 个）。")


def _uvicorn_log_config(log_file: str | None) -> dict:
    """Uvicorn logging config: console always, file when log_file is set."""
    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        },
    }
    if log_file:
        handlers["file"] = {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": log_file,
            "encoding": "utf-8",
        }
    loggers: dict = {}
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        loggers[name] = {
            "handlers": ["console", "file"] if log_file else ["console"],
            "level": "INFO",
            "propagate": False,
        }
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
        },
        "handlers": handlers,
        "loggers": loggers,
    }


def _open_browser_later(url: str, delay: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def run_web(
    host: str = "127.0.0.1",
    port: int = 8000,
    no_browser: bool = False,
    dev: bool = False,
) -> int:
    """Start the single-process server. Returns process exit code."""
    from web.backend.app import create_app
    from web.backend.static import mount_frontend

    # Production home: user-level config belongs in %APPDATA%, not the CWD.
    # (Development keeps whatever BOBODAN_HOME / BOBODAN_WORKSPACE say.)
    if not dev and not os.getenv("BOBODAN_HOME"):
        production_home = resolve_home()
        os.environ["BOBODAN_HOME"] = production_home
        Path(production_home).mkdir(parents=True, exist_ok=True)
        print(f"用户数据目录：{production_home}")

    # Logs to %LOCALAPPDATA% in production; stderr in dev. uvicorn's own
    # dictConfig must carry the file handler (basicConfig gets overwritten).
    log_file: str | None = None
    if not dev:
        log_dir = Path(resolve_log_dir())
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "web.log")
            print(f"日志：{log_file}")
        except OSError as exc:
            print(f"无法写入日志目录（{exc}），日志输出到终端。", file=sys.stderr)

    app = create_app()
    mount_frontend(app)

    try:
        free_port = find_free_port(host, port)
    except OSError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1

    url = f"http://{host}:{free_port}/"
    if not no_browser:
        _open_browser_later(url)
    print(f"Bobodan 已启动：{url}")

    try:
        import uvicorn

        uvicorn.run(
            app,
            host=host,
            port=free_port,
            log_level="info",
            log_config=_uvicorn_log_config(log_file),
        )
    except KeyboardInterrupt:
        print("\n已停止。")
        return 0
    except Exception as exc:
        # Port race, bind failure, backend crash — give an actionable hint.
        print(f"服务启动失败：{exc}", file=sys.stderr)
        print(
            "请检查：\n"
            "  1. 端口是否被其他程序占用（换 --port 端口重试）；\n"
            "  2. 配置是否完整（.env 中 Provider API Key）；\n"
            "  3. 前端是否已构建（cd web/frontend && npm run build）。",
            file=sys.stderr,
        )
        return 1


def build_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="首选端口（默认 8000，被占用时自动向后找）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    # 注意：argparse 把 help 当 % 格式串，%APPDATA% 必须写成 %%APPDATA%%。
    parser.add_argument("--dev", action="store_true", help="开发模式：不切换 %%APPDATA%% 数据目录")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bobodan web", description="单进程启动 Bobodan 本地 Web")
    build_parser(parser)
    args = parser.parse_args(argv)
    return run_web(host=args.host, port=args.port, no_browser=args.no_browser, dev=args.dev)


if __name__ == "__main__":
    raise SystemExit(main())
