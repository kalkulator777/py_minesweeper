"""Комната: лобби, матч, игроки, пауза.

Здесь живёт главное требование проекта — устойчивость к тому, что людей
дёргают с игры. Порядок приоритетов: сначала подождать человека,
и только если команда решит — заменить ботом.
"""
from __future__ import annotations

import json
import time

from ..game import content as C, gamemap as gm
from ..game.consts import (
    DISCONNECT_GRACE, ORDER_ATTACK_MOVE, ORDER_ATTACK_UNIT, ORDER_HOLD,
    ORDER_MOVE, ORDER_STOP, PAUSE_REASON_DISCONNECT, PAUSE_REASON_MANUAL,
    PHASE_FINISHED, PHASE_LOBBY, PHASE_PAUSED, PHASE_PREGAME, PHASE_RUNNING,
    TEAM_DEV, TEAM_MGMT, TEAM_NAMES, TICK_DT, UNPAUSE_COUNTDOWN,
)
from ..game.snapshot import ClientView, scoreboard, static_map
from ..game.world import World

PREGAME_TIME = 20.0          # с от старта матча до первой волны


class Player:
    """Человек за компом. Переживает разрыв связи — по этому и узнаётся."""

    __slots__ = ("pid", "name", "team", "hero_key", "hero_id", "connected",
                 "socket", "view", "last_seen", "is_host", "ready", "replaced_by_bot")

    def __init__(self, pid: str, name: str) -> None:
        self.pid = pid
        self.name = name
        self.team = -1
        self.hero_key = ""
        self.hero_id = 0
        self.connected = True
        self.socket = None
        self.view: ClientView | None = None
        self.last_seen = time.monotonic()
        self.is_host = False
        self.ready = False
        self.replaced_by_bot = False

    def to_wire(self) -> dict:
        return {
            "pid": self.pid, "name": self.name, "team": self.team,
            "hero": self.hero_key, "connected": 1 if self.connected else 0,
            "host": 1 if self.is_host else 0, "ready": 1 if self.ready else 0,
            "bot": 1 if self.replaced_by_bot else 0,
        }


class Room:
    def __init__(self, name: str = "Офис") -> None:
        self.name = name
        self.players: dict[str, Player] = {}
        self.world: World | None = None
        self.phase = PHASE_LOBBY
        self.created = time.time()

        # --- состояние паузы ---
        self.paused = False
        self.pause_reason = ""
        self.pause_by = ""
        self.pause_waiting_for: list[str] = []
        self.unpause_countdown = 0.0
        self.pregame_timer = 0.0
        self._disconnect_deadlines: dict[str, float] = {}

        self.chat: list[dict] = []
        self._last_scoreboard = 0.0

    # ======================================================================
    #  Игроки
    # ======================================================================
    def join(self, pid: str, name: str, socket) -> Player:
        p = self.players.get(pid)
        if p is None:
            p = Player(pid, name)
            p.is_host = not any(pl.is_host for pl in self.players.values())
            self.players[pid] = p
            if self.phase == PHASE_LOBBY:
                p.team = self._auto_team()
        else:
            # Реконнект: человек вернулся и забирает своего героя обратно
            p.name = name or p.name
            if p.replaced_by_bot and p.hero_id and self.world:
                h = self.world.heroes.get(p.hero_id)
                if h is not None:
                    h.is_bot = False
                p.replaced_by_bot = False
                self.broadcast_system(f"{p.name} вернулся и забрал своего героя у бота")

        p.connected = True
        p.socket = socket
        p.last_seen = time.monotonic()
        p.view = ClientView(p.team if p.team >= 0 else TEAM_DEV)
        self._disconnect_deadlines.pop(pid, None)

        if self.paused and self.pause_reason == PAUSE_REASON_DISCONNECT:
            if pid in self.pause_waiting_for:
                self.pause_waiting_for.remove(pid)
            if not self.pause_waiting_for:
                self.request_unpause(f"{p.name} вернулся")
        return p

    def _auto_team(self) -> int:
        dev = sum(1 for p in self.players.values() if p.team == TEAM_DEV)
        mgmt = sum(1 for p in self.players.values() if p.team == TEAM_MGMT)
        return TEAM_DEV if dev <= mgmt else TEAM_MGMT

    def leave(self, pid: str) -> None:
        p = self.players.get(pid)
        if p is None:
            return
        p.connected = False
        p.socket = None
        if self.phase == PHASE_LOBBY:
            self.players.pop(pid, None)
            if p.is_host:
                for other in self.players.values():
                    other.is_host = True
                    break
            return
        # В матче — не выкидываем, даём время вернуться
        self._disconnect_deadlines[pid] = time.monotonic() + DISCONNECT_GRACE
        self.broadcast_system(f"{p.name} отключился, ждём {int(DISCONNECT_GRACE)} с")

    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]

    # ======================================================================
    #  Пауза
    # ======================================================================
    def set_pause(self, reason: str, by: str = "", waiting: list[str] | None = None) -> None:
        if self.phase not in (PHASE_RUNNING, PHASE_PREGAME):
            return
        if self.paused:
            if waiting:
                for w in waiting:
                    if w not in self.pause_waiting_for:
                        self.pause_waiting_for.append(w)
            return
        self.paused = True
        self.pause_reason = reason
        self.pause_by = by
        self.pause_waiting_for = list(waiting or [])
        self.unpause_countdown = 0.0
        who = ", ".join(self.players[w].name for w in self.pause_waiting_for
                        if w in self.players)
        if reason == PAUSE_REASON_DISCONNECT:
            self.broadcast_system(f"Пауза: ждём {who}")
        else:
            self.broadcast_system(f"Пауза от {by}")
        self.broadcast_state()

    def request_unpause(self, why: str = "") -> None:
        if not self.paused:
            return
        if self.pause_reason == PAUSE_REASON_DISCONNECT and self.pause_waiting_for:
            # Нельзя снять паузу, пока кого-то ждём, — сначала «играем без него»
            return
        self.unpause_countdown = UNPAUSE_COUNTDOWN
        if why:
            self.broadcast_system(why)
        self.broadcast_state()

    def play_without(self, pid: str) -> None:
        """Команда решила не ждать: герой уходит под управление бота."""
        p = self.players.get(pid)
        if p is None:
            return
        p.replaced_by_bot = True
        if p.hero_id and self.world:
            h = self.world.heroes.get(p.hero_id)
            if h is not None:
                h.is_bot = True
        if pid in self.pause_waiting_for:
            self.pause_waiting_for.remove(pid)
        self.broadcast_system(f"Играем без {p.name} — героя ведёт бот")
        if not self.pause_waiting_for:
            self.request_unpause()

    def _check_disconnects(self) -> None:
        now = time.monotonic()
        due = [pid for pid, dl in self._disconnect_deadlines.items() if now >= dl]
        for pid in due:
            self._disconnect_deadlines.pop(pid, None)
            p = self.players.get(pid)
            if p is None or p.connected:
                continue
            if self.phase == PHASE_RUNNING:
                self.set_pause(PAUSE_REASON_DISCONNECT, waiting=[pid])

    # ======================================================================
    #  Жизненный цикл матча
    # ======================================================================
    def start_match(self) -> tuple[bool, str]:
        if self.phase != PHASE_LOBBY:
            return False, "матч уже идёт"
        picked = [p for p in self.players.values() if p.hero_key]
        if not picked:
            return False, "никто не выбрал героя"

        self.world = World(seed=int(time.time()) & 0xFFFF)
        for p in picked:
            if p.team < 0:
                p.team = self._auto_team()
            h = self.world.spawn_hero(p.team, p.hero_key, name=p.name)
            p.hero_id = h.id
            p.view = ClientView(p.team)
        self.phase = PHASE_PREGAME
        self.pregame_timer = PREGAME_TIME
        self.world.next_wave_time = PREGAME_TIME + C.WAVES["first_wave_time"]
        self.broadcast_system("Матч начинается")
        self.broadcast_state()
        return True, ""

    def tick(self) -> None:
        if self.phase in (PHASE_LOBBY, PHASE_FINISHED):
            return
        self._check_disconnects()

        if self.paused:
            if self.unpause_countdown > 0.0:
                self.unpause_countdown -= TICK_DT
                if self.unpause_countdown <= 0.0:
                    self.paused = False
                    self.pause_reason = ""
                    self.pause_waiting_for = []
                    self.broadcast_system("Продолжаем")
                    self.broadcast_state()
            return

        if self.phase == PHASE_PREGAME:
            self.pregame_timer -= TICK_DT
            if self.pregame_timer <= 0.0:
                self.phase = PHASE_RUNNING
                self.broadcast_state()

        if self.world is not None:
            self.world.tick(TICK_DT)
            if self.world.phase == PHASE_FINISHED:
                self.phase = PHASE_FINISHED
                w = self.world.winner
                self.broadcast_system(f"Победа: {TEAM_NAMES.get(w, '?')}")
                self.broadcast_state()

    # ======================================================================
    #  Рассылка
    # ======================================================================
    def send(self, p: Player, msg: dict) -> None:
        if p.socket is None:
            return
        try:
            p.socket.write_message(json.dumps(msg, ensure_ascii=False))
        except Exception:
            p.connected = False
            p.socket = None

    def broadcast(self, msg: dict) -> None:
        for p in self.connected_players():
            self.send(p, msg)

    def broadcast_system(self, text: str) -> None:
        entry = {"from": "", "text": text, "sys": 1, "at": round(time.time(), 1)}
        self.chat.append(entry)
        self.chat = self.chat[-80:]
        self.broadcast({"t": "chat", "m": entry})

    def broadcast_state(self) -> None:
        self.broadcast(self.state_msg())

    def state_msg(self) -> dict:
        return {
            "t": "state",
            "phase": self.phase,
            "paused": 1 if self.paused else 0,
            "pause_reason": self.pause_reason,
            "pause_by": self.pause_by,
            "waiting": [{"pid": w, "name": self.players[w].name}
                        for w in self.pause_waiting_for if w in self.players],
            "countdown": round(self.unpause_countdown, 1),
            "pregame": round(self.pregame_timer, 1),
            "players": [p.to_wire() for p in self.players.values()],
            "room": self.name,
            "winner": self.world.winner if self.world else -1,
        }

    def push_snapshots(self) -> None:
        if self.world is None:
            return
        events = self.world.drain_events()
        for p in self.connected_players():
            if p.view is None:
                continue
            hero = self.world.heroes.get(p.hero_id) if p.hero_id else None
            msg = p.view.build(self.world, hero)
            if events:
                msg["ev"] = events
            if self.paused:
                msg["paused"] = 1
            self.send(p, msg)

        now = time.monotonic()
        if now - self._last_scoreboard > 1.0:
            self._last_scoreboard = now
            sb = scoreboard(self.world)
            sb["t"] = "score"
            self.broadcast(sb)
