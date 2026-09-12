"""Сборка снапшотов для клиента.

Два принципа:
1. Клиент получает только то, что видит его команда. Это и античит, и трафик.
2. Постоянные данные юнита (имя, тип, максимум HP) шлются один раз при
   появлении; каждый тик уходят только меняющиеся числа.
"""
from __future__ import annotations

from .consts import (
    E_ANCIENT, E_BARRACKS, E_CREEP, E_FOUNTAIN, E_HERO, E_ILLUSION, E_NEUTRAL,
    E_SUMMON, E_TOWER, E_WARD, F_INVISIBLE, F_TRUESIGHT, TEAM_NEUTRAL,
)
from .vmath import dist_sq

# Типы, которые клиенту вообще не нужны как сущности
_SKIP = frozenset()


def compute_visible(world, team: int) -> set[int]:
    """Множество id сущностей, видимых команде.

    Используется пространственный индекс: обходим свои источники зрения и
    помечаем всех вокруг, вместо проверки каждого врага против каждого своего.
    """
    visible: set[int] = set()
    sources = []
    for u in world.units.values():
        if u.team != team:
            continue
        visible.add(u.id)
        if u.alive:
            sources.append(u)

    truesight = [u for u in sources if u.flags & F_TRUESIGHT]

    for src in sources:
        radius = src.vision
        if radius <= 0:
            continue
        for other in world.spatial.query(src.x, src.y, radius):
            if other.id in visible:
                continue
            if dist_sq(src.x, src.y, other.x, other.y) > radius * radius:
                continue
            if other.flags & F_INVISIBLE:
                # Невидимку выдаёт только истинное зрение рядом
                if not any(dist_sq(t.x, t.y, other.x, other.y) <= t.vision * t.vision
                           for t in truesight):
                    continue
            visible.add(other.id)

    # Разрушенные вражеские строения показываем всегда — руины не прячутся
    for u in world.units.values():
        if u.is_building:
            visible.add(u.id)
    return visible


def unit_static(u) -> dict:
    """Неизменные данные юнита — шлются один раз."""
    d = {
        "id": u.id,
        "e": u.etype,
        "team": u.team,
        "n": u.name,
        "r": round(u.radius),
        # Настоящий радиус обзора: клиент рисует туман ровно по нему,
        # иначе картинка расходится с тем, что сервер считает видимым
        "vis": round(u.vision),
    }
    if u.etype in (E_HERO, E_ILLUSION):
        d["hero"] = u.hero_key
        if getattr(u, "player_id", 0):
            d["pid"] = u.player_id
        if getattr(u, "is_bot", False):
            d["bot"] = 1
    elif u.is_building:
        d["kind"] = u.kind
        d["tier"] = u.tier
        d["lane"] = u.lane
    else:
        d["ck"] = getattr(u, "creep_key", "")
    return d


def unit_dynamic(u) -> list:
    """Меняющиеся числа. Компактный список, а не словарь — экономит трафик."""
    return [
        u.id,
        round(u.x),
        round(u.y),
        round(u.facing * 57.2958),          # градусы целыми
        round(u.hp),
        round(u.max_hp),
        round(u.mana),
        round(u.max_mana),
        u.flags,
        getattr(u, "level", 0),
        1 if u.alive else 0,
    ]


def hero_detail(h, world) -> dict:
    """Полная панель своего героя: способности, предметы, экономика."""
    from . import content as C
    cur = C.xp_for_level(h.level)
    nxt = C.xp_for_level(h.level + 1)
    return {
        "id": h.id,
        "lvl": h.level,
        "xp": round(h.xp),
        "xp0": cur,
        "xp1": nxt,
        "gold": round(h.gold),
        "ap": h.ability_points,
        "kda": [h.kills, h.deaths, h.assists],
        "lh": h.last_hits,
        "dn": h.denies,
        "hp": round(h.hp), "mhp": round(h.max_hp),
        "mana": round(h.mana), "mmana": round(h.max_mana),
        "hpreg": round(h.hp_regen, 1), "manareg": round(h.mana_regen, 1),
        "str": round(h._attributes(h._stat_cache())[0]),
        "agi": round(h._attributes(h._stat_cache())[1]),
        "int": round(h._attributes(h._stat_cache())[2]),
        "primary": h.primary,
        "dmg": [round(h.damage_min), round(h.damage_max)],
        "armor": round(h.armor, 1),
        "mres": round(h.magic_resist * 100),
        "ms": round(h.move_speed),
        "arange": round(h.attack_range),
        "as": round(h.attack_speed),
        "abil": [a.to_wire() for a in h.abilities],
        "items": [it.to_wire() if it else None for it in h.items],
        "back": [it.to_wire() if it else None for it in h.backpack],
        "mods": [m.to_wire() for m in h.modifiers if not m.is_aura_effect],
        "resp": round(h.respawn_timer, 1),
        "alive": 1 if h.alive else 0,
        "deliv": [{"k": d["key"], "t": round(d["t"], 1)} for d in h.deliveries],
        "bbcost": round(world.buyback_cost(h)),
        "bbcd": round(h.buyback_cooldown, 1),
        "glyph": round(world.teams[h.team].glyph_cooldown, 1),
    }


class ClientView:
    """Что конкретный клиент уже знает. Нужен для дельт."""

    __slots__ = ("team", "known", "last_dyn")

    def __init__(self, team: int) -> None:
        self.team = team
        self.known: set[int] = set()
        self.last_dyn: dict[int, list] = {}

    def reset(self) -> None:
        self.known.clear()
        self.last_dyn.clear()

    def build(self, world, hero=None) -> dict:
        visible = compute_visible(world, self.team)

        new_units: list[dict] = []
        dyn: list[list] = []
        for uid in visible:
            u = world.units.get(uid)
            if u is None:
                continue
            if uid not in self.known:
                self.known.add(uid)
                new_units.append(unit_static(u))
            d = unit_dynamic(u)
            if self.last_dyn.get(uid) != d:
                self.last_dyn[uid] = d
                dyn.append(d)

        gone = [uid for uid in self.known if uid not in visible or uid not in world.units]
        for uid in gone:
            self.known.discard(uid)
            self.last_dyn.pop(uid, None)

        msg = {
            "t": "s",
            "tick": world.tick_count,
            "time": round(world.time, 2),
            "u": dyn,
            "p": [[p.id, round(p.x), round(p.y), p.visual, p.team]
                  for p in world.projectiles],
        }
        if new_units:
            msg["new"] = new_units
        if gone:
            msg["gone"] = gone
        if hero is not None:
            msg["me"] = hero_detail(hero, world)
        return msg


def scoreboard(world) -> dict:
    from .consts import TEAM_DEV, TEAM_MGMT, TEAM_NAMES
    rows = {TEAM_DEV: [], TEAM_MGMT: []}
    for h in world.heroes.values():
        if h.etype != E_HERO:
            continue
        rows[h.team].append({
            "id": h.id, "n": h.name, "hero": h.hero_key, "lvl": h.level,
            "k": h.kills, "d": h.deaths, "a": h.assists, "lh": h.last_hits,
            "gold": round(h.gold), "net": round(h.total_gold_earned),
            "bot": 1 if h.is_bot else 0,
            "items": [it.key if it else None for it in h.items],
            "alive": 1 if h.alive else 0, "resp": round(h.respawn_timer, 1),
            "hdmg": round(h.hero_damage), "heal": round(h.healing_done),
        })
    return {
        "teams": {
            str(TEAM_DEV): {"name": TEAM_NAMES[TEAM_DEV],
                            "score": sum(r["k"] for r in rows[TEAM_DEV]),
                            "players": rows[TEAM_DEV]},
            str(TEAM_MGMT): {"name": TEAM_NAMES[TEAM_MGMT],
                             "score": sum(r["k"] for r in rows[TEAM_MGMT]),
                             "players": rows[TEAM_MGMT]},
        },
        "time": round(world.time, 1),
    }


def static_map() -> dict:
    """Геометрия карты — шлётся один раз при входе."""
    from . import gamemap as gm
    return {
        "size": gm.SIZE,
        "walls": [[round(a), round(b), round(c), round(d)] for a, b, c, d in gm.WALL_RECTS],
        "lanes": {k: [[round(x), round(y)] for x, y in v]
                  for k, v in gm.LANE_PATHS.items()},
        "river": [[round(x), round(y)] for x, y in gm.RIVER_PATH],
        "bases": {str(t): [round(v) for v in r] for t, r in gm.BASE_RECT.items()},
        "fountains": {str(t): [round(p[0]), round(p[1])]
                      for t, p in gm.FOUNTAIN_POS.items()},
        "camps": [[t, s, round(p[0]), round(p[1])] for t, s, p in gm.CAMPS],
        "roshan": [round(gm.ROSHAN_POS[0]), round(gm.ROSHAN_POS[1])],
        "runes": [[round(x), round(y)] for x, y in gm.POWER_RUNE_POS],
        "bounty": [[round(x), round(y)] for x, y in gm.BOUNTY_RUNE_POS],
        "shops": [[round(x), round(y)] for x, y in gm.SECRET_SHOP_POS],
    }
