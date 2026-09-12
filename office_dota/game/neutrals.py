"""Лес, Легаси и руны.

Вынесено из world.py, чтобы тот не разрастался: это самостоятельная
подсистема со своими таймерами, которая общается с миром через несколько
понятных вызовов.
"""
from __future__ import annotations

import math

from . import content as C, gamemap as gm, vmath
from .consts import (
    E_RUNE, TEAM_DEV, TEAM_MGMT, TEAM_NEUTRAL, enemy_of,
)
from .entities import Creep, Unit
from .modifiers import Modifier

RUNE_PICKUP_RADIUS = 160.0
ROSHAN_CAMP_ID = -100


class CampState:
    __slots__ = ("cid", "size", "x", "y", "alive_ids", "respawn_at", "spawned_once")

    def __init__(self, cid: int, size: str, x: float, y: float) -> None:
        self.cid = cid
        self.size = size
        self.x, self.y = x, y
        self.alive_ids: set[int] = set()
        self.respawn_at = 0.0
        self.spawned_once = False


class RuneSpot:
    __slots__ = ("kind", "x", "y", "entity_id", "next_spawn")

    def __init__(self, kind: str, x: float, y: float, first: float) -> None:
        self.kind = kind
        self.x, self.y = x, y
        self.entity_id = 0
        self.next_spawn = first


class Rune(Unit):
    """Руна на земле. Технически юнит, чтобы попадать в снапшот и туман,
    но неатакуемый — цели её не выбирают."""

    __slots__ = ("rune_kind",)

    def __init__(self, eid: int, x: float, y: float, kind: str, name: str) -> None:
        Unit.__init__(self, eid, E_RUNE, TEAM_NEUTRAL, x, y, radius=30.0, name=name)
        self.rune_kind = kind
        self.can_be_attacked = False
        self.base_max_hp = 1.0
        self.base_move_speed = 0.0
        self.base_vision_day = 0.0
        self.recompute()
        self.hp = 1.0


class Neutrals:
    """Все нейтральные обитатели карты и руны."""

    def __init__(self, world) -> None:
        self.world = world
        self.camps: list[CampState] = []
        for i, (_team, size, (x, y)) in enumerate(gm.CAMPS):
            self.camps.append(CampState(i, size, x, y))
        self.roshan = CampState(ROSHAN_CAMP_ID, "roshan", *gm.ROSHAN_POS)

        rune_cfg = C.RUNES or {}
        power = rune_cfg.get("power", {})
        bounty = rune_cfg.get("bounty", {})
        self.power_first = float(power.get("first_spawn_sec", 180.0))
        self.power_interval = float(power.get("interval_sec", 120.0))
        self.bounty_first = float(bounty.get("first_spawn_sec", 0.0))
        self.bounty_interval = float(bounty.get("interval_sec", 120.0))
        self.power_types = list((power.get("types") or {}).items())

        self.spots: list[RuneSpot] = []
        for (x, y) in gm.POWER_RUNE_POS:
            self.spots.append(RuneSpot("power", x, y, self.power_first))
        for (x, y) in gm.BOUNTY_RUNE_POS:
            self.spots.append(RuneSpot("bounty", x, y, self.bounty_first))

        self._camp_first = 30.0     # лес открывается не с нулевой секунды

    # ------------------------------------------------------------------
    def tick(self, dt: float) -> None:
        w = self.world
        for camp in self.camps:
            self._tick_camp(camp, self._camp_cfg(camp.size))
        self._tick_camp(self.roshan, C.JUNGLE.get("roshan", {}))
        self._tick_runes()

    def _camp_cfg(self, size: str) -> dict:
        return C.JUNGLE.get(size, {})

    def _tick_camp(self, camp: CampState, cfg: dict) -> None:
        if not cfg:
            return
        w = self.world
        camp.alive_ids = {i for i in camp.alive_ids
                          if (u := w.units.get(i)) is not None and u.alive}
        if camp.alive_ids:
            return
        if not camp.spawned_once:
            first = float(cfg.get("first_spawn_sec", self._camp_first))
            if w.time < first:
                return
            camp.spawned_once = True
        elif w.time < camp.respawn_at:
            return
        self._spawn_camp(camp, cfg)

    def _spawn_camp(self, camp: CampState, cfg: dict) -> None:
        w = self.world
        variants = cfg.get("variants") or []
        if not variants:
            return
        variant = variants[w.rng.randrange(len(variants))]
        scaling = cfg.get("scaling") or {}
        minutes = w.time / 60.0
        idx = 0
        for spec in variant.get("units", []):
            for _ in range(int(spec.get("count", 1))):
                ang = (idx / 5.0) * math.tau
                dx, dy = vmath.from_angle(ang, 70.0)
                x, y = gm.nearest_walkable(camp.x + dx, camp.y + dy)
                c = Creep(w.next_id(), TEAM_NEUTRAL, x, y, spec.get("key", "neutral"),
                          name=spec.get("name", "Нейтрал"))
                c.base_max_hp = float(spec["hp"]) + float(scaling.get("per_min_hp", 0)) * minutes
                c.base_damage_min, c.base_damage_max = [
                    float(v) + float(scaling.get("per_min_damage", 0)) * minutes
                    for v in spec["damage"]]
                c.base_armor = float(spec.get("armor", 0))
                c.base_magic_resist = float(spec.get("magic_resist", 0))
                c.base_attack_range = float(spec.get("attack_range", 100))
                c.base_bat = float(spec.get("bat", 1.4))
                c.base_move_speed = float(spec.get("move_speed", 300))
                c.base_vision_day = float(spec.get("vision", 800))
                c.bounty_gold = w.rng.uniform(*spec.get("bounty_gold", [40, 50]))
                c.bounty_xp = float(spec.get("bounty_xp", 40))
                c.innate_bash_chance = float(spec.get("bash_chance", 0.0))
                c.innate_bash_duration = float(spec.get("bash_duration", 0.0))
                c.is_ranged = c.base_attack_range > 200
                c.camp_id = camp.cid
                c.spawn_x, c.spawn_y = camp.x, camp.y
                c.leash_radius = 1100.0
                c.attack_point = 0.3
                c.recompute()
                c.hp = c.max_hp
                w.register(c)
                camp.alive_ids.add(c.id)
                idx += 1

        rs = cfg.get("respawn_sec", 45.0)
        if isinstance(rs, (list, tuple)):
            rs = w.rng.uniform(float(rs[0]), float(rs[1]))
        camp.respawn_at = w.time + float(rs)

    def on_camp_unit_died(self, unit: Creep) -> None:
        for camp in (*self.camps, self.roshan):
            if unit.id in camp.alive_ids:
                camp.alive_ids.discard(unit.id)
                if camp.cid == ROSHAN_CAMP_ID and not camp.alive_ids:
                    self.world.emit("roshan_down", at=round(self.world.time))
                break

    # ------------------------------------------------------------------
    def _tick_runes(self) -> None:
        w = self.world
        for spot in self.spots:
            ent = w.units.get(spot.entity_id) if spot.entity_id else None
            if ent is not None and ent.alive:
                self._check_pickup(spot, ent)
                continue
            spot.entity_id = 0
            if w.time < spot.next_spawn:
                continue
            self._spawn_rune(spot)

    def _spawn_rune(self, spot: RuneSpot) -> None:
        w = self.world
        if spot.kind == "bounty":
            kind, name = "bounty", "Премия"
        else:
            if not self.power_types:
                return
            # Как в доте: две руны силы на карте всегда разных типов
            taken = {r.rune_kind for r in (w.units.get(s2.entity_id)
                                           for s2 in self.spots if s2.kind == "power")
                     if isinstance(r, Rune) and r.alive}
            choices = [t for t in self.power_types if t[0] not in taken] or self.power_types
            key, cfg = choices[w.rng.randrange(len(choices))]
            kind, name = key, cfg.get("name", key)
        r = Rune(w.next_id(), spot.x, spot.y, kind, name)
        w.register(r)
        spot.entity_id = r.id
        spot.next_spawn = w.time + (self.bounty_interval if spot.kind == "bounty"
                                    else self.power_interval)
        w.emit("rune", id=r.id, k=kind, x=round(spot.x), y=round(spot.y))

    def _check_pickup(self, spot: RuneSpot, ent: Rune) -> None:
        w = self.world
        for h in w.heroes.values():
            if not h.alive or h.etype != "hero":
                continue
            if vmath.dist_sq(h.x, h.y, ent.x, ent.y) > RUNE_PICKUP_RADIUS ** 2:
                continue
            self.apply_rune(h, ent.rune_kind)
            ent.alive = False
            w.units.pop(ent.id, None)
            spot.entity_id = 0
            w.emit("rune_taken", id=h.id, k=ent.rune_kind, name=ent.name)
            return

    def apply_rune(self, hero, kind: str) -> None:
        w = self.world
        if kind == "bounty":
            cfg = (C.RUNES.get("bounty") or {})
            minutes = w.time / 60.0
            gold = float(cfg.get("gold_base", 80)) + float(cfg.get("gold_per_min", 20)) * minutes
            xp = float(cfg.get("xp_base", 40)) + float(cfg.get("xp_per_min", 10)) * minutes
            w.grant_gold(hero, gold, "bounty_rune")
            w.grant_xp(hero, xp)
            return

        types = (C.RUNES.get("power") or {}).get("types") or {}
        cfg = types.get(kind) or {}
        dur = float(cfg.get("duration", 30.0))
        eff = cfg.get("effect") or {}
        name = cfg.get("name", kind)

        if kind == "double_damage":
            hero.ensure_stats()
            bonus = hero.base_damage_max * (float(eff.get("damage_mult", 2.0)) - 1.0)
            hero.add_modifier(Modifier("rune_dd", dur, name=name,
                                       stats={"damage": bonus}, visual="rune_dd"))
        elif kind == "haste":
            hero.add_modifier(Modifier("rune_haste", dur, name=name,
                                       stats={"move_speed_pct": 100.0}, visual="rune_haste"))
        elif kind == "regeneration":
            pct = float(eff.get("hp_regen_pct_per_sec", 0.06))
            hero.add_modifier(Modifier(
                "rune_regen", dur, name=name, visual="rune_regen",
                tick_interval=0.5,
                tick_effects=[{"op": "heal", "amount": hero.max_hp * pct * 0.5,
                               "target": "hit"}],
                stats={"mana_regen": hero.max_mana * pct}))
        elif kind == "invisibility":
            from .consts import F_INVISIBLE
            hero.add_modifier(Modifier("rune_invis", dur, name=name,
                                       flags=F_INVISIBLE, dispellable=False,
                                       visual="rune_invis"))
        elif kind == "arcane":
            hero.add_modifier(Modifier("rune_arcane", dur, name=name,
                                       stats={"cooldown_reduction": 30.0,
                                              "mana_regen": 8.0}, visual="rune_arcane"))
        elif kind == "illusion":
            w.spawn_illusions(hero, 2, dur, 35.0, 300.0)
        else:
            hero.add_modifier(Modifier(f"rune_{kind}", dur, name=name, visual="rune"))
