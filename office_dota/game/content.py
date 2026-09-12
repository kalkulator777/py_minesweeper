"""Загрузка игрового контента.

Герои, предметы и числа баланса лежат в office_dota/game/data/ и пишутся
отдельно от движка. Модуль подхватывает их, если они есть, и подставляет
минимальные заглушки, если нет, — чтобы движок оставался запускаемым
и тестируемым независимо от готовности контента.
"""
from __future__ import annotations

import sys

# --- Герои -----------------------------------------------------------------
try:
    from .data.heroes import HEROES as _HEROES           # type: ignore
    HEROES_LOADED = True
except Exception as exc:                                  # noqa: BLE001
    print(f"[content] герои не загружены ({exc}), работаю на заглушке", file=sys.stderr)
    HEROES_LOADED = False
    _HEROES = {}

# --- Предметы --------------------------------------------------------------
try:
    from .data.items import ITEMS as _ITEMS, SHOP_LAYOUT as _SHOP  # type: ignore
    ITEMS_LOADED = True
except Exception as exc:                                  # noqa: BLE001
    print(f"[content] предметы не загружены ({exc}), работаю на заглушке", file=sys.stderr)
    ITEMS_LOADED = False
    _ITEMS, _SHOP = {}, {}

# --- Числа баланса ---------------------------------------------------------
try:
    from .data import tuning as _t                         # type: ignore
    TUNING_LOADED = True
except Exception as exc:                                  # noqa: BLE001
    print(f"[content] баланс не загружен ({exc}), работаю на заглушке", file=sys.stderr)
    TUNING_LOADED = False
    _t = None


# ==========================================================================
#  Заглушки — минимум, на котором игра запускается и тестируется
# ==========================================================================

_FALLBACK_HERO = {
    "key": "stub", "name": "Стажёр", "title": "Заглушка", "archetype": "—",
    "prototype": "—", "primary": "str", "attack_type": "melee",
    "attack_range": 150, "projectile_speed": 0, "bat": 1.7,
    "base_str": 22, "str_gain": 3.0, "base_agi": 18, "agi_gain": 2.0,
    "base_int": 18, "int_gain": 2.0, "base_damage": [26, 32], "base_armor": 2.0,
    "base_hp_regen": 0.5, "base_mana_regen": 0.9, "move_speed": 300,
    "vision_day": 1800, "vision_night": 800, "difficulty": 1, "roles": ["mid"],
    "lore": "Ещё не прошёл онбординг.",
    "abilities": [],
}

_FALLBACK_XP = [0]
_acc = 0
for _i in range(1, 25):
    _acc += int(160 + 90 * _i)
    _FALLBACK_XP.append(_acc)

_FALLBACK_CREEPS = {
    "melee_creep": {"name": "Стажёр", "hp": 550, "damage": [21, 24], "armor": 2,
                    "magic_resist": 0, "attack_range": 100, "bat": 1.0,
                    "move_speed": 325, "bounty_gold": [36, 46], "bounty_xp": 62,
                    "vision": 750},
    "ranged_creep": {"name": "Аналитик", "hp": 300, "damage": [23, 27], "armor": 0,
                     "magic_resist": 0, "attack_range": 500, "bat": 1.0,
                     "move_speed": 325, "bounty_gold": [46, 56], "bounty_xp": 76,
                     "vision": 750},
    "siege_creep": {"name": "Подрядчик", "hp": 875, "damage": [35, 44], "armor": 0,
                    "magic_resist": 0.5, "attack_range": 690, "bat": 3.0,
                    "move_speed": 325, "bounty_gold": [62, 74], "bounty_xp": 98,
                    "vision": 750},
    "super_melee": {"name": "Ведущий стажёр", "hp": 1000, "damage": [40, 46], "armor": 4,
                    "magic_resist": 0, "attack_range": 100, "bat": 1.0,
                    "move_speed": 335, "bounty_gold": [40, 50], "bounty_xp": 70,
                    "vision": 750},
    "super_ranged": {"name": "Ведущий аналитик", "hp": 550, "damage": [42, 50], "armor": 2,
                     "magic_resist": 0, "attack_range": 500, "bat": 1.0,
                     "move_speed": 335, "bounty_gold": [50, 60], "bounty_xp": 84,
                     "vision": 750},
}

_FALLBACK_BUILDINGS = {
    "tower_t1": {"name": "Кулер", "hp": 1800, "damage": [110, 120], "armor": 14,
                 "magic_resist": 0.4, "attack_range": 700, "bat": 1.0,
                 "team_bounty": 100, "killer_bounty": 160, "hp_regen": 0},
    "tower_t2": {"name": "Принтер", "hp": 2200, "damage": [122, 132], "armor": 16,
                 "magic_resist": 0.4, "attack_range": 700, "bat": 1.0,
                 "team_bounty": 120, "killer_bounty": 180, "hp_regen": 4},
    "tower_t3": {"name": "Кофемашина", "hp": 2600, "damage": [138, 148], "armor": 18,
                 "magic_resist": 0.4, "attack_range": 700, "bat": 1.0,
                 "team_bounty": 140, "killer_bounty": 200, "hp_regen": 6},
    "tower_t4": {"name": "Турникет", "hp": 2600, "damage": [152, 162], "armor": 20,
                 "magic_resist": 0.4, "attack_range": 700, "bat": 1.0,
                 "team_bounty": 160, "killer_bounty": 220, "hp_regen": 8},
    "barracks_melee": {"name": "Отдел найма", "hp": 2200, "damage": [0, 0], "armor": 12,
                       "magic_resist": 0.4, "attack_range": 0, "bat": 1.0,
                       "team_bounty": 120, "killer_bounty": 130, "hp_regen": 5},
    "barracks_ranged": {"name": "Отдел саппорта", "hp": 1800, "damage": [0, 0], "armor": 10,
                        "magic_resist": 0.4, "attack_range": 0, "bat": 1.0,
                        "team_bounty": 120, "killer_bounty": 130, "hp_regen": 5},
    "ancient": {"name": "Трон", "hp": 5000, "damage": [0, 0], "armor": 12,
                "magic_resist": 0.5, "attack_range": 0, "bat": 1.0,
                "team_bounty": 0, "killer_bounty": 0, "hp_regen": 0},
    "fountain": {"name": "Кухня", "hp": 100000, "damage": [200, 240], "armor": 100,
                 "magic_resist": 1.0, "attack_range": 1200, "bat": 0.4,
                 "team_bounty": 0, "killer_bounty": 0, "hp_regen": 0},
}

_FALLBACK_WAVES = {
    "first_wave_time": 30.0,
    "interval": 25.0,
    "melee_per_wave": 3,
    "ranged_per_wave": 1,
    "siege_every_n_waves": 5,
    "siege_first_wave": 3,
    "extra_melee_after": 900.0,
}

_FALLBACK_RESPAWN = [0.0] + [min(45.0, 3.0 + 1.7 * i) for i in range(1, 26)]

_FALLBACK_ECONOMY = {
    "starting_gold": 900,
    "passive_gold_per_sec": 3.0,
    "hero_kill_base": 120,
    "hero_kill_per_level": 12,
    "streak_bonus": [0, 0, 30, 70, 120, 180, 250, 330, 420],
    "assist_share": 0.45,
    "death_gold_loss_pct": 0.0,
    "buyback_base": 200,
    "buyback_per_level": 45,
    "xp_share_radius": 1400.0,
}


# ==========================================================================
#  Публичный доступ
# ==========================================================================

HEROES: dict = _HEROES if _HEROES else {"stub": _FALLBACK_HERO}
ITEMS: dict = _ITEMS
SHOP_LAYOUT: dict = _SHOP

# ==========================================================================
#  Нормализация
# ==========================================================================
# Данные пишутся отдельно от движка и могут расходиться в мелочах схемы
# (урон числом или диапазоном, разные имена полей награды). Движок владеет
# канонической формой, а загрузчик приводит к ней что угодно — так данные
# и код развиваются независимо.

def _as_range(v, default=(0.0, 0.0)) -> list[float]:
    if v is None:
        return [float(default[0]), float(default[1])]
    if isinstance(v, (list, tuple)):
        if len(v) >= 2:
            return [float(v[0]), float(v[1])]
        if len(v) == 1:
            return [float(v[0]), float(v[0])]
        return [float(default[0]), float(default[1])]
    return [float(v), float(v)]


def _pick(d: dict, *names, default=None):
    for n in names:
        if n in d:
            return d[n]
    return default


def _norm_creep(d: dict) -> dict:
    return {
        "name": d.get("name", "Крип"),
        "hp": float(d.get("hp", 500)),
        "damage": _as_range(d.get("damage"), (20, 24)),
        "armor": float(d.get("armor", 0)),
        "magic_resist": float(d.get("magic_resist", 0)),
        "attack_range": float(d.get("attack_range", 100)),
        "bat": float(d.get("bat", 1.0)),
        "move_speed": float(d.get("move_speed", 325)),
        "bounty_gold": _as_range(d.get("bounty_gold"), (30, 40)),
        "bounty_xp": float(d.get("bounty_xp", 50)),
        "vision": float(d.get("vision", 750)),
        "building_damage_mult": float(d.get("building_damage_mult", 1.0)),
        "hp_regen": float(d.get("hp_regen", 0.0)),
    }


def _norm_building(d: dict) -> dict:
    return {
        "name": d.get("name", "Строение"),
        "hp": float(d.get("hp", 1500)),
        "damage": _as_range(d.get("damage"), (0, 0)),
        "armor": float(d.get("armor", 0)),
        "magic_resist": float(d.get("magic_resist", 0)),
        "attack_range": float(d.get("attack_range", 0)),
        "bat": float(d.get("bat", 1.0)),
        "team_bounty": float(_pick(d, "team_bounty", "bounty_team_gold", default=0)),
        "killer_bounty": float(_pick(d, "killer_bounty", "bounty_killer_gold", default=0)),
        "hp_regen": float(d.get("hp_regen", 0)),
        "backdoor_protection": bool(d.get("backdoor_protection", False)),
        "vision": float(d.get("vision", 1400)),
    }


def _norm_waves(d: dict) -> dict:
    comp = d.get("composition") or {}
    siege = d.get("siege") or {}
    return {
        "first_wave_time": float(_pick(d, "first_wave_spawn_sec", "first_wave_time",
                                       default=20.0)),
        "interval": float(_pick(d, "interval_sec", "interval", default=25.0)),
        "melee_per_wave": int(comp.get("melee_creep",
                                       d.get("melee_per_wave", 3))),
        "ranged_per_wave": int(comp.get("ranged_creep",
                                        d.get("ranged_per_wave", 1))),
        "siege_unit": siege.get("unit", "siege_creep"),
        "siege_count": int(siege.get("count", 1)),
        "siege_first_time": float(_pick(siege, "first_spawn_sec",
                                        default=d.get("siege_first_wave", 180.0))),
        "siege_every_n": int(_pick(siege, "every_n_waves",
                                   default=d.get("siege_every_n_waves", 3))),
        "raw": d,
    }


XP_TABLE: list = getattr(_t, "XP_TABLE", _FALLBACK_XP)
MAX_LEVEL: int = getattr(_t, "MAX_LEVEL", 25)
CREEPS: dict = {k: _norm_creep(v) for k, v in
                (getattr(_t, "CREEPS", None) or _FALLBACK_CREEPS).items()}
BUILDINGS: dict = {k: _norm_building(v) for k, v in
                   (getattr(_t, "BUILDINGS", None) or _FALLBACK_BUILDINGS).items()}
WAVES: dict = _norm_waves(getattr(_t, "WAVE_SCHEDULE", None) or _FALLBACK_WAVES)
JUNGLE: dict = getattr(_t, "JUNGLE", {})
RUNES: dict = getattr(_t, "RUNES", {})
ECONOMY: dict = getattr(_t, "ECONOMY", _FALLBACK_ECONOMY)
RESPAWN_TABLE: list = getattr(_t, "RESPAWN_TABLE", _FALLBACK_RESPAWN)
BUILDING_RULES: dict = getattr(_t, "BUILDING_RULES", None) or {
    "backdoor_damage_taken_pct": 0.25,
    "backdoor_regen_hp_per_sec": 25.0,
    "backdoor_active_while_lane_creeps_absent_sec": 5.0,
    "out_of_combat_regen_delay_sec": 15.0,
    "glyph_cooldown_sec": 180.0,
    "glyph_duration_sec": 6.0,
}

HUMAN_POWER: float = getattr(_t, "HUMAN_POWER", 1.0)
BOT_POWER: float = getattr(_t, "BOT_POWER", 0.6)
DYNAMIC_ECONOMY_ENABLED: bool = getattr(_t, "DYNAMIC_ECONOMY_ENABLED", True)
UNDERDOG_MULT_CAP: float = getattr(_t, "UNDERDOG_MULT_CAP", 2.2)


def _fallback_team_income(team_size: int) -> float:
    if team_size <= 1:
        return 1.0
    return (team_size ** 0.75) / team_size


def _fallback_underdog(own_power: float, enemy_power: float) -> float:
    if own_power <= 0.01:
        return 1.0
    return max(1.0, min(UNDERDOG_MULT_CAP, (enemy_power / own_power) ** 0.65))


team_income_multiplier = getattr(_t, "team_income_multiplier", _fallback_team_income)
underdog_multiplier = getattr(_t, "underdog_multiplier", _fallback_underdog)


def hero_def(key: str) -> dict:
    return HEROES.get(key) or _FALLBACK_HERO


def creep_def(key: str) -> dict:
    return CREEPS.get(key) or _FALLBACK_CREEPS["melee_creep"]


def building_def(key: str) -> dict:
    return BUILDINGS.get(key) or _FALLBACK_BUILDINGS["tower_t1"]


def item_def(key: str) -> dict | None:
    return ITEMS.get(key)


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    idx = min(level - 1, len(XP_TABLE) - 1)
    return XP_TABLE[idx]


def level_for_xp(xp: float) -> int:
    lvl = 1
    for i in range(1, len(XP_TABLE)):
        if xp >= XP_TABLE[i]:
            lvl = i + 1
        else:
            break
    return min(lvl, MAX_LEVEL)


def respawn_time(level: int) -> float:
    """Время возрождения. Таблица может быть записана двумя способами:
    ровно MAX_LEVEL значений (индекс level-1) или с фиктивным нулём в начале
    (индекс level). Определяем по длине, чтобы не зависеть от соглашения автора."""
    level = max(1, min(level, MAX_LEVEL))
    if len(RESPAWN_TABLE) > MAX_LEVEL:
        return float(RESPAWN_TABLE[min(level, len(RESPAWN_TABLE) - 1)])
    return float(RESPAWN_TABLE[min(level - 1, len(RESPAWN_TABLE) - 1)])


def status() -> dict:
    return {
        "heroes": len(HEROES) if HEROES_LOADED else 0,
        "items": len(ITEMS) if ITEMS_LOADED else 0,
        "tuning": TUNING_LOADED,
        "heroes_loaded": HEROES_LOADED,
        "items_loaded": ITEMS_LOADED,
    }
