"""Рантайм предметов: экземпляр в инвентаре, откаты, заряды, сборка рецептов."""
from __future__ import annotations

from . import abilities as ab, content as C


class Item:
    """Предмет в слоте героя."""

    __slots__ = ("key", "defn", "cooldown", "charges", "toggled", "disabled_until")

    def __init__(self, key: str, defn: dict | None = None) -> None:
        self.key = key
        self.defn = defn if defn is not None else (C.item_def(key) or {})
        self.cooldown = 0.0
        self.charges = int(self.defn.get("charges", 0))
        self.toggled = False
        self.disabled_until = 0.0

    @property
    def name(self) -> str:
        return self.defn.get("name", self.key)

    @property
    def cost(self) -> int:
        return int(self.defn.get("cost", 0))

    @property
    def active(self) -> dict | None:
        return self.defn.get("active")

    @property
    def is_consumable(self) -> bool:
        return self.defn.get("shop") == "consumable" or self.defn.get("consumable", False)

    def tick(self, dt: float) -> None:
        if self.cooldown > 0.0:
            self.cooldown = max(0.0, self.cooldown - dt)

    def contribute(self, out: dict) -> int:
        """Пассивные характеристики и эффекты предмета."""
        from .entities import add_stat
        flags = 0
        for k, v in self.defn.get("stats", {}).items():
            add_stat(out, k, float(v))
        passives = self.defn.get("passives") or []
        if passives:
            flags |= ab.contribute_passives(passives, 1, out)
        return flags

    def ready(self, owner, now: float) -> tuple[bool, str]:
        a = self.active
        if not a:
            return False, "нет активной способности"
        if self.cooldown > 0.0:
            return False, "откат"
        if now < self.disabled_until:
            return False, "заблокировано уроном"
        if owner.mana < float(a.get("mana_cost", 0)):
            return False, "мало маны"
        from .consts import CANNOT_USE_ITEMS
        if owner.flags & CANNOT_USE_ITEMS:
            return False, "нельзя использовать"
        return True, ""

    def to_wire(self) -> dict:
        d = {"k": self.key, "n": self.name, "cost": self.cost}
        if self.cooldown > 0:
            d["cd"] = round(self.cooldown, 2)
        a = self.active
        if a:
            d["cdmax"] = float(a.get("cooldown", 0))
            d["tgt"] = a.get("targeting", "none")
            d["range"] = float(a.get("cast_range", 0))
            d["mana"] = float(a.get("mana_cost", 0))
        if self.charges:
            d["ch"] = self.charges
        if self.toggled:
            d["on"] = 1
        return d


def build_tree() -> dict[str, list[str]]:
    """key -> список предметов, в которые он входит компонентом."""
    tree: dict[str, list[str]] = {}
    for key, d in C.ITEMS.items():
        for comp in d.get("components", []) or []:
            tree.setdefault(comp, []).append(key)
    return tree


UPGRADES_INTO = build_tree()


def missing_components(hero, key: str) -> list[str] | None:
    """Чего не хватает герою для сборки предмета. None — предмет не собирается."""
    d = C.item_def(key)
    if not d:
        return None
    comps = list(d.get("components", []) or [])
    if not comps:
        return None
    have = [it.key for it in hero.all_items()] + \
           [it.key for it in hero.backpack if it is not None]
    missing = []
    for c in comps:
        if c in have:
            have.remove(c)
        else:
            missing.append(c)
    return missing


def try_assemble(hero, key: str) -> bool:
    """Собирает предмет из компонентов в инвентаре. True — собрали."""
    d = C.item_def(key)
    comps = list(d.get("components", []) or []) if d else []
    if not comps:
        return False
    slots: list[tuple[str, int]] = []
    pool = list(comps)
    for store in ("items", "backpack"):
        arr = getattr(hero, store)
        for i, it in enumerate(arr):
            if it is not None and it.key in pool:
                pool.remove(it.key)
                slots.append((store, i))
    if pool:
        return False
    first = slots[0]
    for store, i in slots:
        getattr(hero, store)[i] = None
    getattr(hero, first[0])[first[1]] = Item(key)
    hero._stats_dirty = True
    return True
