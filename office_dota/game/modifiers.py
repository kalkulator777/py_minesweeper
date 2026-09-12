"""Модификаторы: баффы, дебаффы, контроль, ауры, щиты.

Любой временный эффект в игре — модификатор. Юнит хранит их списком и
пересчитывает производные характеристики лениво, по флагу «грязно».

Правила сложения характеристик повторяют Dota 2:
  * магсопр, уклонение и сопротивление статусу складываются мультипликативно
  * остальное складывается плоско, проценты применяются после плоских бонусов
"""
from __future__ import annotations

from .consts import BLOCKED_BY_MAGIC_IMMUNITY, F_MAGIC_IMMUNE

# --- Правила наложения -----------------------------------------------------
STACK_REFRESH = "refresh"          # повторное наложение обновляет длительность
STACK_ADD = "stack"                # копится до max_stacks
STACK_NONE = "none"                # если уже висит — второе применение игнорируется
STACK_INDEPENDENT = "independent"  # каждый экземпляр живёт сам по себе

# Характеристики, которые складываются мультипликативно как «доли сопротивления»
_MULTIPLICATIVE = ("magic_resist", "evasion", "status_resist")

# Все допустимые ключи характеристик (ABILITY_SPEC.md §5)
STAT_KEYS = frozenset({
    "str", "agi", "int", "all_stats",
    "hp", "mana", "max_hp_pct", "max_mana_pct",
    "hp_regen", "mana_regen", "hp_regen_pct", "mana_regen_pct",
    "damage", "attack_speed", "attack_range", "bat_pct",
    "armor", "magic_resist", "status_resist", "evasion",
    "move_speed", "move_speed_pct",
    "spell_amp", "cooldown_reduction",
    "damage_taken_pct",
    "vision_day", "vision_night",
})


class Modifier:
    """Один наложенный эффект."""

    __slots__ = (
        "key", "name", "duration", "remaining", "stats", "flags",
        "stacking", "stacks", "max_stacks", "dispellable", "permanent",
        "source_id", "source_team", "ability_key",
        "tick_interval", "tick_accum", "tick_effects",
        "shield_amount", "shield_type",
        "pierces_magic_immunity", "is_aura_effect", "data", "visual",
    )

    def __init__(
        self,
        key: str,
        duration: float = 0.0,
        *,
        name: str = "",
        stats: dict[str, float] | None = None,
        flags: int = 0,
        stacking: str = STACK_REFRESH,
        max_stacks: int = 1,
        dispellable: bool = True,
        permanent: bool = False,
        source_id: int = 0,
        source_team: int = -1,
        ability_key: str = "",
        tick_interval: float = 0.0,
        tick_effects: list | None = None,
        shield_amount: float = 0.0,
        shield_type: str = "all",
        pierces_magic_immunity: bool = False,
        is_aura_effect: bool = False,
        visual: str = "",
        data: dict | None = None,
    ) -> None:
        self.key = key
        self.name = name or key
        self.duration = duration
        self.remaining = duration
        self.stats = stats or {}
        self.flags = flags
        self.stacking = stacking
        self.stacks = 1
        self.max_stacks = max_stacks
        self.dispellable = dispellable
        self.permanent = permanent
        self.source_id = source_id
        self.source_team = source_team
        self.ability_key = ability_key
        self.tick_interval = tick_interval
        self.tick_accum = 0.0
        self.tick_effects = tick_effects or []
        self.shield_amount = shield_amount
        self.shield_type = shield_type
        self.pierces_magic_immunity = pierces_magic_immunity
        self.is_aura_effect = is_aura_effect
        self.visual = visual
        self.data = data or {}

        for k in self.stats:
            if k not in STAT_KEYS:
                raise ValueError(f"модификатор {key}: неизвестная характеристика {k!r}")

    @property
    def expired(self) -> bool:
        if self.permanent:
            return False
        if self.shield_amount and self.shield_amount <= 0.0:
            return True
        return self.remaining <= 0.0

    def refresh(self, duration: float) -> None:
        self.duration = max(self.duration, duration)
        self.remaining = max(self.remaining, duration)

    def to_wire(self) -> dict:
        d = {"k": self.key, "n": self.name}
        if not self.permanent:
            d["r"] = round(self.remaining, 2)
            d["d"] = round(self.duration, 2)
        if self.stacks > 1:
            d["s"] = self.stacks
        if self.shield_amount > 0:
            d["sh"] = round(self.shield_amount)
        if self.visual:
            d["v"] = self.visual
        return d


class ModifierHost:
    """Примесь для юнита: хранение модификаторов и агрегация характеристик.

    Наследник обязан иметь атрибуты `_stats_dirty` (bool) и `id` (int),
    а также метод `on_modifier_changed()` — он вызывается при любом изменении.
    """

    __slots__ = ()

    # --- наложение и снятие -----------------------------------------------
    def add_modifier(self, mod: Modifier) -> Modifier | None:
        """Накладывает модификатор с учётом правил стакания.

        Возвращает фактически действующий экземпляр или None, если наложение
        отменено (магический иммунитет, правило STACK_NONE).
        """
        if self._blocks_modifier(mod):
            return None

        if mod.data.get("unique"):
            keep = self._resolve_unique(mod)
            if keep is not None:
                return keep

        if mod.stacking != STACK_INDEPENDENT:
            existing = self.find_modifier(mod.key)
            if existing is not None:
                if mod.stacking == STACK_NONE:
                    return existing
                if mod.stacking == STACK_ADD and existing.stacks < existing.max_stacks:
                    existing.stacks += 1
                existing.refresh(mod.duration)
                existing.stats = mod.stats
                existing.flags = mod.flags
                if mod.shield_amount:
                    existing.shield_amount = max(existing.shield_amount, mod.shield_amount)
                self._stats_dirty = True
                self.on_modifier_changed()
                return existing

        self.modifiers.append(mod)
        self._stats_dirty = True
        self.on_modifier_changed()
        return mod

    def _resolve_unique(self, mod: Modifier) -> Modifier | None:
        """Из одной уникальной группы остаётся сильнейший.

        Нужно там, где улучшенный предмет собирается из базового: обе ауры
        висели бы одновременно и складывались, чего быть не должно.
        Возвращает действующий модификатор, если новый не нужен.
        """
        group = mod.data["unique"]
        rank = float(mod.data.get("unique_rank", 1))
        drop: list[Modifier] = []
        for m in self.modifiers:
            if m.data.get("unique") != group or m.key == mod.key:
                continue
            if float(m.data.get("unique_rank", 1)) >= rank:
                return m                      # уже висит не слабее — новый не нужен
            drop.append(m)
        if drop:
            self.modifiers = [m for m in self.modifiers if m not in drop]
            self._stats_dirty = True
        return None

    def _blocks_modifier(self, mod: Modifier) -> bool:
        """Магический иммунитет отсекает контроль, если тот его не пробивает."""
        if mod.pierces_magic_immunity:
            return False
        if not (self.flags & F_MAGIC_IMMUNE):
            return False
        return bool(mod.flags & BLOCKED_BY_MAGIC_IMMUNITY)

    def find_modifier(self, key: str) -> Modifier | None:
        for m in self.modifiers:
            if m.key == key:
                return m
        return None

    def has_modifier(self, key: str) -> bool:
        return self.find_modifier(key) is not None

    def remove_modifier(self, key: str) -> bool:
        removed = False
        for i in range(len(self.modifiers) - 1, -1, -1):
            if self.modifiers[i].key == key:
                del self.modifiers[i]
                removed = True
        if removed:
            self._stats_dirty = True
            self.on_modifier_changed()
        return removed

    def remove_modifiers_from(self, source_id: int) -> None:
        before = len(self.modifiers)
        self.modifiers = [m for m in self.modifiers if m.source_id != source_id]
        if len(self.modifiers) != before:
            self._stats_dirty = True
            self.on_modifier_changed()

    def purge(self, strong: bool = False) -> int:
        """Снимает развеиваемые дебаффы. Сильное развеивание бьёт и по неразвеиваемым
        эффектам контроля, кроме постоянных. Возвращает число снятых."""
        keep: list[Modifier] = []
        removed = 0
        for m in self.modifiers:
            if m.permanent or m.is_aura_effect:
                keep.append(m)
                continue
            if m.dispellable or (strong and not m.pierces_magic_immunity):
                removed += 1
                continue
            keep.append(m)
        if removed:
            self.modifiers = keep
            self._stats_dirty = True
            self.on_modifier_changed()
        return removed

    # --- обновление --------------------------------------------------------
    def tick_modifiers(self, dt: float) -> list[tuple[Modifier, int]]:
        """Продвигает таймеры. Возвращает список (модификатор, число_срабатываний)
        для периодических эффектов — вызывающий сам применяет их."""
        if not self.modifiers:
            return []
        fired: list[tuple[Modifier, int]] = []
        alive: list[Modifier] = []
        changed = False
        for m in self.modifiers:
            if not m.permanent:
                m.remaining -= dt
            if m.tick_interval > 0.0 and m.tick_effects:
                m.tick_accum += dt
                n = 0
                while m.tick_accum >= m.tick_interval:
                    m.tick_accum -= m.tick_interval
                    n += 1
                if n:
                    fired.append((m, n))
            if m.expired:
                changed = True
                continue
            alive.append(m)
        if changed:
            self.modifiers = alive
            self._stats_dirty = True
            self.on_modifier_changed()
        return fired

    # --- агрегация ---------------------------------------------------------
    def aggregate_stats(self, out: dict[str, float]) -> int:
        """Складывает вклад всех модификаторов в out. Возвращает объединённые флаги.

        Мультипликативные характеристики накапливаются как «остаток»:
        out[k] хранит произведение (1 - r_i), вызывающий переводит его в долю.
        """
        flags = 0
        for m in self.modifiers:
            flags |= m.flags
            if not m.stats:
                continue
            mul = m.stacks
            for k, v in m.stats.items():
                if k == "all_stats":
                    v = v * mul
                    out["str"] = out.get("str", 0.0) + v
                    out["agi"] = out.get("agi", 0.0) + v
                    out["int"] = out.get("int", 0.0) + v
                elif k in _MULTIPLICATIVE:
                    frac = v / 100.0 if abs(v) > 1.0 else v
                    rem = out.get(k, 1.0)
                    for _ in range(mul):
                        rem *= (1.0 - frac)
                    out[k] = rem
                else:
                    out[k] = out.get(k, 0.0) + v * mul
        return flags

    def total_shield(self, dtype: str) -> float:
        total = 0.0
        for m in self.modifiers:
            if m.shield_amount <= 0:
                continue
            if m.shield_type == "all" or m.shield_type == dtype:
                total += m.shield_amount
        return total

    def consume_shield(self, amount: float, dtype: str) -> float:
        """Тратит щиты на поглощение урона. Возвращает остаток урона."""
        if amount <= 0:
            return 0.0
        for m in self.modifiers:
            if amount <= 0:
                break
            if m.shield_amount <= 0:
                continue
            if m.shield_type != "all" and m.shield_type != dtype:
                continue
            absorbed = min(m.shield_amount, amount)
            m.shield_amount -= absorbed
            amount -= absorbed
            if m.shield_amount <= 0:
                self._stats_dirty = True
        return amount


# --- Фабрики частых модификаторов ------------------------------------------

def stun(duration: float, source_id: int = 0, key: str = "stun") -> Modifier:
    from .consts import F_STUNNED
    return Modifier(key, duration, name="Оглушение", flags=F_STUNNED,
                    dispellable=False, source_id=source_id, visual="stun")


def silence(duration: float, source_id: int = 0, key: str = "silence") -> Modifier:
    from .consts import F_SILENCED
    return Modifier(key, duration, name="Немота", flags=F_SILENCED,
                    source_id=source_id, visual="silence")


def root(duration: float, source_id: int = 0, key: str = "root") -> Modifier:
    from .consts import F_ROOTED
    return Modifier(key, duration, name="Обездвиживание", flags=F_ROOTED,
                    source_id=source_id, visual="root")


def disarm(duration: float, source_id: int = 0, key: str = "disarm") -> Modifier:
    from .consts import F_DISARMED
    return Modifier(key, duration, name="Разоружение", flags=F_DISARMED,
                    source_id=source_id, visual="disarm")


def hex_mod(duration: float, source_id: int = 0, key: str = "hex") -> Modifier:
    from .consts import F_HEXED
    return Modifier(key, duration, name="Превращение", flags=F_HEXED,
                    stats={"move_speed_pct": -40.0}, dispellable=False,
                    source_id=source_id, visual="hex")


def slow(duration: float, move_pct: float = 0.0, attack_speed: float = 0.0,
         source_id: int = 0, key: str = "slow", name: str = "Замедление") -> Modifier:
    stats: dict[str, float] = {}
    if move_pct:
        stats["move_speed_pct"] = move_pct
    if attack_speed:
        stats["attack_speed"] = attack_speed
    return Modifier(key, duration, name=name, stats=stats,
                    source_id=source_id, visual="slow")


def shield(amount: float, duration: float, stype: str = "all",
           source_id: int = 0, key: str = "shield") -> Modifier:
    return Modifier(key, duration, name="Щит", shield_amount=amount,
                    shield_type=stype, source_id=source_id, visual="shield")


def magic_immunity(duration: float, source_id: int = 0, key: str = "magic_immune") -> Modifier:
    return Modifier(key, duration, name="Магический иммунитет", flags=F_MAGIC_IMMUNE,
                    dispellable=False, source_id=source_id, visual="bkb")


def invulnerable(duration: float, source_id: int = 0, key: str = "invuln") -> Modifier:
    from .consts import F_INVULNERABLE
    return Modifier(key, duration, name="Неуязвимость", flags=F_INVULNERABLE,
                    dispellable=False, source_id=source_id, visual="invuln")
