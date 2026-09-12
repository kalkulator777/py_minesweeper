"""Исполнитель эффектов и рантайм способностей.

Способности и предметы описаны декларативно (см. docs/ABILITY_SPEC.md).
Этот модуль — единственное место, где декларация превращается в действие.
Добавить новую способность = добавить данные, а не код.
"""
from __future__ import annotations

import math

from . import combat, modifiers as mods, vmath
from .consts import (
    CANNOT_CAST, DMG_MAGICAL, DMG_PHYSICAL, DMG_PURE, E_ILLUSION, E_SUMMON,
    F_CHEAT_DEATH, F_ETHEREAL, F_INVISIBLE, F_TAUNTED, F_TRUESIGHT,
    SRC_ABILITY, SRC_DOT, SRC_ITEM, TEAM_NEUTRAL, enemy_of,
)

# Операции, допустимые в данных. Всё, чего тут нет, — ошибка в данных.
VALID_OPS = frozenset({
    "damage", "heal", "dot", "execute", "lifesteal_burst",
    # добавлены по итогам проектирования контента — см. ENGINE_REQUESTS
    # в data/heroes.py и data/items.py
    "chain", "restore_mana", "mana_burn", "grant_gold", "grant_xp",
    "true_sight", "ghost", "cyclone", "toggle_pulse",
    "stun", "slow", "silence", "root", "disarm", "hex", "taunt", "purge",
    "shield", "invulnerable", "magic_immune", "invisible", "cheat_death", "stat_buff",
    "blink", "pull", "push", "leap",
    "projectile", "area", "aura", "channel", "delayed", "global",
    "passive_stats", "proc_attack", "crit", "bash", "evasion", "lifesteal",
    "cleave", "on_kill", "on_take_damage",
    "summon", "illusion",
})

# Операции, которые работают только как пассивные (не исполняются при касте)
PASSIVE_OPS = frozenset({
    "passive_stats", "proc_attack", "crit", "bash", "evasion",
    "lifesteal", "cleave", "aura", "on_kill",
})
# on_take_damage работает и пассивно (в passives предмета), и активно
# (в active.effects, тогда действует указанное время) — см. «Ответить всем».


def lv(value, level: int):
    """Достаёт значение для уровня способности. Скаляр возвращается как есть."""
    if isinstance(value, (list, tuple)):
        if not value:
            return 0
        return value[min(max(level, 1), len(value)) - 1]
    return value


class EffectContext:
    """Кто применяет, во что и на каком уровне."""

    __slots__ = ("caster", "hit", "px", "py", "level", "ability_key", "source",
                 "pierces_mi", "root_ability")

    def __init__(self, caster, hit=None, px: float = 0.0, py: float = 0.0,
                 level: int = 1, ability_key: str = "", source: str = SRC_ABILITY,
                 pierces_mi: bool = False, root_ability=None) -> None:
        self.caster = caster
        self.hit = hit
        self.px = px
        self.py = py
        self.level = level
        self.ability_key = ability_key
        self.source = source
        self.pierces_mi = pierces_mi
        self.root_ability = root_ability

    def with_hit(self, unit) -> "EffectContext":
        return EffectContext(self.caster, unit, unit.x, unit.y, self.level,
                             self.ability_key, self.source, self.pierces_mi,
                             self.root_ability)


def _resolve_targets(world, ctx: EffectContext, eff: dict) -> list:
    """Куда применяется операция: hit / caster / область."""
    tgt = eff.get("target", "hit")
    if tgt == "caster":
        return [ctx.caster]
    if tgt == "hit":
        return [ctx.hit] if ctx.hit is not None and ctx.hit.alive else []
    radius = float(lv(eff.get("radius", 0), ctx.level))
    if tgt == "allies_in_radius":
        return world.units_in_radius(ctx.px, ctx.py, radius, team=ctx.caster.team)
    if tgt == "enemies_in_radius":
        return world.units_in_radius(ctx.px, ctx.py, radius, team=enemy_of(ctx.caster.team))
    return [ctx.hit] if ctx.hit is not None and ctx.hit.alive else []


def _filtered(world, ctx: EffectContext, x: float, y: float, radius: float,
              filt: str, max_targets: int = 0) -> list:
    team = ctx.caster.team
    # «enemy» намеренно не включает строения: в доте площадные заклинания
    # по башням не бьют. Для пушеров есть отдельные фильтры.
    if filt == "enemy":
        units = [u for u in world.units_in_radius(x, y, radius, team=enemy_of(team),
                                                  include_neutrals=True)
                 if not u.is_building and u.can_be_attacked]
    elif filt == "enemy_all":
        units = [u for u in world.units_in_radius(x, y, radius, team=enemy_of(team),
                                                  include_neutrals=True)
                 if u.can_be_attacked]
    elif filt == "buildings":
        units = [u for u in world.units_in_radius(x, y, radius, team=enemy_of(team))
                 if u.is_building and u.etype != "fountain"
                 and not world.is_invulnerable_building(u)]
    elif filt == "ally":
        units = [u for u in world.units_in_radius(x, y, radius, team=team)
                 if u.can_be_attacked]
    elif filt == "creeps":
        units = [u for u in world.units_in_radius(x, y, radius, team=None)
                 if not u.is_building and u.etype != "hero" and u.can_be_attacked]
    else:
        units = [u for u in world.units_in_radius(x, y, radius, team=None)
                 if u.can_be_attacked]
    if max_targets and len(units) > max_targets:
        units.sort(key=lambda u: vmath.dist_sq(x, y, u.x, u.y))
        units = units[:max_targets]
    return units


def execute(world, ctx: EffectContext, effects: list) -> None:
    """Выполняет список операций. Точка входа для способностей и предметов."""
    for eff in effects:
        op = eff.get("op")
        if op in PASSIVE_OPS:
            continue
        fn = _HANDLERS.get(op)
        if fn is None:
            raise ValueError(f"неизвестная операция {op!r} в {ctx.ability_key}")
        fn(world, ctx, eff)


# ==========================================================================
#  Обработчики операций
# ==========================================================================

def _op_damage(world, ctx, eff):
    dtype = eff.get("dtype", DMG_MAGICAL)
    amount = float(lv(eff.get("amount", 0), ctx.level))
    scale_stat = eff.get("scale_stat")
    if scale_stat:
        amount += getattr(ctx.caster, scale_stat, 0.0) * float(eff.get("scale", 0.0))
    for t in _resolve_targets(world, ctx, eff):
        combat.apply_damage(world, t, amount, dtype, ctx.caster, ctx.source,
                            ctx.ability_key, ctx.pierces_mi)


def _op_heal(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    for t in _resolve_targets(world, ctx, eff):
        combat.heal(world, t, amount, ctx.caster, ctx.ability_key)


def _op_dot(world, ctx, eff):
    dps = float(lv(eff.get("dps", 0), ctx.level))
    duration = float(lv(eff.get("duration", 1), ctx.level))
    interval = float(eff.get("interval", 0.5))
    dtype = eff.get("dtype", DMG_MAGICAL)
    key = eff.get("key") or f"{ctx.ability_key}_dot"
    for t in _resolve_targets(world, ctx, eff):
        m = mods.Modifier(
            key, t.scaled_duration(duration) if eff.get("is_debuff", True) else duration,
            name=eff.get("name", "Периодический урон"),
            source_id=ctx.caster.id, source_team=ctx.caster.team,
            ability_key=ctx.ability_key, tick_interval=interval,
            tick_effects=[{"op": "damage", "dtype": dtype,
                           "amount": dps * interval, "target": "caster"}],
            pierces_magic_immunity=ctx.pierces_mi, visual=eff.get("visual", "dot"),
        )
        t.add_modifier(m)


def _op_execute(world, ctx, eff):
    threshold = float(lv(eff.get("hp_threshold", 0), ctx.level))
    allowed = eff.get("target_types")
    for t in _resolve_targets(world, ctx, eff):
        if allowed and t.etype not in allowed:
            continue
        if t.hp <= threshold and not (t.flags & F_CHEAT_DEATH):
            combat.apply_damage(world, t, t.hp + 1.0, DMG_PURE, ctx.caster,
                                ctx.source, ctx.ability_key, True)
            if eff.get("on_kill"):
                execute(world, ctx, eff["on_kill"])
        elif eff.get("on_fail"):
            execute(world, ctx.with_hit(t), eff["on_fail"])


def _op_lifesteal_burst(world, ctx, eff):
    pct = float(lv(eff.get("pct", 0), ctx.level)) / 100.0
    dealt = world.last_damage_by.get(ctx.caster.id, 0.0)
    if dealt > 0:
        combat.heal(world, ctx.caster, dealt * pct, ctx.caster, ctx.ability_key)


def _control(flag_factory, duration_key="duration"):
    def handler(world, ctx, eff):
        duration = float(lv(eff.get(duration_key, 0), ctx.level))
        key = eff.get("key") or f"{ctx.ability_key}_{flag_factory.__name__}"
        bound = bool(eff.get("bound_to_channel"))
        for t in _resolve_targets(world, ctx, eff):
            m = flag_factory(t.scaled_duration(duration), ctx.caster.id, key)
            m.pierces_magic_immunity = ctx.pierces_mi
            m.ability_key = ctx.ability_key
            m.source_team = ctx.caster.team
            if t.add_modifier(m) is not None and bound:
                # Прервали канал — снимаем и контроль. Иначе цель стоит
                # оглушённой, хотя способность уже не работает.
                world.bind_to_channel(ctx.caster.id, t.id, key)
    return handler


def _op_slow(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    move = float(lv(eff.get("move_pct", 0), ctx.level))
    aspd = float(lv(eff.get("attack_speed", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_slow"
    for t in _resolve_targets(world, ctx, eff):
        m = mods.slow(t.scaled_duration(duration), move, aspd, ctx.caster.id, key,
                      eff.get("name", "Замедление"))
        m.ability_key = ctx.ability_key
        m.pierces_magic_immunity = ctx.pierces_mi
        t.add_modifier(m)


def _op_taunt(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    radius = float(lv(eff.get("radius", 300), ctx.level))
    targets = _filtered(world, ctx, ctx.caster.x, ctx.caster.y, radius, "enemy")
    key = eff.get("key") or f"{ctx.ability_key}_taunt"
    for t in targets:
        if t.is_building:
            continue
        m = mods.Modifier(key, t.scaled_duration(duration), name="Насмешка",
                          flags=F_TAUNTED, dispellable=False,
                          source_id=ctx.caster.id, ability_key=ctx.ability_key,
                          visual="taunt")
        if t.add_modifier(m) is not None:
            t.taunt_source_id = ctx.caster.id
            t.order_attack(ctx.caster.id)


def _op_purge(world, ctx, eff):
    strong = eff.get("strength") == "strong"
    for t in _resolve_targets(world, ctx, eff):
        t.purge(strong)


def _op_shield(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    duration = float(lv(eff.get("duration", 10), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_shield"
    for t in _resolve_targets(world, ctx, eff):
        m = mods.shield(amount, duration, eff.get("stype", "all"), ctx.caster.id, key)
        m.name = eff.get("name", "Щит")
        t.add_modifier(m)


def _op_invulnerable(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_invuln"
    for t in _resolve_targets(world, ctx, eff):
        t.add_modifier(mods.invulnerable(duration, ctx.caster.id, key))


def _op_magic_immune(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_mi"
    for t in _resolve_targets(world, ctx, eff):
        t.purge(False)
        t.add_modifier(mods.magic_immunity(duration, ctx.caster.id, key))


def _op_invisible(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_invis"
    fade = float(eff.get("fade_delay", 0.0))
    for t in _resolve_targets(world, ctx, eff):
        if fade > 0:
            world.schedule(fade, lambda u=t, k=key, d=duration: u.add_modifier(
                mods.Modifier(k, d, name="Невидимость", flags=F_INVISIBLE,
                              dispellable=False, visual="invis")))
        else:
            t.add_modifier(mods.Modifier(key, duration, name="Невидимость",
                                         flags=F_INVISIBLE, dispellable=False,
                                         visual="invis"))


def _op_cheat_death(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_grave"
    for t in _resolve_targets(world, ctx, eff):
        t.add_modifier(mods.Modifier(key, duration, name="Обман смерти",
                                     flags=F_CHEAT_DEATH, dispellable=False,
                                     source_id=ctx.caster.id, visual="grave"))


def _op_stat_buff(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    stats = {k: float(lv(v, ctx.level)) for k, v in eff.get("stats", {}).items()}
    key = eff.get("key") or f"{ctx.ability_key}_buff"
    is_debuff = any(v < 0 for v in stats.values())
    data = {}
    if eff.get("unique"):
        data["unique"] = eff["unique"]
        data["unique_rank"] = float(eff.get("unique_rank", 1))
    if eff.get("break_on_damage"):
        data["break_on_damage"] = True
    if eff.get("on_death_effects"):
        # Метка платит, когда помеченный умирает от чьей угодно руки
        data["on_death_effects"] = eff["on_death_effects"]
    for t in _resolve_targets(world, ctx, eff):
        d = t.scaled_duration(duration) if is_debuff else duration
        m = mods.Modifier(key, d, name=eff.get("name", "Эффект"), stats=stats,
                          source_id=ctx.caster.id, ability_key=ctx.ability_key,
                          dispellable=eff.get("dispellable", True),
                          stacking=eff.get("stacking", mods.STACK_REFRESH),
                          max_stacks=eff.get("max_stacks", 1),
                          visual=eff.get("visual", "buff"), data=data)
        t.add_modifier(m)


def _op_blink(world, ctx, eff):
    max_dist = float(lv(eff.get("max_dist", 1200), ctx.level))
    to = eff.get("to", "point")
    c = ctx.caster
    if to == "target" and ctx.hit is not None:
        tx, ty = ctx.hit.x, ctx.hit.y
    elif to == "behind_target" and ctx.hit is not None:
        dx, dy = vmath.direction(c.x, c.y, ctx.hit.x, ctx.hit.y)
        tx = ctx.hit.x + dx * (ctx.hit.radius + c.radius + 30)
        ty = ctx.hit.y + dy * (ctx.hit.radius + c.radius + 30)
    else:
        tx, ty = ctx.px, ctx.py
    tx, ty = vmath.clamp_to_circle(tx, ty, c.x, c.y, max_dist)
    world.teleport_unit(c, tx, ty)


def _op_leap(world, ctx, eff):
    dist = float(lv(eff.get("distance", 300), ctx.level))
    duration = float(eff.get("duration", 0.4))
    c = ctx.caster
    dx, dy = vmath.from_angle(c.facing, 1.0)
    world.start_forced_move(c, c.x + dx * dist, c.y + dy * dist, duration)


def _op_pull(world, ctx, eff):
    speed = float(lv(eff.get("speed", 1000), ctx.level))
    c = ctx.caster
    for t in _resolve_targets(world, ctx, eff):
        d = vmath.dist(c.x, c.y, t.x, t.y)
        world.start_forced_move(t, c.x, c.y, max(0.05, d / max(1.0, speed)))


def _op_push(world, ctx, eff):
    speed = float(lv(eff.get("speed", 1000), ctx.level))
    distance = float(lv(eff.get("distance", 600), ctx.level))
    c = ctx.caster
    for t in _resolve_targets(world, ctx, eff):
        dx, dy = vmath.direction(c.x, c.y, t.x, t.y)
        if dx == 0.0 and dy == 0.0:
            dx, dy = vmath.from_angle(c.facing, 1.0)
        world.start_forced_move(t, t.x + dx * distance, t.y + dy * distance,
                                max(0.05, distance / max(1.0, speed)))


def _op_projectile(world, ctx, eff):
    c = ctx.caster
    speed = float(lv(eff.get("speed", 1000), ctx.level))
    if ctx.hit is not None and not eff.get("pierce"):
        world.spawn_ability_projectile(
            c, ctx, speed, target=ctx.hit, on_hit=eff.get("on_hit", []),
            radius=float(lv(eff.get("radius", 0), ctx.level)),
            visual=eff.get("visual", "bolt"))
    else:
        dx, dy = vmath.direction(c.x, c.y, ctx.px, ctx.py)
        if dx == 0.0 and dy == 0.0:
            dx, dy = vmath.from_angle(c.facing, 1.0)
        max_dist = float(lv(eff.get("max_dist", 1000), ctx.level))
        world.spawn_ability_projectile(
            c, ctx, speed, tx=c.x + dx * max_dist, ty=c.y + dy * max_dist,
            on_hit=eff.get("on_hit", []),
            radius=float(lv(eff.get("radius", 100), ctx.level)),
            pierce=bool(eff.get("pierce")), max_dist=max_dist,
            visual=eff.get("visual", "bolt"))


def _op_area(world, ctx, eff):
    radius = float(lv(eff.get("radius", 300), ctx.level))
    filt = eff.get("filter", "enemy")
    max_targets = int(eff.get("max_targets", 0))
    targets = _filtered(world, ctx, ctx.px, ctx.py, radius, filt, max_targets)
    world.emit_effect("area", ctx.px, ctx.py, radius, ctx.ability_key, ctx.caster.team)
    inner = eff.get("effects", [])
    for t in targets:
        execute(world, ctx.with_hit(t), inner)


def _op_global(world, ctx, eff):
    filt = eff.get("filter", "enemy")
    team = enemy_of(ctx.caster.team) if filt == "enemy" else ctx.caster.team
    inner = eff.get("effects", [])
    for u in world.all_heroes():
        if u.team != team or not u.alive:
            continue
        execute(world, ctx.with_hit(u), inner)


def _op_delayed(world, ctx, eff):
    delay = float(lv(eff.get("delay", 0.5), ctx.level))
    inner = eff.get("effects", [])
    px, py, hit = ctx.px, ctx.py, ctx.hit
    caster, level, akey = ctx.caster, ctx.level, ctx.ability_key
    pierces, src = ctx.pierces_mi, ctx.source

    def fire():
        if not caster.alive:
            return
        c2 = EffectContext(caster, hit if (hit is not None and hit.alive) else None,
                           px, py, level, akey, src, pierces)
        execute(world, c2, inner)

    world.schedule(delay, fire)


def _op_channel(world, ctx, eff):
    duration = float(lv(eff.get("duration", 1), ctx.level))
    interval = float(eff.get("interval", 0.5))
    world.start_channel(ctx.caster, ctx, duration, interval,
                        eff.get("on_tick", []), bool(eff.get("break_on_move", True)),
                        eff.get("on_finish", []))


def _op_summon(world, ctx, eff):
    unit_key = eff.get("unit", "intern")
    count = int(lv(eff.get("count", 1), ctx.level))
    duration = float(lv(eff.get("duration", 30), ctx.level))
    for i in range(count):
        ang = (i / max(1, count)) * math.tau
        dx, dy = vmath.from_angle(ang, 120.0)
        world.spawn_summon(ctx.caster, unit_key, ctx.caster.x + dx,
                           ctx.caster.y + dy, duration)


def _op_illusion(world, ctx, eff):
    count = int(lv(eff.get("count", 1), ctx.level))
    duration = float(lv(eff.get("duration", 20), ctx.level))
    out_pct = float(lv(eff.get("dmg_out_pct", 40), ctx.level))
    in_pct = float(lv(eff.get("dmg_in_pct", 200), ctx.level))
    world.spawn_illusions(ctx.caster, count, duration, out_pct, in_pct)



def _op_chain(world, ctx, eff):
    """Прыжки эффекта по целям — молния Зевса, волна Dazzle.

    Каждый прыжок бьёт слабее предыдущего на (1 - decay) и не возвращается
    к уже задетым. Прыжки разнесены во времени, чтобы это читалось глазом.
    """
    jumps = int(lv(eff.get("jumps", 3), ctx.level))
    radius = float(lv(eff.get("radius", 500), ctx.level))
    decay = float(eff.get("decay", 1.0))
    delay = float(eff.get("delay", 0.25))
    filt = eff.get("filter", "enemy")
    inner = eff.get("effects", [])
    first = ctx.hit
    if first is None:
        found = _filtered(world, ctx, ctx.px, ctx.py, radius, filt, 1)
        if not found:
            return
        first = found[0]

    def hop(target, left: int, scale: float, seen: set):
        if target is None or not target.alive:
            return
        seen.add(target.id)
        c2 = ctx.with_hit(target)
        execute(world, c2, _scaled(inner, scale))
        world.emit("fx", fx="chain", x=round(target.x), y=round(target.y),
                   r=40, k=ctx.ability_key, team=ctx.caster.team)
        if left <= 1:
            return
        nxt = [u for u in _filtered(world, ctx, target.x, target.y, radius, filt)
               if u.id not in seen]
        if not nxt:
            return
        nxt.sort(key=lambda u: vmath.dist_sq(target.x, target.y, u.x, u.y))
        world.schedule(delay, lambda t=nxt[0], l=left - 1, s=scale * decay:
                       hop(t, l, s, seen))

    hop(first, jumps, 1.0, set())


def _scaled(effects: list, scale: float) -> list:
    """Копия списка эффектов с умноженными числовыми величинами."""
    if scale >= 0.999:
        return effects
    out = []
    for e in effects:
        e2 = dict(e)
        for key in ("amount", "dps", "heal"):
            if key in e2 and isinstance(e2[key], (int, float)):
                e2[key] = e2[key] * scale
            elif key in e2 and isinstance(e2[key], (list, tuple)):
                e2[key] = [v * scale for v in e2[key]]
        out.append(e2)
    return out


def _op_restore_mana(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    pct = float(lv(eff.get("pct", 0), ctx.level))
    for t in _resolve_targets(world, ctx, eff):
        gain = amount + (t.max_mana * pct / 100.0 if pct else 0.0)
        if gain <= 0 or t.max_mana <= 0:
            continue
        t.mana = min(t.max_mana, t.mana + gain)
        world.emit("mana", id=t.id, v=round(gain))


def _op_mana_burn(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    per_int = float(lv(eff.get("per_int", 0), ctx.level))
    ratio = float(lv(eff.get("damage_per_mana", 0), ctx.level))
    for t in _resolve_targets(world, ctx, eff):
        burn = amount
        if per_int:
            st = {}
            t.aggregate_stats(st)
            burn += per_int * t._attributes(st)[2]
        burn = min(burn, t.mana)
        if burn <= 0:
            continue
        t.mana -= burn
        world.emit("mana", id=t.id, v=-round(burn))
        if ratio:
            combat.apply_damage(world, t, burn * ratio, DMG_MAGICAL, ctx.caster,
                                ctx.source, ctx.ability_key, ctx.pierces_mi)


def _op_grant_gold(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    for t in _resolve_targets(world, ctx, eff):
        if t.etype == "hero":
            world.grant_gold(t, amount, ctx.ability_key,
                             apply_mult=bool(eff.get("apply_mult", False)))


def _op_grant_xp(world, ctx, eff):
    amount = float(lv(eff.get("amount", 0), ctx.level))
    # Множитель от награды жертвы — так работает Midas: ценность растёт
    # вместе с тем, кого съели, а не одинакова на стажёре и на боссе леса
    mult = float(eff.get("from_target_bounty", 0))
    if mult and ctx.hit is not None:
        amount += float(getattr(ctx.hit, "bounty_xp", 0)) * mult
    for t in _resolve_targets(world, ctx, eff):
        if t.etype == "hero":
            world.grant_xp(t, amount, apply_mult=bool(eff.get("apply_mult", False)))


def _op_true_sight(world, ctx, eff):
    duration = float(lv(eff.get("duration", 0), ctx.level))
    radius = float(lv(eff.get("radius", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_truesight"
    for t in _resolve_targets(world, ctx, eff):
        t.add_modifier(mods.Modifier(key, duration, name="Истинное зрение",
                                     flags=F_TRUESIGHT, dispellable=False,
                                     source_id=ctx.caster.id,
                                     data={"radius": radius}, visual="truesight"))


def _op_ghost(world, ctx, eff):
    """Эфирная форма: физический урон не проходит, магический усилен."""
    duration = float(lv(eff.get("duration", 0), ctx.level))
    amp = float(lv(eff.get("magic_amp", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_ghost"
    stats = {"damage_taken_pct": amp} if amp else {}
    for t in _resolve_targets(world, ctx, eff):
        t.add_modifier(mods.Modifier(key, duration, name="Эфирная форма",
                                     flags=F_ETHEREAL, stats=stats,
                                     source_id=ctx.caster.id, visual="ghost"))


def _op_cyclone(world, ctx, eff):
    """Подбрасывает цель: она неуязвима, обездвижена и ничего не делает."""
    duration = float(lv(eff.get("duration", 0), ctx.level))
    key = eff.get("key") or f"{ctx.ability_key}_cyclone"
    from .consts import F_INVULNERABLE, F_ROOTED, F_SILENCED, F_DISARMED
    flags = F_INVULNERABLE | F_ROOTED | F_SILENCED | F_DISARMED
    for t in _resolve_targets(world, ctx, eff):
        t.purge(False)
        m = mods.Modifier(key, t.scaled_duration(duration), name="Внезапный созвон",
                          flags=flags, dispellable=False, source_id=ctx.caster.id,
                          visual="cyclone")
        m.pierces_magic_immunity = ctx.pierces_mi
        if t.add_modifier(m) is not None:
            t.order_stop()
            world.forced_moves.pop(t.id, None)
            world.channels.pop(t.id, None)
        after = eff.get("on_land")
        if after:
            world.schedule(duration, lambda u=t: execute(world, ctx.with_hit(u), after))


def _op_on_take_damage(world, ctx, eff):
    """Возврат урона на время. Пассивный вариант собирается в refresh_triggers."""
    # В активке длительность обязана быть задана данными. Если её забыли —
    # берём умеренное значение вместо «висит вечно», но это стоит поправить
    # в данных, а не полагаться на подстановку.
    duration = float(lv(eff.get("duration", 0), ctx.level)) or 5.0
    key = eff.get("key") or f"{ctx.ability_key}_reflect"
    m = mods.Modifier(key, duration, name=eff.get("name", "Возврат урона"),
                      source_id=ctx.caster.id, dispellable=False, visual="reflect",
                      data={"reflect_effects": eff.get("effects", []),
                            "reflect_pct": float(eff.get("reflect_pct", 0))})
    ctx.caster.add_modifier(m)


def _op_toggle_pulse(world, ctx, eff):
    """Обёртка: содержимое применяется, пока способность включена.
    Сам цикл ведёт мир, здесь — разовое применение одного такта."""
    execute(world, ctx, eff.get("effects", []))


_HANDLERS = {
    "damage": _op_damage,
    "heal": _op_heal,
    "dot": _op_dot,
    "execute": _op_execute,
    "lifesteal_burst": _op_lifesteal_burst,
    "stun": _control(mods.stun),
    "silence": _control(mods.silence),
    "root": _control(mods.root),
    "disarm": _control(mods.disarm),
    "hex": _control(mods.hex_mod),
    "slow": _op_slow,
    "taunt": _op_taunt,
    "purge": _op_purge,
    "shield": _op_shield,
    "invulnerable": _op_invulnerable,
    "magic_immune": _op_magic_immune,
    "invisible": _op_invisible,
    "cheat_death": _op_cheat_death,
    "stat_buff": _op_stat_buff,
    "blink": _op_blink,
    "leap": _op_leap,
    "pull": _op_pull,
    "push": _op_push,
    "projectile": _op_projectile,
    "area": _op_area,
    "global": _op_global,
    "delayed": _op_delayed,
    "channel": _op_channel,
    "summon": _op_summon,
    "illusion": _op_illusion,
    "chain": _op_chain,
    "restore_mana": _op_restore_mana,
    "mana_burn": _op_mana_burn,
    "grant_gold": _op_grant_gold,
    "grant_xp": _op_grant_xp,
    "true_sight": _op_true_sight,
    "ghost": _op_ghost,
    "cyclone": _op_cyclone,
    "toggle_pulse": _op_toggle_pulse,
    "on_take_damage": _op_on_take_damage,
}


# ==========================================================================
#  Пассивные вклады
# ==========================================================================

def contribute_passives(effects: list, level: int, out: dict) -> int:
    """Складывает пассивные эффекты в накопитель характеристик. Возвращает флаги.

    Величины, которых нет в STAT_KEYS (крит, вампиризм, рассечение), живут
    в накопителе под служебными ключами с подчёркиванием.
    """
    from .entities import add_stat
    flags = 0
    for eff in effects:
        op = eff.get("op")
        if op == "passive_stats":
            for k, v in eff.get("stats", {}).items():
                add_stat(out, k, float(lv(v, level)))
        elif op == "crit":
            out["_crit_chance"] = max(out.get("_crit_chance", 0.0),
                                      float(lv(eff.get("chance", 0), level)) / 100.0)
            out["_crit_mult"] = max(out.get("_crit_mult", 1.0),
                                    float(lv(eff.get("mult", 1), level)))
        elif op == "bash":
            out["_bash_chance"] = max(out.get("_bash_chance", 0.0),
                                      float(lv(eff.get("chance", 0), level)) / 100.0)
            out["_bash_duration"] = max(out.get("_bash_duration", 0.0),
                                        float(lv(eff.get("duration", 0), level)))
        elif op == "evasion":
            mul_pct = float(lv(eff.get("pct", 0), level))
            out["evasion"] = out.get("evasion", 1.0) * (1.0 - mul_pct / 100.0)
        elif op == "lifesteal":
            out["_lifesteal"] = out.get("_lifesteal", 0.0) + \
                float(lv(eff.get("pct", 0), level)) / 100.0
        elif op == "cleave":
            out["_cleave_pct"] = max(out.get("_cleave_pct", 0.0),
                                     float(lv(eff.get("pct", 0), level)) / 100.0)
            out["_cleave_radius"] = max(out.get("_cleave_radius", 0.0),
                                        float(lv(eff.get("radius", 0), level)))
    return flags


def attack_procs(effects: list, level: int) -> list[dict]:
    """Срабатывания при атаке.

    Поле cooldown у пассивки — это кулдаун самого срабатывания. Без него
    пассивка с chance 100 срабатывает каждым ударом: именно так ломалась
    кража бюджета у Безопасника.
    """
    out = []
    for i, eff in enumerate(effects):
        if eff.get("op") != "proc_attack":
            continue
        out.append({
            "chance": float(lv(eff.get("chance", 100), level)) / 100.0,
            "effects": eff.get("effects", []),
            "cooldown": float(lv(eff.get("cooldown", 0), level)),
            "key": eff.get("key") or f"proc{i}",
            "level": level,
            "once_per_target": bool(eff.get("once_per_target")),
        })
    return out


def triggered(effects: list, op: str) -> list[list]:
    return [e.get("effects", []) for e in effects if e.get("op") == op]


def auras(effects: list, level: int) -> list[dict]:
    out = []
    for eff in effects:
        if eff.get("op") == "aura":
            out.append({
                "radius": float(lv(eff.get("radius", 900), level)),
                "filter": eff.get("filter", "ally"),
                "stats": {k: float(lv(v, level)) for k, v in eff.get("stats", {}).items()},
                "key": eff.get("key", "aura"),
                "name": eff.get("name", "Аура"),
                "unique": eff.get("unique", ""),
                "unique_rank": float(eff.get("unique_rank", 1)),
            })
    return out


# ==========================================================================
#  Рантайм способности
# ==========================================================================

class Ability:
    """Экземпляр способности у конкретного героя."""

    __slots__ = ("defn", "level", "cooldown", "owner_id", "toggled", "charges",
                 "_cached_passive_level", "_passive_cache")

    def __init__(self, defn: dict, owner_id: int = 0) -> None:
        self.defn = defn
        self.level = 0
        self.cooldown = 0.0
        self.owner_id = owner_id
        self.toggled = False
        self.charges = 0

    # --- свойства из данных ------------------------------------------------
    @property
    def key(self) -> str:
        return self.defn["key"]

    @property
    def name(self) -> str:
        return self.defn.get("name", self.key)

    @property
    def hotkey(self) -> str:
        return self.defn.get("hotkey", "")

    @property
    def targeting(self) -> str:
        return self.defn.get("targeting", "none")

    @property
    def max_level(self) -> int:
        return int(self.defn.get("max_level", 4))

    @property
    def is_ultimate(self) -> bool:
        return self.max_level == 3

    @property
    def cast_range(self) -> float:
        return float(lv(self.defn.get("cast_range", 0), max(1, self.level)))

    @property
    def cast_point(self) -> float:
        return float(self.defn.get("cast_point", 0.3))

    def mana_cost(self) -> float:
        return float(lv(self.defn.get("mana_cost", 0), max(1, self.level)))

    def full_cooldown(self, owner=None) -> float:
        cd = float(lv(self.defn.get("cooldown", 0), max(1, self.level)))
        if owner is not None:
            cd *= 1.0 - owner.cooldown_reduction
        return cd

    def can_level(self, hero_level: int) -> bool:
        if self.level >= self.max_level:
            return False
        reqs = self.defn.get("level_req")
        if reqs and self.level < len(reqs):
            return hero_level >= reqs[self.level]
        return True

    # --- готовность --------------------------------------------------------
    def ready(self, owner) -> tuple[bool, str]:
        if self.level <= 0:
            return False, "не изучено"
        if self.targeting == "passive":
            return False, "пассивная"
        if self.cooldown > 0.0:
            return False, "откат"
        if owner.flags & CANNOT_CAST:
            return False, "нельзя применять"
        if owner.mana < self.mana_cost():
            return False, "мало маны"
        return True, ""

    def tick(self, dt: float) -> None:
        if self.cooldown > 0.0:
            self.cooldown = max(0.0, self.cooldown - dt)

    def start_cooldown(self, owner) -> None:
        self.cooldown = self.full_cooldown(owner)

    def contribute_passive(self, out: dict) -> int:
        if self.level <= 0:
            return 0
        return contribute_passives(self.defn.get("effects", []), self.level, out)

    def to_wire(self) -> dict:
        return {
            "k": self.key, "n": self.name, "h": self.hotkey,
            "lvl": self.level, "max": self.max_level,
            "cd": round(self.cooldown, 2),
            "cdmax": round(float(lv(self.defn.get("cooldown", 0), max(1, self.level))), 2),
            "mana": round(self.mana_cost()),
            "tgt": self.targeting,
            "range": self.cast_range,
            "aoe": float(lv(self.defn.get("aoe_radius", 0), max(1, self.level))),
            "desc": self.defn.get("desc", ""),
            "ult": self.is_ultimate,
        }
