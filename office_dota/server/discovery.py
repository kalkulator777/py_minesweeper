"""Обнаружение матчей в локальной сети через UDP-броадкаст.

Смысл: человек запускает один файл и сразу видит список матчей коллег.
Никакого «узнай у Ани её IP».

Каждый сервер раз в две секунды кидает в сеть маячок с описанием комнаты
и одновременно слушает чужие маячки.
"""
from __future__ import annotations

import json
import socket
import threading
import time

BEACON_PORT = 8889
BEACON_INTERVAL = 2.0
BEACON_TTL = 7.0                 # через столько секунд молчания матч считается пропавшим
MAGIC = "OFFICEDOTA1"


def local_ip() -> str:
    """IP машины в локальной сети. Пакеты при этом никуда не уходят."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def _broadcast_addresses() -> list[str]:
    """Куда рассылать. Общий броадкаст плюс широковещательный адрес своей подсети."""
    addrs = ["255.255.255.255"]
    ip = local_ip()
    parts = ip.split(".")
    if len(parts) == 4 and ip != "127.0.0.1":
        addrs.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    return addrs


class Discovery:
    """Маячок и приёмник. Работает в фоновых потоках, не трогает цикл Tornado."""

    def __init__(self, describe, port: int = BEACON_PORT) -> None:
        self.describe = describe          # функция -> dict с описанием комнаты
        self.port = port
        self.found: dict[str, dict] = {}  # "ip:port" -> описание
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self.enabled = True
        self.error = ""

    def start(self) -> None:
        for target in (self._listen_loop, self._announce_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    # --- рассылка ----------------------------------------------------------
    def _announce_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        targets = _broadcast_addresses()
        while not self._stop.is_set():
            try:
                info = dict(self.describe())
                info["magic"] = MAGIC
                payload = json.dumps(info, ensure_ascii=False).encode("utf-8")
                for addr in targets:
                    try:
                        sock.sendto(payload, (addr, self.port))
                    except OSError:
                        pass
            except Exception as exc:                          # noqa: BLE001
                self.error = str(exc)
            self._stop.wait(BEACON_INTERVAL)
        sock.close()

    # --- приём -------------------------------------------------------------
    def _listen_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            sock.bind(("", self.port))
        except OSError as exc:
            # Порт занят другим экземпляром на этой же машине — не страшно,
            # просто не увидим чужие матчи из этого процесса.
            self.enabled = False
            self.error = f"не удалось слушать UDP {self.port}: {exc}"
            sock.close()
            return
        sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(info, dict) or info.get("magic") != MAGIC:
                continue
            info["ip"] = addr[0]
            info["seen"] = time.time()
            key = f"{addr[0]}:{info.get('port', 8888)}"
            with self._lock:
                self.found[key] = info
        sock.close()

    def games(self, exclude_self: str = "") -> list[dict]:
        now = time.time()
        with self._lock:
            stale = [k for k, v in self.found.items() if now - v["seen"] > BEACON_TTL]
            for k in stale:
                self.found.pop(k, None)
            out = []
            for key, v in self.found.items():
                if exclude_self and v.get("id") == exclude_self:
                    continue
                d = dict(v)
                d["url"] = f"http://{v['ip']}:{v.get('port', 8888)}/"
                d["key"] = key
                d.pop("magic", None)
                out.append(d)
        out.sort(key=lambda d: (d.get("phase") != "lobby", d.get("name", "")))
        return out
