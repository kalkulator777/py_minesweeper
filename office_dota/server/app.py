"""Tornado-приложение: статика, WebSocket, обнаружение матчей, цикл симуляции."""
from __future__ import annotations

import os
import time
import uuid

import tornado.ioloop
import tornado.web

from ..game import content as C
from ..game.consts import TICK_DT
from .discovery import Discovery, local_ip
from .room import Room
from .ws import GameSocket

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "web")


class IndexHandler(tornado.web.RequestHandler):
    def get(self) -> None:
        self.set_header("Cache-Control", "no-store")
        self.render(os.path.join(WEB_DIR, "index.html"))


class GamesHandler(tornado.web.RequestHandler):
    def initialize(self, server) -> None:
        self.server = server

    def get(self) -> None:
        self.set_header("Cache-Control", "no-store")
        self.write({
            "games": self.server.discovery.games(exclude_self=self.server.server_id)
            if self.server.discovery else [],
            "discovery": bool(self.server.discovery and self.server.discovery.enabled),
            "note": (self.server.discovery.error
                     if self.server.discovery and self.server.discovery.error else ""),
        })


class InfoHandler(tornado.web.RequestHandler):
    def initialize(self, server) -> None:
        self.server = server

    def get(self) -> None:
        self.set_header("Cache-Control", "no-store")
        self.write({
            "name": self.server.room.name,
            "ip": self.server.ip,
            "port": self.server.port,
            "url": f"http://{self.server.ip}:{self.server.port}/",
            "phase": self.server.room.phase,
            "players": len(self.server.room.players),
            "content": C.status(),
        })


class GameServer:
    def __init__(self, port: int = 8888, room_name: str = "", announce: bool = True) -> None:
        self.port = port
        self.ip = local_ip()
        self.server_id = uuid.uuid4().hex[:12]
        self.room = Room(room_name or f"Матч на {self.ip}")
        self.discovery: Discovery | None = None
        self.announce = announce

        self.app = tornado.web.Application(
            [
                (r"/", IndexHandler),
                (r"/ws", GameSocket, {"room": self.room}),
                (r"/api/games", GamesHandler, {"server": self}),
                (r"/api/info", InfoHandler, {"server": self}),
                (r"/(.*)", tornado.web.StaticFileHandler,
                 {"path": WEB_DIR, "default_filename": "index.html"}),
            ],
            debug=False,
            compress_response=True,
        )

    def describe(self) -> dict:
        return {
            "id": self.server_id,
            "name": self.room.name,
            "port": self.port,
            "players": len([p for p in self.room.players.values() if p.connected]),
            "total": len(self.room.players),
            "phase": self.room.phase,
            "started": round(self.room.created),
        }

    def _loop(self) -> None:
        self.room.tick()
        self.room.push_snapshots()

    def run(self) -> None:
        self.app.listen(self.port, address="0.0.0.0")
        if self.announce:
            self.discovery = Discovery(self.describe)
            self.discovery.start()
        tornado.ioloop.PeriodicCallback(self._loop, TICK_DT * 1000.0).start()
        tornado.ioloop.IOLoop.current().start()
