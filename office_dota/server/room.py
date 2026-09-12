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
        print(f"[room] {p.name} отключился, дедлайн через {DISCONNECT_GRACE}с, фаза={self.phase}", flush=True)
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
            print(f"[room] дедлайн {p.name} истёк, фаза={self.phase}", flush=True)
            if self.phase in (PHASE_RUNNING, PHASE_PREGAME):
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

    # ======================================================================
    #  Команды от клиента
    # ======================================================================
    def handle(self, p: Player, msg: dict) -> None:
        kind = msg.get("t")
        fn = getattr(self, f"_cmd_{kind}", None)
        if fn is None:
            self.send(p, {"t": "err", "m": f"неизвестная команда {kind}"})
            return
        try:
            fn(p, msg)
        except Exception as exc:                              # noqa: BLE001
            self.send(p, {"t": "err", "m": f"{type(exc).__name__}: {exc}"})

    # --- лобби -------------------------------------------------------------
    def _cmd_set_name(self, p: Player, m: dict) -> None:
        name = str(m.get("name", "")).strip()[:24]
        if name:
            p.name = name
            if self.world and p.hero_id:
                h = self.world.heroes.get(p.hero_id)
                if h is not None:
                    h.name = name
            self.broadcast_state()

    def _cmd_set_team(self, p: Player, m: dict) -> None:
        if self.phase != PHASE_LOBBY:
            return
        team = int(m.get("team", 0))
        if team in (TEAM_DEV, TEAM_MGMT):
            p.team = team
            p.view = ClientView(team)
            self.broadcast_state()

    def _cmd_pick_hero(self, p: Player, m: dict) -> None:
        if self.phase not in (PHASE_LOBBY, PHASE_PREGAME, PHASE_RUNNING):
            return
        if self.phase != PHASE_LOBBY and p.hero_id:
            return                       # герой уже есть, менять на ходу нельзя
        key = str(m.get("hero", ""))
        if key not in C.HEROES:
            self.send(p, {"t": "err", "m": "нет такого героя"})
            return
        taken = {pl.hero_key for pl in self.players.values()
                 if pl is not p and pl.team == p.team}
        if key in taken:
            self.send(p, {"t": "err", "m": "герой уже занят в вашей команде"})
            return
        p.hero_key = key
        if self.phase != PHASE_LOBBY:
            self._spawn_latecomer(p)
        self.broadcast_state()

    def _spawn_latecomer(self, p: Player) -> None:
        """Опоздавший получает героя с догоняющей компенсацией.

        Без компенсации заходить в матч на десятой минуте бессмысленно:
        первый же размен закончится смертью. Даём средний уровень и
        средний нетворс своей команды, слегка урезанные.
        """
        if self.world is None:
            return
        if p.team < 0:
            p.team = self._auto_team()
        mates = [h for h in self.world.heroes.values()
                 if h.team == p.team and h.etype == "hero"]
        h = self.world.spawn_hero(p.team, p.hero_key, name=p.name)
        p.hero_id = h.id
        p.view = ClientView(p.team)

        if mates:
            avg_level = sum(m.level for m in mates) / len(mates)
            avg_gold = sum(m.total_gold_earned for m in mates) / len(mates)
        else:
            # Пустая команда — равняемся на противника, иначе опоздавший
            # выходит первым уровнем против восемнадцатого
            enemies = [e for e in self.world.heroes.values()
                       if e.team != p.team and e.etype == "hero"]
            avg_level = (sum(e.level for e in enemies) / len(enemies)) if enemies else 1
            avg_gold = (sum(e.total_gold_earned for e in enemies) / len(enemies)) if enemies else 0

        target_level = max(1, int(avg_level * 0.85))
        if target_level > 1:
            self.world.grant_xp(h, C.xp_for_level(target_level), apply_mult=False)
        h.gold = max(h.gold, avg_gold * 0.7)
        self.broadcast_system(f"{p.name} подключился к матчу "
                              f"(уровень {h.level}, бюджет {int(h.gold)})")

    def _cmd_ready(self, p: Player, m: dict) -> None:
        p.ready = bool(m.get("v", True))
        self.broadcast_state()

    def _cmd_start(self, p: Player, m: dict) -> None:
        ok, err = self.start_match()
        if not ok:
            self.send(p, {"t": "err", "m": err})

    def _cmd_add_bot(self, p: Player, m: dict) -> None:
        if self.phase != PHASE_LOBBY:
            return
        team = int(m.get("team", TEAM_DEV))
        key = str(m.get("hero", "")) or self._free_hero(team)
        if not key:
            return
        bid = f"bot:{len(self.players)}:{key}"
        b = Player(bid, f"Бот — {C.HEROES[key]['name']}")
        b.team = team
        b.hero_key = key
        b.connected = False
        b.replaced_by_bot = True
        self.players[bid] = b
        self.broadcast_state()

    def _free_hero(self, team: int) -> str:
        taken = {pl.hero_key for pl in self.players.values() if pl.team == team}
        for k in C.HEROES:
            if k not in taken:
                return k
        return ""

    def _cmd_kick(self, p: Player, m: dict) -> None:
        if not p.is_host or self.phase != PHASE_LOBBY:
            return
        self.players.pop(str(m.get("pid", "")), None)
        self.broadcast_state()

    # --- пауза -------------------------------------------------------------
    def _cmd_pause(self, p: Player, m: dict) -> None:
        self.set_pause(PAUSE_REASON_MANUAL, by=p.name)

    def _cmd_unpause(self, p: Player, m: dict) -> None:
        self.request_unpause(f"{p.name} снимает паузу")

    def _cmd_play_without(self, p: Player, m: dict) -> None:
        self.play_without(str(m.get("pid", "")))

    def _cmd_chat(self, p: Player, m: dict) -> None:
        text = str(m.get("text", "")).strip()[:200]
        if not text:
            return
        entry = {"from": p.name, "team": p.team, "text": text,
                 "at": round(time.time(), 1)}
        self.chat.append(entry)
        self.chat = self.chat[-80:]
        self.broadcast({"t": "chat", "m": entry})

    # --- игровые действия --------------------------------------------------
    def _my_hero(self, p: Player):
        if self.world is None or not p.hero_id:
            return None
        h = self.world.heroes.get(p.hero_id)
        if h is None or not h.alive:
            return None
        return h

    def _cmd_order(self, p: Player, m: dict) -> None:
        h = self._my_hero(p)
        if h is None or self.paused:
            return
        self.world.issue_order(h, str(m.get("kind", "move")),
                               float(m.get("x", 0)), float(m.get("y", 0)),
                               int(m.get("target", 0)))

    def _cmd_cast(self, p: Player, m: dict) -> None:
        h = self._my_hero(p)
        if h is None or self.paused:
            return
        ok, why = self.world.cast_ability(h, int(m.get("i", 0)),
                                          int(m.get("target", 0)),
                                          float(m.get("x", 0)), float(m.get("y", 0)))
        if not ok:
            self.send(p, {"t": "err", "m": why, "quiet": 1})

    def _cmd_item(self, p: Player, m: dict) -> None:
        h = self._my_hero(p)
        if h is None or self.paused:
            return
        ok, why = self.world.use_item(h, int(m.get("slot", 0)),
                                      int(m.get("target", 0)),
                                      float(m.get("x", 0)), float(m.get("y", 0)))
        if not ok:
            self.send(p, {"t": "err", "m": why, "quiet": 1})

    def _cmd_level_up(self, p: Player, m: dict) -> None:
        h = self._my_hero(p)
        if h is None:
            return
        ok, why = self.world.level_ability(h, int(m.get("i", 0)))
        if not ok:
            self.send(p, {"t": "err", "m": why, "quiet": 1})

    def _cmd_buy(self, p: Player, m: dict) -> None:
        h = self._my_hero(p) or (self.world.heroes.get(p.hero_id) if self.world else None)
        if h is None:
            return
        ok, why = self.world.buy_item(h, str(m.get("k", "")))
        if not ok:
            self.send(p, {"t": "err", "m": why, "quiet": 1})

    def _cmd_sell(self, p: Player, m: dict) -> None:
        h = self.world.heroes.get(p.hero_id) if self.world else None
        if h is not None:
            self.world.sell_item(h, int(m.get("slot", 0)))

    def _cmd_swap(self, p: Player, m: dict) -> None:
        h = self.world.heroes.get(p.hero_id) if self.world else None
        if h is None:
            return
        a, b = int(m.get("a", 0)), int(m.get("b", 0))
        slots = h.items + h.backpack
        if 0 <= a < len(slots) and 0 <= b < len(slots):
            slots[a], slots[b] = slots[b], slots[a]
            h.items = slots[:len(h.items)]
            h.backpack = slots[len(h.items):]
            h._stats_dirty = True

    def _cmd_ping(self, p: Player, m: dict) -> None:
        self.send(p, {"t": "pong", "c": m.get("c")})
