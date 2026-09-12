"""Заморозка матча на диск и его восстановление.

Офисный сценарий: начали в обед, всех разогнали на созвон, доигрываем вечером.
Сервер при этом может быть перезапущен или даже переехать на другую машину.

Сохраняется только то, что нельзя вывести заново. Карта, строения и их
цепочка неуязвимости пересобираются детерминированно, поэтому в файл
попадает лишь их состояние, а не геометрия. Летящие снаряды, каналы и
отложенные вызовы сознательно теряются: они живут доли секунды, и
восстанавливать их дороже, чем они стоят.
"""
from __future__ import annotations

import json
import os
import time

from ..game import content as C
from ..game.consts import (
    E_ANCIENT, E_BARRACKS, E_FOUNTAIN, E_HERO, E_TOWER, PHASE_PAUSED,
)
from ..game.items import Item
from ..game.world import World

FORMAT_VERSION = 4
SAVE_DIR = os.path.join(os.path.expanduser("~"), ".office_dota", "saves")


def save_path(name: str = "last") -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "last"
    return os.path.join(SAVE_DIR, f"{safe}.json")


# ==========================================================================
#  Сохранение
# ==========================================================================

def dump_room(room) -> dict:
    w = room.world
    if w is None:
        raise ValueError("матч ещё не начат, сохранять нечего")
    return {
        "version": FORMAT_VERSION,
        "saved_at": time.time(),
        "room": {
            "name": room.name,
            "phase": room.phase,
            "pregame": room.pregame_timer,
            "chat": room.chat[-40:],
        },
        "players": [
            {"pid": p.pid, "name": p.name, "team": p.team,
             "hero_key": p.hero_key, "hero_id": p.hero_id,
             "bot": p.replaced_by_bot, "host": p.is_host}
            for p in room.players.values()
        ],
        "world": dump_world(w),
    }


def dump_world(w: World) -> dict:
    return {
        "time": w.time,
        "tick": w.tick_count,
        "next_id": w._next_id,
        "wave_number": w.wave_number,
        "next_wave_time": w.next_wave_time,
        "winner": w.winner,
        "phase": w.phase,
        "teams": {
            str(t): {
                "barracks_down": {k: sorted(v) for k, v in ts.barracks_down.items()},
                "mega": ts.mega_creeps,
                "gold_earned": ts.gold_earned,
                "tower_kills": ts.tower_kills,
                "roshan_kills": ts.roshan_kills,
            } for t, ts in w.teams.items()
        },
        # Строения узнаём по роли, а не по id: id зависит от порядка создания,
        # роль — нет, поэтому сейв переживает изменения в порядке постройки.
        "buildings": [
            {"key": _building_key(b), "hp": b.hp, "alive": b.alive}
            for b in w.units.values() if b.is_building
        ],
        "heroes": [_dump_hero(h) for h in w.heroes.values() if h.etype == E_HERO],
        "neutrals": {
            "camps": [{"cid": c.cid, "respawn_at": c.respawn_at,
                       "spawned": c.spawned_once} for c in w.neutrals.camps],
            "roshan": {"respawn_at": w.neutrals.roshan.respawn_at,
                       "spawned": w.neutrals.roshan.spawned_once},
            "spots": [{"kind": s.kind, "next": s.next_spawn} for s in w.neutrals.spots],
        },
        "bots": [{"hero_id": b.hero_id, "lane": b.lane, "buy_idx": b.buy_idx}
                 for b in w.bots.brains.values()],
    }


def _building_key(b) -> str:
    return f"{b.team}:{b.etype}:{b.lane}:{b.tier}:{b.kind}:{round(b.x)}"


def _dump_hero(h) -> dict:
    return {
        "id": h.id, "key": h.hero_key, "team": h.team, "name": h.name,
        "player_id": h.player_id, "bot": h.is_bot,
        "x": h.x, "y": h.y, "hp": h.hp, "mana": h.mana, "alive": h.alive,
        "level": h.level, "xp": h.xp, "ap": h.ability_points,
        "gold": h.gold, "earned": h.total_gold_earned,
        "kills": h.kills, "deaths": h.deaths, "assists": h.assists,
        "last_hits": h.last_hits, "denies": h.denies,
        "respawn": h.respawn_timer, "streak": h.kill_streak,
        "buyback_cd": h.buyback_cooldown,
        "stash": list(h.stash),
        # Баффы сохраняем: без этого сейв обнулял откат выкупа всей команде,
        # то есть был эксплойтом, а не просто потерей данных
        "mods": [{"k": m.key, "n": m.name, "r": m.remaining, "d": m.duration,
                  "stats": m.stats, "flags": m.flags, "st": m.stacks,
                  "sh": m.shield_amount, "sht": m.shield_type,
                  "src": m.source_id, "perm": m.permanent, "data": m.data}
                 for m in h.modifiers if not m.is_aura_effect and not m.permanent],
        "hero_damage": h.hero_damage, "tower_damage": h.tower_damage,
        "healing": h.healing_done,
        "abilities": [{"k": a.key, "lvl": a.level, "cd": a.cooldown,
                       "on": a.toggled} for a in h.abilities],
        "items": [None if it is None else {"k": it.key, "cd": it.cooldown,
                                           "ch": it.charges} for it in h.items],
        "backpack": [None if it is None else {"k": it.key} for it in h.backpack],
        "deliveries": [{"key": d["key"], "t": d["t"]} for d in h.deliveries],
    }


def save_room(room, name: str = "last") -> str:
    os.makedirs(SAVE_DIR, exist_ok=True)
    path = save_path(name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dump_room(room), f, ensure_ascii=False)
    os.replace(tmp, path)      # атомарно: сейв не может остаться обрезанным
    return path


# ==========================================================================
#  Восстановление
# ==========================================================================

def load_room(room, name: str = "last") -> tuple[bool, str]:
    path = save_path(name)
    if not os.path.exists(path):
        return False, "сохранения нет"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:                                   # noqa: BLE001
        return False, f"файл сохранения повреждён: {exc}"

    if data.get("version") != FORMAT_VERSION:
        return False, (f"сохранение версии {data.get('version')}, "
                       f"а нужна {FORMAT_VERSION} — доиграть не выйдет")
    try:
        _restore(room, data)
    except Exception as exc:                                   # noqa: BLE001
        return False, f"не удалось восстановить матч: {type(exc).__name__}: {exc}"
    return True, ""


def _restore(room, data: dict) -> None:
    from .room import Player

    wd = data["world"]
    w = World()
    w.time = float(wd["time"])
    w.tick_count = int(wd["tick"])
    w.wave_number = int(wd["wave_number"])
    w.next_wave_time = float(wd["next_wave_time"])
    w.winner = int(wd.get("winner", -1))
    w.phase = wd.get("phase", w.phase)

    for t_str, ts_data in wd["teams"].items():
        ts = w.teams[int(t_str)]
        ts.barracks_down = {k: set(v) for k, v in ts_data["barracks_down"].items()}
        ts.mega_creeps = bool(ts_data["mega"])
        ts.gold_earned = float(ts_data["gold_earned"])
        ts.tower_kills = int(ts_data["tower_kills"])
        ts.roshan_kills = int(ts_data.get("roshan_kills", 0))

    by_key = {_building_key(b): b for b in w.units.values() if b.is_building}
    for bd in wd["buildings"]:
        b = by_key.get(bd["key"])
        if b is None:
            continue
        b.hp = float(bd["hp"])
        b.alive = bool(bd["alive"])

    max_id = int(wd["next_id"])
    for hd in wd["heroes"]:
        h = w.spawn_hero(hd["team"], hd["key"], hd.get("player_id", 0),
                         hd.get("name", ""), bool(hd.get("bot")))
        # Сохранённый id важен: на него ссылаются игроки и боты
        w.units.pop(h.id, None)
        w.heroes.pop(h.id, None)
        h.id = int(hd["id"])
        w.units[h.id] = h
        w.heroes[h.id] = h
        max_id = max(max_id, h.id + 1)

        h.level = int(hd["level"])
        h.xp = float(hd["xp"])
        h.ability_points = int(hd["ap"])
        h.gold = float(hd["gold"])
        h.total_gold_earned = float(hd["earned"])
        h.kills, h.deaths, h.assists = hd["kills"], hd["deaths"], hd["assists"]
        h.last_hits, h.denies = hd["last_hits"], hd["denies"]
        h.respawn_timer = float(hd["respawn"])
        h.kill_streak = int(hd.get("streak", 0))
        h.hero_damage = float(hd.get("hero_damage", 0))
        h.tower_damage = float(hd.get("tower_damage", 0))
        h.healing_done = float(hd.get("healing", 0))

        for saved, ability in zip(hd["abilities"], h.abilities):
            ability.level = int(saved["lvl"])
            ability.cooldown = float(saved["cd"])
            ability.toggled = bool(saved.get("on"))
        for i, sd in enumerate(hd["items"]):
            if sd and i < len(h.items):
                it = Item(sd["k"])
                it.cooldown = float(sd.get("cd", 0))
                it.charges = int(sd.get("ch", it.charges))
                h.items[i] = it
        for i, sd in enumerate(hd["backpack"]):
            if sd and i < len(h.backpack):
                h.backpack[i] = Item(sd["k"])
        h.deliveries = [{"key": d["key"], "t": float(d["t"])}
                        for d in hd.get("deliveries", [])]
        h.buyback_cooldown = float(hd.get("buyback_cd", 0.0))
        h.stash = list(hd.get("stash", []))
        from ..game.modifiers import Modifier
        for md in hd.get("mods", []):
            m = Modifier(md["k"], float(md.get("d", 0)), name=md.get("n", ""),
                         stats=md.get("stats") or {}, flags=int(md.get("flags", 0)),
                         shield_amount=float(md.get("sh", 0)),
                         shield_type=md.get("sht", "all"),
                         source_id=int(md.get("src", 0)),
                         data=md.get("data") or {})
            m.remaining = float(md.get("r", m.duration))
            m.stacks = int(md.get("st", 1))
            h.modifiers.append(m)

        h.x, h.y = float(hd["x"]), float(hd["y"])
        h.alive = bool(hd["alive"])
        h._stats_dirty = True
        h.ensure_stats()
        h.hp = min(float(hd["hp"]), h.max_hp)
        h.mana = min(float(hd["mana"]), h.max_mana)

    w._next_id = max_id

    nd = wd.get("neutrals", {})
    for saved, camp in zip(nd.get("camps", []), w.neutrals.camps):
        camp.respawn_at = float(saved["respawn_at"])
        camp.spawned_once = bool(saved["spawned"])
    if nd.get("roshan"):
        w.neutrals.roshan.respawn_at = float(nd["roshan"]["respawn_at"])
        w.neutrals.roshan.spawned_once = bool(nd["roshan"]["spawned"])
    for saved, spot in zip(nd.get("spots", []), w.neutrals.spots):
        spot.next_spawn = float(saved["next"])

    for bd in wd.get("bots", []):
        h = w.heroes.get(int(bd["hero_id"]))
        if h is None:
            continue
        brain = w.bots.ensure(h)
        brain.lane = bd["lane"]
        brain.buy_idx = int(bd["buy_idx"])

    room.world = w
    room.name = data["room"]["name"]
    room.phase = data["room"]["phase"]
    room.pregame_timer = float(data["room"].get("pregame", 0))
    room.chat = list(data["room"].get("chat", []))
    room.players.clear()
    for pd in data["players"]:
        p = Player(pd["pid"], pd["name"])
        p.team = pd["team"]
        p.hero_key = pd["hero_key"]
        p.hero_id = pd["hero_id"]
        p.replaced_by_bot = bool(pd.get("bot"))
        p.is_host = bool(pd.get("host"))
        p.connected = False
        room.players[p.pid] = p

    # Восстановленный матч всегда встаёт на паузу: люди ещё не за компами
    room.paused = True
    room.pause_reason = "manual"
    room.pause_by = "восстановление"
    room.unpause_countdown = 0.0


def list_saves() -> list[dict]:
    if not os.path.isdir(SAVE_DIR):
        return []
    out = []
    for fn in os.listdir(SAVE_DIR):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(SAVE_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            out.append({
                "name": fn[:-5],
                "saved_at": d.get("saved_at", 0),
                "room": d.get("room", {}).get("name", ""),
                "time": round(d.get("world", {}).get("time", 0)),
                "players": len(d.get("players", [])),
                "version": d.get("version"),
            })
        except Exception:
            continue
    out.sort(key=lambda d: -d["saved_at"])
    return out
