"""WebSocket-точка входа. Тонкая: разбирает сообщение и отдаёт комнате."""
from __future__ import annotations

import json

import tornado.websocket

from ..game import content as C
from ..game.snapshot import static_map


class GameSocket(tornado.websocket.WebSocketHandler):
    def initialize(self, room) -> None:
        self.room = room
        self.pid = ""

    def check_origin(self, origin: str) -> bool:
        return True                      # игра живёт в локальной сети

    def open(self) -> None:
        self.set_nodelay(True)

    def on_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        if not isinstance(msg, dict):
            return

        if msg.get("t") == "hello":
            self.pid = str(msg.get("pid", ""))[:64] or f"anon{id(self)}"
            name = str(msg.get("name", "")).strip()[:24] or "Аноним"
            p = self.room.join(self.pid, name, self)
            self.write_message(json.dumps({
                "t": "welcome",
                "pid": p.pid,
                "you": p.to_wire(),
                "map": static_map(),
                "heroes": C.HEROES,
                "items": C.ITEMS,
                "shop": C.SHOP_LAYOUT,
                "chat": self.room.chat[-30:],
            }, ensure_ascii=False))
            # Остальным тоже нужно увидеть, что кто-то зашёл
            self.room.broadcast_state()
            return

        p = self.room.players.get(self.pid)
        if p is None:
            return
        p.socket = self
        self.room.handle(p, msg)

    def on_close(self) -> None:
        if self.pid:
            self.room.leave(self.pid)
            self.room.broadcast_state()
