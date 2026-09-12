"""Запуск одной командой.

Никакого выбора «сервер или клиент». Запускаешь файл — поднимается сервер,
открывается браузер, а в меню уже виден список матчей коллег в сети.
Хочешь свой матч — жмёшь «Создать». Хочешь к Ане — жмёшь на её матч.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser


def _port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port(preferred: int = 8888) -> int:
    for p in range(preferred, preferred + 20):
        if _port_free(p):
            return p
    raise SystemExit("не нашёл свободный порт в диапазоне "
                     f"{preferred}..{preferred + 19}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="office-dota",
        description="Офисная дота: запусти этот файл, остальное — в браузере.")
    ap.add_argument("--port", type=int, default=8888, help="порт (по умолчанию 8888)")
    ap.add_argument("--name", default="", help="название матча в списке сети")
    ap.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    ap.add_argument("--no-announce", action="store_true",
                    help="не объявлять матч в локальной сети")
    args = ap.parse_args(argv)

    if sys.version_info < (3, 11):
        raise SystemExit(f"нужен Python 3.11+, а запущен {sys.version.split()[0]}")

    try:
        import tornado  # noqa: F401
    except ImportError:
        raise SystemExit(
            "не установлен tornado. Поставь его командой:\n"
            "    pip install tornado")

    from .server.app import GameServer

    port = pick_port(args.port)
    server = GameServer(port=port, room_name=args.name,
                        announce=not args.no_announce)
    url = f"http://{server.ip}:{port}/"

    from .game import content as C
    st = C.status()
    print("=" * 62)
    print("  ОФИСНАЯ ДОТА")
    print("=" * 62)
    print(f"  Открой в браузере:   {url}")
    print(f"  Или локально:        http://localhost:{port}/")
    print(f"  Коллегам скажи:      {server.ip}:{port}")
    print(f"  Героев: {st['heroes']}   Предметов: {st['items']}")
    if not args.no_announce:
        print("  Матч виден коллегам в сети автоматически.")
    print("  Остановить: Ctrl+C")
    print("=" * 62)

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}/")).start()

    try:
        server.run()
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
