"""Боевая модель. Формулы совпадают с Dota 2 — это осознанное требование:
человек, знающий доту, должен правильно предсказывать исход размена.
"""
from __future__ import annotations

import random

from .consts import (
    ARMOR_K, DMG_MAGICAL, DMG_PHYSICAL, DMG_PURE,
    F_CHEAT_DEATH, F_ETHEREAL, F_INVULNERABLE, F_MAGIC_IMMUNE,
    MAX_ATTACK_SPEED, MIN_ATTACK_SPEED, SRC_ABILITY, SRC_ATTACK, SRC_ITEM,
)

ETHEREAL_MAGIC_AMP = 0.40          # эфирная форма: +40% получаемого магического урона


def physical_multiplier(armor: float) -> float:
    """Множитель физического урона от брони. Отрицательная броня усиливает урон."""
    k = ARMOR_K * armor
    return 1.0 - k / (1.0 + (k if armor >= 0 else -k))


def resist_from_sources(remainder: float) -> float:
    """Переводит произведение (1 - r_i) в итоговую долю сопротивления."""
    return 1.0 - remainder


def attack_time(bat: float, attack_speed: float) -> float:
    """Время между атаками. attack_speed — это IAS (100 = базовая)."""
    ias = min(MAX_ATTACK_SPEED, max(MIN_ATTACK_SPEED, attack_speed))
    return bat / (ias / 100.0)


class DamageResult:
    __slots__ = ("dealt", "blocked", "absorbed", "killed", "was_lethal")

    def __init__(self) -> None:
        self.dealt = 0.0
        self.blocked = 0.0
        self.absorbed = 0.0
        self.killed = False
        self.was_lethal = False


def compute_damage(target, amount: float, dtype: str, attacker=None,
                   source: str = SRC_ABILITY,
                   pierces_magic_immunity: bool = False) -> tuple[float, float]:
    """Считает урон после всех сопротивлений. Возвращает (итог, сколько_срезано).

    Щиты здесь не трогаются — они списываются в apply_damage.
    """
    if amount <= 0.0:
        return 0.0, 0.0
    # Флаги живут на юните и обновляются при пересчёте. Без этой строки
    # неуязвимость, магический иммунитет и эфирная форма начинали бы
    # действовать только со следующего тика — целый класс ошибок вида
    # «наложил щит и тут же получил урон сквозь него».
    target.ensure_stats()
    raw = amount
    flags = target.flags

    if flags & F_INVULNERABLE:
        return 0.0, raw

    if dtype == DMG_MAGICAL:
        if (flags & F_MAGIC_IMMUNE) and not pierces_magic_immunity:
            return 0.0, raw
        # Усиление заклинаний кастера — только для способностей и предметов
        if attacker is not None and source != SRC_ATTACK:
            amount *= 1.0 + getattr(attacker, "spell_amp", 0.0)
        amount *= 1.0 - target.magic_resist
        if flags & F_ETHEREAL:
            amount *= 1.0 + ETHEREAL_MAGIC_AMP

    elif dtype == DMG_PHYSICAL:
        if flags & F_ETHEREAL:
            return 0.0, raw
        amount *= physical_multiplier(target.armor)

    elif dtype == DMG_PURE:
        # Магический иммунитет режет и чистый урон от способностей —
        # так же ведёт себя дота. Пробить это можно только явным
        # pierces_magic_immunity у самой способности.
        if (flags & F_MAGIC_IMMUNE) and not pierces_magic_immunity \
                and source in (SRC_ABILITY, SRC_ITEM):
            return 0.0, raw

    amount *= target.damage_taken_mult

    # Защита от бэкдора: строение без своих крипов рядом почти не получает
    # урона. Иначе один герой тихо сносит трон, пока идёт драка на другом
    # конце карты.
    if target.is_building and getattr(target, "backdoor_protected", False):
        amount *= _backdoor_mult()

    if amount < 0.0:
        amount = 0.0
    return amount, raw - amount


def _backdoor_mult() -> float:
    from . import content as C
    return float(C.BUILDING_RULES.get("backdoor_damage_taken_pct", 0.25))


def apply_damage(world, target, amount: float, dtype: str, attacker=None,
                 source: str = SRC_ABILITY, ability_key: str = "",
                 pierces_magic_immunity: bool = False) -> DamageResult:
    """Наносит урон цели: сопротивления, щиты, обман смерти, гибель."""
    res = DamageResult()
    if not target.alive or amount <= 0.0:
        return res

    dealt, blocked = compute_damage(target, amount, dtype, attacker, source,
                                    pierces_magic_immunity)
    res.blocked = blocked
    if dealt <= 0.0:
        return res

    before_shield = dealt
    dealt = target.consume_shield(dealt, dtype)
    res.absorbed = before_shield - dealt
    if dealt <= 0.0:
        return res

    target.hp -= dealt
    res.dealt = dealt

    if target.hp <= 0.0:
        res.was_lethal = True
        if target.flags & F_CHEAT_DEATH:
            target.hp = 1.0
        else:
            target.hp = 0.0
            res.killed = True

    target.on_damaged(attacker, dealt, dtype, source, ability_key)
    world.record_damage(attacker, target, dealt, dtype, ability_key)

    if res.killed:
        world.kill_unit(target, attacker, ability_key)
    return res


def heal(world, target, amount: float, healer=None, ability_key: str = "") -> float:
    if not target.alive or amount <= 0.0:
        return 0.0
    amount *= target.heal_taken_mult
    before = target.hp
    target.hp = min(target.max_hp, target.hp + amount)
    healed = target.hp - before
    if healed > 0.0:
        world.record_heal(healer, target, healed, ability_key)
    return healed


def roll_attack_damage(attacker, target, rng: random.Random) -> tuple[float, bool, bool]:
    """Разыгрывает автоатаку: уклонение, крит.

    Возвращает (урон, был_ли_крит, промах).
    """
    if target.evasion > 0.0 and rng.random() < target.evasion:
        return 0.0, False, True

    dmg = rng.uniform(attacker.damage_min, attacker.damage_max)
    crit = False
    if attacker.crit_chance > 0.0 and rng.random() < attacker.crit_chance:
        dmg *= attacker.crit_mult
        crit = True
    return dmg, crit, False


def hp_bar_fraction(unit) -> float:
    if unit.max_hp <= 0:
        return 0.0
    return max(0.0, min(1.0, unit.hp / unit.max_hp))
