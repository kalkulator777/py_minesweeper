"""Сущности мира: юниты, герои, крипы, строения, снаряды.

Характеристики считаются лениво. Любое изменение (модификатор, предмет,
уровень) поднимает флаг _stats_dirty, пересчёт происходит при первом
обращении к производной характеристике.
"""
from __future__ import annotations

import math

from . import vmath
from .consts import (
    ATTACK_RANGE_BUFFER, BASE_MAGIC_RESIST, DEFAULT_BAT, E_ANCIENT, E_BARRACKS,
    E_CREEP, E_FOUNTAIN, E_HERO, E_ILLUSION, E_NEUTRAL, E_PROJECTILE, E_SUMMON,
    E_TOWER, E_WARD, F_INVISIBLE, F_TAUNTED,
    HP_PER_STR, HP_REGEN_PER_STR, ARMOR_PER_AGI, ATTACK_SPEED_PER_AGI,
    MANA_PER_INT, MANA_REGEN_PER_INT, SPELL_AMP_PER_INT,
    MAX_MOVE_SPEED, MIN_MOVE_SPEED, ORDER_ATTACK_MOVE, ORDER_ATTACK_UNIT,
    ORDER_CAST, ORDER_HOLD, ORDER_MOVE, ORDER_NONE, ORDER_STOP,
    TURN_RATE_DEFAULT, UNIVERSAL_DAMAGE_PER_STAT, CANNOT_MOVE, CANNOT_ATTACK,
    ITEM_SLOTS, BACKPACK_SLOTS, BUILDING_TYPES,
)
from .modifiers import ModifierHost, STAT_KEYS

_MULTIPLICATIVE = ("magic_resist", "evasion", "status_resist")


def mul_stat(out: dict[str, float], key: str, pct: float) -> None:
    """Добавляет мультипликативный источник сопротивления в накопитель."""
    frac = pct / 100.0 if abs(pct) > 1.0 else pct
    out[key] = out.get(key, 1.0) * (1.0 - frac)


def add_stat(out: dict[str, float], key: str, value: float) -> None:
    if key in _MULTIPLICATIVE:
        mul_stat(out, key, value)
    elif key == "all_stats":
        out["str"] = out.get("str", 0.0) + value
        out["agi"] = out.get("agi", 0.0) + value
        out["int"] = out.get("int", 0.0) + value
    else:
        out[key] = out.get(key, 0.0) + value


class Entity:
    __slots__ = ("id", "etype", "team", "x", "y", "facing", "radius", "alive", "world", "name")

    def __init__(self, eid: int, etype: str, team: int, x: float, y: float,
                 radius: float = 24.0, name: str = "") -> None:
        self.id = eid
        self.etype = etype
        self.team = team
        self.x = x
        self.y = y
        self.facing = 0.0
        self.radius = radius
        self.alive = True
        self.world = None
        self.name = name

    def dist_to(self, other) -> float:
        return vmath.dist(self.x, self.y, other.x, other.y)

    def dist_sq_to(self, other) -> float:
        return vmath.dist_sq(self.x, self.y, other.x, other.y)


class Unit(Entity, ModifierHost):
    """Всё, что имеет здоровье, может атаковать и получать приказы."""

    __slots__ = (
        "modifiers", "_stats_dirty", "flags",
        # базовые характеристики
        "base_max_hp", "base_max_mana", "base_hp_regen", "base_mana_regen",
        "base_damage_min", "base_damage_max", "base_armor", "base_magic_resist",
        "base_move_speed", "base_attack_range", "base_bat",
        "base_vision_day", "base_vision_night",
        # производные
        "max_hp", "max_mana", "hp_regen", "mana_regen",
        "damage_min", "damage_max", "armor", "magic_resist", "evasion",
        "status_resist", "move_speed", "attack_range", "bat", "attack_speed",
        "spell_amp", "cooldown_reduction", "damage_taken_mult", "heal_taken_mult",
        "vision", "crit_chance", "crit_mult", "lifesteal", "cleave_pct", "cleave_radius",
        "bash_chance", "bash_duration",
        # текущее состояние
        "hp", "mana",
        # приказы
        "order", "order_x", "order_y", "order_target_id", "path", "path_idx",
        "pending_cast",
        # атака
        "attack_cd", "attack_windup", "attack_target_id", "turn_rate",
        "is_ranged", "projectile_speed", "attack_point",
        # прочее
        "bounty_gold", "bounty_xp", "last_attacker_id", "last_attacked_time",
        "taunt_source_id", "owner_id", "can_be_attacked", "is_building",
        "attack_procs", "on_kill_procs", "on_damaged_procs",
    )

    def __init__(self, eid: int, etype: str, team: int, x: float, y: float,
                 radius: float = 24.0, name: str = "") -> None:
        Entity.__init__(self, eid, etype, team, x, y, radius, name)
        self.modifiers = []
        self._stats_dirty = True
        self.flags = 0

        self.base_max_hp = 200.0
        self.base_max_mana = 0.0
        self.base_hp_regen = 0.0
        self.base_mana_regen = 0.0
        self.base_damage_min = 10.0
        self.base_damage_max = 12.0
        self.base_armor = 0.0
        self.base_magic_resist = 0.0
        self.base_move_speed = 300.0
        self.base_attack_range = 150.0
        self.base_bat = DEFAULT_BAT
        self.base_vision_day = 1200.0
        self.base_vision_night = 800.0

        self.max_hp = 200.0
        self.max_mana = 0.0
        self.hp_regen = 0.0
        self.mana_regen = 0.0
        self.damage_min = 10.0
        self.damage_max = 12.0
        self.armor = 0.0
        self.magic_resist = 0.0
        self.evasion = 0.0
        self.status_resist = 0.0
        self.move_speed = 300.0
        self.attack_range = 150.0
        self.bat = DEFAULT_BAT
        self.attack_speed = 100.0
        self.spell_amp = 0.0
        self.cooldown_reduction = 0.0
        self.damage_taken_mult = 1.0
        self.heal_taken_mult = 1.0
        self.vision = 1200.0
        self.crit_chance = 0.0
        self.crit_mult = 1.0
        self.lifesteal = 0.0
        self.cleave_pct = 0.0
        self.cleave_radius = 0.0
        self.bash_chance = 0.0
        self.bash_duration = 0.0

        self.hp = 200.0
        self.mana = 0.0

        self.order = ORDER_NONE
        self.order_x = x
        self.order_y = y
        self.order_target_id = 0
        self.path = []
        self.path_idx = 0
        self.pending_cast = None

        self.attack_cd = 0.0
        self.attack_windup = 0.0
        self.attack_target_id = 0
        self.attack_point = 0.35
        self.turn_rate = TURN_RATE_DEFAULT
        self.is_ranged = False
        self.projectile_speed = 900.0

        self.bounty_gold = 0.0
        self.bounty_xp = 0.0
        self.last_attacker_id = 0
        self.last_attacked_time = -999.0
        self.taunt_source_id = 0
        self.owner_id = 0
        self.can_be_attacked = True
        self.is_building = etype in BUILDING_TYPES

        self.attack_procs = []
        self.on_kill_procs = []
        self.on_damaged_procs = []

    # --- пересчёт характеристик -------------------------------------------
    def on_modifier_changed(self) -> None:
        self._stats_dirty = True

    def collect_extra_stats(self, out: dict[str, float]) -> int:
        """Вклад предметов и пассивок. Базовый юнит их не имеет."""
        return 0

    def ensure_stats(self) -> None:
        if self._stats_dirty:
            self.recompute()

    def recompute(self) -> None:
        self._stats_dirty = False
        st: dict[str, float] = {}
        flags = self.aggregate_stats(st)
        flags |= self.collect_extra_stats(st)
        self.flags = flags

        bonus_str, bonus_agi, bonus_int = self._attributes(st)

        self.max_hp = max(1.0, (self.base_max_hp + bonus_str * HP_PER_STR
                                + st.get("hp", 0.0))
                          * (1.0 + st.get("max_hp_pct", 0.0) / 100.0))
        self.max_mana = max(0.0, (self.base_max_mana + bonus_int * MANA_PER_INT
                                  + st.get("mana", 0.0))
                            * (1.0 + st.get("max_mana_pct", 0.0) / 100.0))

        self.hp_regen = ((self.base_hp_regen + bonus_str * HP_REGEN_PER_STR
                          + st.get("hp_regen", 0.0))
                         * (1.0 + st.get("hp_regen_pct", 0.0) / 100.0))
        self.mana_regen = ((self.base_mana_regen + bonus_int * MANA_REGEN_PER_INT
                            + st.get("mana_regen", 0.0))
                           * (1.0 + st.get("mana_regen_pct", 0.0) / 100.0))

        dmg_bonus = st.get("damage", 0.0) + self._primary_damage(bonus_str, bonus_agi, bonus_int)
        self.damage_min = max(0.0, self.base_damage_min + dmg_bonus)
        self.damage_max = max(0.0, self.base_damage_max + dmg_bonus)

        self.armor = self.base_armor + bonus_agi * ARMOR_PER_AGI + st.get("armor", 0.0)

        mr_rem = st.get("magic_resist", 1.0) * (1.0 - self.base_magic_resist)
        self.magic_resist = 1.0 - mr_rem
        self.evasion = 1.0 - st.get("evasion", 1.0)
        self.status_resist = 1.0 - st.get("status_resist", 1.0)

        ms = (self.base_move_speed + st.get("move_speed", 0.0)) * \
             (1.0 + st.get("move_speed_pct", 0.0) / 100.0)
        self.move_speed = min(MAX_MOVE_SPEED, max(MIN_MOVE_SPEED, ms))

        self.attack_range = self.base_attack_range + st.get("attack_range", 0.0)
        self.bat = self.base_bat * (1.0 + st.get("bat_pct", 0.0) / 100.0)
        self.attack_speed = 100.0 + bonus_agi * ATTACK_SPEED_PER_AGI + st.get("attack_speed", 0.0)

        self.spell_amp = st.get("spell_amp", 0.0) / 100.0 + bonus_int * SPELL_AMP_PER_INT
        self.cooldown_reduction = min(0.8, st.get("cooldown_reduction", 0.0) / 100.0)
        self.damage_taken_mult = max(0.0, 1.0 + st.get("damage_taken_pct", 0.0) / 100.0)

        self.vision = self.base_vision_day + st.get("vision_day", 0.0)

        self.crit_chance = min(1.0, st.get("_crit_chance", 0.0))
        self.crit_mult = max(1.0, st.get("_crit_mult", 1.0))
        self.lifesteal = st.get("_lifesteal", 0.0)
        self.cleave_pct = st.get("_cleave_pct", 0.0)
        self.cleave_radius = st.get("_cleave_radius", 0.0)
        self.bash_chance = st.get("_bash_chance", 0.0)
        self.bash_duration = st.get("_bash_duration", 0.0)

        if self.hp > self.max_hp:
            self.hp = self.max_hp
        if self.mana > self.max_mana:
            self.mana = self.max_mana
        self.refresh_triggers()

    def refresh_triggers(self) -> None:
        """Пересобирает срабатывания от предметов и пассивок. У простых юнитов пусто."""
        pass

    def _attributes(self, st: dict[str, float]) -> tuple[float, float, float]:
        """Итоговые атрибуты. У обычных юнитов атрибутов нет."""
        return 0.0, 0.0, 0.0

    def _primary_damage(self, s: float, a: float, i: float) -> float:
        return 0.0

    # --- состояние ---------------------------------------------------------
    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def mana_pct(self) -> float:
        return self.mana / self.max_mana if self.max_mana > 0 else 1.0

    @property
    def can_move(self) -> bool:
        return not (self.flags & CANNOT_MOVE) and self.move_speed > 0.0

    @property
    def can_attack(self) -> bool:
        return not (self.flags & CANNOT_ATTACK)

    def is_visible_to(self, team: int) -> bool:
        if self.team == team:
            return True
        return not (self.flags & F_INVISIBLE)

    def scaled_duration(self, duration: float) -> float:
        """Сокращает длительность контроля на сопротивление статусу."""
        return duration * (1.0 - self.status_resist)

    # --- приказы -----------------------------------------------------------
    def clear_order(self) -> None:
        self.order = ORDER_NONE
        self.order_target_id = 0
        self.path = []
        self.path_idx = 0
        self.pending_cast = None

    def order_move_to(self, x: float, y: float, path: list) -> None:
        self.order = ORDER_MOVE
        self.order_x = x
        self.order_y = y
        self.order_target_id = 0
        self.path = path
        self.path_idx = 0
        self.pending_cast = None

    def order_attack(self, target_id: int) -> None:
        self.order = ORDER_ATTACK_UNIT
        self.order_target_id = target_id
        self.path = []
        self.path_idx = 0
        self.pending_cast = None

    def order_attack_move(self, x: float, y: float, path: list) -> None:
        self.order = ORDER_ATTACK_MOVE
        self.order_x = x
        self.order_y = y
        self.order_target_id = 0
        self.path = path
        self.path_idx = 0
        self.pending_cast = None

    def order_hold(self) -> None:
        self.order = ORDER_HOLD
        self.path = []
        self.pending_cast = None

    def order_stop(self) -> None:
        self.clear_order()
        self.order = ORDER_STOP
        self.attack_target_id = 0
        self.attack_windup = 0.0

    # --- движение ----------------------------------------------------------
    def step_towards(self, tx: float, ty: float, dt: float) -> bool:
        """Шаг к точке с разворотом. True — дошли."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return True
        target_facing = math.atan2(dy, dx)
        self.facing = vmath.rotate_towards(self.facing, target_facing, self.turn_rate * dt)
        # Пока не развернулись хотя бы примерно — не едем боком
        if abs(vmath.angle_diff(self.facing, target_facing)) > 0.9:
            return False
        step = self.move_speed * dt
        if d <= step:
            self.x, self.y = tx, ty
            return True
        inv = step / d
        self.x += dx * inv
        self.y += dy * inv
        return False

    def face_towards(self, tx: float, ty: float, dt: float) -> bool:
        dx, dy = tx - self.x, ty - self.y
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return True
        target = math.atan2(dy, dx)
        self.facing = vmath.rotate_towards(self.facing, target, self.turn_rate * dt)
        return abs(vmath.angle_diff(self.facing, target)) < 0.15

    def in_attack_range(self, target) -> bool:
        reach = self.attack_range + self.radius + target.radius + ATTACK_RANGE_BUFFER
        return self.dist_sq_to(target) <= reach * reach

    # --- хуки --------------------------------------------------------------
    def on_damaged(self, attacker, amount: float, dtype: str, source: str,
                   ability_key: str) -> None:
        if attacker is not None:
            self.last_attacker_id = attacker.id

    def on_death(self, killer) -> None:
        pass


class Hero(Unit):
    """Герой: атрибуты, уровни, способности, предметы, золото."""

    __slots__ = (
        "hero_key", "player_id", "level", "xp", "ability_points",
        "primary", "base_str", "base_agi", "base_int",
        "str_gain", "agi_gain", "int_gain",
        "abilities", "items", "backpack", "stash",
        "gold", "reliable_gold", "total_gold_earned",
        "kills", "deaths", "assists", "last_hits", "denies",
        "respawn_timer", "buyback_cooldown", "kill_streak", "death_streak",
        "is_bot", "assist_credit", "deliveries",
        "hero_damage", "tower_damage", "healing_done",
    )

    def __init__(self, eid: int, team: int, x: float, y: float, hero_key: str,
                 name: str = "") -> None:
        Unit.__init__(self, eid, E_HERO, team, x, y, radius=28.0, name=name)
        self.hero_key = hero_key
        self.player_id = 0
        self.level = 1
        self.xp = 0.0
        self.ability_points = 1
        self.primary = "str"
        self.base_str = 20.0
        self.base_agi = 20.0
        self.base_int = 20.0
        self.str_gain = 2.0
        self.agi_gain = 2.0
        self.int_gain = 2.0
        self.base_magic_resist = BASE_MAGIC_RESIST

        self.abilities = []
        self.items = [None] * ITEM_SLOTS
        self.backpack = [None] * BACKPACK_SLOTS
        self.stash = []

        self.gold = 0.0
        self.reliable_gold = 0.0
        self.total_gold_earned = 0.0
        self.kills = 0
        self.deaths = 0
        self.assists = 0
        self.last_hits = 0
        self.denies = 0
        self.respawn_timer = 0.0
        self.buyback_cooldown = 0.0
        self.kill_streak = 0
        self.death_streak = 0
        self.is_bot = False
        self.assist_credit = {}
        self.deliveries = []
        self.hero_damage = 0.0
        self.tower_damage = 0.0
        self.healing_done = 0.0

    def _attributes(self, st: dict[str, float]) -> tuple[float, float, float]:
        lv = self.level - 1
        s = self.base_str + self.str_gain * lv + st.get("str", 0.0)
        a = self.base_agi + self.agi_gain * lv + st.get("agi", 0.0)
        i = self.base_int + self.int_gain * lv + st.get("int", 0.0)
        return s, a, i

    def _primary_damage(self, s: float, a: float, i: float) -> float:
        if self.primary == "str":
            return s
        if self.primary == "agi":
            return a
        if self.primary == "int":
            return i
        return (s + a + i) * UNIVERSAL_DAMAGE_PER_STAT

    @property
    def strength(self) -> float:
        self.ensure_stats()
        return self._attributes(self._stat_cache())[0]

    def _stat_cache(self) -> dict[str, float]:
        st: dict[str, float] = {}
        self.aggregate_stats(st)
        self.collect_extra_stats(st)
        return st

    def collect_extra_stats(self, out: dict[str, float]) -> int:
        flags = 0
        for it in self.items:
            if it is None:
                continue
            flags |= it.contribute(out)
        for ab in self.abilities:
            if ab.level > 0:
                flags |= ab.contribute_passive(out)
        return flags

    def refresh_triggers(self) -> None:
        from .abilities import attack_procs, triggered
        procs: list = []
        on_kill: list = []
        on_dmg: list = []
        for it in self.items:
            if it is None:
                continue
            eff = it.defn.get("passives") or []
            procs += attack_procs(eff, 1)
            for e in triggered(eff, "on_kill"):
                on_kill.append(e)
            for e in triggered(eff, "on_take_damage"):
                on_dmg.append((e, it.defn))
        for ab in self.abilities:
            if ab.level <= 0:
                continue
            eff = ab.defn.get("effects") or []
            procs += attack_procs(eff, ab.level)
            for e in triggered(eff, "on_kill"):
                on_kill.append(e)
            for e in triggered(eff, "on_take_damage"):
                on_dmg.append((e, ab.defn))
        self.attack_procs = procs
        self.on_kill_procs = on_kill
        self.on_damaged_procs = on_dmg

    def all_items(self):
        for it in self.items:
            if it is not None:
                yield it

    def has_item(self, key: str) -> bool:
        return any(it.key == key for it in self.all_items())

    def free_item_slot(self) -> int:
        for i, it in enumerate(self.items):
            if it is None:
                return i
        return -1

    def free_backpack_slot(self) -> int:
        for i, it in enumerate(self.backpack):
            if it is None:
                return i
        return -1


class Creep(Unit):
    """Линейный крип или нейтрал."""

    __slots__ = ("lane", "waypoints", "wp_idx", "creep_key", "is_neutral",
                 "camp_id", "spawn_x", "spawn_y", "leash_radius", "is_super")

    def __init__(self, eid: int, team: int, x: float, y: float, creep_key: str,
                 lane: str = "", name: str = "") -> None:
        etype = E_NEUTRAL if team == 2 else E_CREEP
        Unit.__init__(self, eid, etype, team, x, y, radius=22.0, name=name)
        self.creep_key = creep_key
        self.lane = lane
        self.waypoints = []
        self.wp_idx = 0
        self.is_neutral = team == 2
        self.camp_id = -1
        self.spawn_x = x
        self.spawn_y = y
        self.leash_radius = 900.0
        self.is_super = False


class Building(Unit):
    """Башня, бараки, трон, фонтан. Не двигается, может быть неуязвима."""

    __slots__ = ("lane", "tier", "kind", "invuln_until_alive", "backdoor_protected",
                 "team_bounty", "killer_bounty", "glyph_timer")

    def __init__(self, eid: int, etype: str, team: int, x: float, y: float,
                 kind: str, lane: str = "", tier: int = 0, name: str = "") -> None:
        radius = {E_TOWER: 60.0, E_BARRACKS: 80.0, E_ANCIENT: 130.0,
                  E_FOUNTAIN: 90.0}.get(etype, 60.0)
        Unit.__init__(self, eid, etype, team, x, y, radius=radius, name=name)
        self.kind = kind
        self.lane = lane
        self.tier = tier
        self.invuln_until_alive = []      # id строений, пока живо любое — это неуязвимо
        self.backdoor_protected = True
        self.team_bounty = 0.0
        self.killer_bounty = 0.0
        self.glyph_timer = 0.0
        self.turn_rate = 999.0
        self.base_move_speed = 0.0
        self.move_speed = 0.0
        self.is_building = True


class Projectile(Entity):
    """Летящий снаряд: автоатака дальнего юнита или снаряд способности."""

    __slots__ = ("source_id", "target_id", "tx", "ty", "speed", "on_hit",
                 "radius_hit", "pierce", "traveled", "max_dist", "hit_ids",
                 "is_attack", "attack_damage", "is_crit", "visual", "ability_key", "level")

    def __init__(self, eid: int, team: int, x: float, y: float, speed: float,
                 source_id: int, target_id: int = 0, tx: float = 0.0, ty: float = 0.0,
                 visual: str = "arrow") -> None:
        Entity.__init__(self, eid, E_PROJECTILE, team, x, y, radius=12.0)
        self.source_id = source_id
        self.target_id = target_id
        self.tx = tx
        self.ty = ty
        self.speed = speed
        self.on_hit = []
        self.radius_hit = 0.0
        self.pierce = False
        self.traveled = 0.0
        self.max_dist = 0.0
        self.hit_ids = set()
        self.is_attack = False
        self.attack_damage = 0.0
        self.is_crit = False
        self.visual = visual
        self.ability_key = ""
        self.level = 1
