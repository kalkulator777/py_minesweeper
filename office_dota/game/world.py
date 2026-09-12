"""Мир: фиксированный тик симуляции и всё, что в нём происходит.

Сервер авторитетен. Клиент шлёт намерения, мир решает, что из них выйдет.
Тик фиксированный (TICK_DT), поэтому пауза — это просто отказ вызывать tick().
"""
from __future__ import annotations

import math
import random

from . import abilities as ab, combat, content as C, gamemap as gm, vmath
from .consts import (
    IS_DISABLED as IS_DISABLED_MASK,
    DMG_PURE,
    ATTACK_RANGE_BUFFER, DAY_NIGHT_PERIOD, DELIVERY_TIME, DMG_MAGICAL, DMG_PHYSICAL,
    E_ANCIENT, E_BARRACKS, E_CREEP, E_FOUNTAIN, E_HERO, E_ILLUSION, E_NEUTRAL,
    E_SUMMON, E_TOWER, E_WARD, F_CHANNELING, F_INVISIBLE, F_TAUNTED, F_TRUESIGHT,
    ORDER_ATTACK_MOVE, ORDER_ATTACK_UNIT, ORDER_CAST, ORDER_HOLD, ORDER_MOVE,
    ORDER_NONE, ORDER_STOP, PHASE_FINISHED, PHASE_RUNNING,
    SRC_ATTACK, SRC_ITEM, SRC_TOWER, TEAM_DEV, TEAM_MGMT, TEAM_NEUTRAL, TICK_DT,
    TEAM_NAMES, enemy_of,
)
from .entities import Building, Creep, Hero, Projectile, Unit


BACKDOOR_MULT_DEFAULT = 0.25


def _has_blink(defn: dict) -> bool:
    act = defn.get("active") or {}
    return any(e.get("op") == "blink" for e in act.get("effects", []))
from .spatial import SpatialHash

CREEP_AGGRO_RADIUS = 500.0
TOWER_AGGRO_RADIUS = 700.0
HERO_AUTO_ACQUIRE_RADIUS = 600.0
FOUNTAIN_HEAL_RADIUS = 1100.0


class ForcedMove:
    """Принудительное перемещение: крюк, толчок, прыжок."""
    __slots__ = ("sx", "sy", "tx", "ty", "elapsed", "duration")

    def __init__(self, sx, sy, tx, ty, duration):
        self.sx, self.sy = sx, sy
        self.tx, self.ty = tx, ty
        self.elapsed = 0.0
        self.duration = max(0.02, duration)


class Channel:
    """Активный канал способности."""
    __slots__ = ("ctx", "remaining", "interval", "accum", "on_tick", "break_on_move",
                 "on_finish", "start_x", "start_y")

    def __init__(self, ctx, duration, interval, on_tick, break_on_move, on_finish, x, y):
        self.ctx = ctx
        self.remaining = duration
        self.interval = max(0.05, interval)
        self.accum = 0.0
        self.on_tick = on_tick
        self.break_on_move = break_on_move
        self.on_finish = on_finish or []
        self.start_x, self.start_y = x, y


class TeamState:
    __slots__ = ("team", "score", "ancient_id", "barracks_down", "mega_creeps",
                 "glyph_cooldown", "roshan_kills", "gold_earned", "tower_kills")

    def __init__(self, team: int) -> None:
        self.team = team
        self.score = 0
        self.ancient_id = 0
        self.barracks_down = {"top": set(), "mid": set(), "bot": set()}
        self.mega_creeps = False
        self.glyph_cooldown = 0.0
        self.roshan_kills = 0
        self.gold_earned = 0.0
        self.tower_kills = 0


class World:
    """Состояние матча и его продвижение во времени."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed or 1337)
        self.time = 0.0
        self.tick_count = 0
        self.phase = PHASE_RUNNING
        self.winner = -1

        self._next_id = 1
        self.units: dict[int, Unit] = {}
        self.projectiles: list[Projectile] = []
        self.spatial = SpatialHash()

        self.teams = {TEAM_DEV: TeamState(TEAM_DEV), TEAM_MGMT: TeamState(TEAM_MGMT)}
        self.heroes: dict[int, Hero] = {}

        self.forced_moves: dict[int, ForcedMove] = {}
        self.channels: dict[int, Channel] = {}
        self._scheduled: list[tuple[float, object]] = []
        self.last_damage_by: dict[int, float] = {}
        self._toggle_acc: dict[tuple[int, int], float] = {}
        self._channel_bound: dict[int, list[tuple[int, str]]] = {}
        self._proc_ready: dict[tuple[int, str], float] = {}
        self._backdoor_accum = 0.0
        self._reflecting = False

        self.events: list[dict] = []
        self.next_wave_time = C.WAVES.get("first_wave_time", 30.0)
        self.wave_number = 0

        self._aura_accum = 0.0
        self._build_map()
        from .neutrals import Neutrals
        self.neutrals = Neutrals(self)
        from .bots import BotDirector
        self.bots = BotDirector(self)

    # --- служебное ---------------------------------------------------------
    def next_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def register(self, u: Unit) -> Unit:
        u.world = self
        self.units[u.id] = u
        if isinstance(u, Hero):
            self.heroes[u.id] = u
        return u

    def get_unit(self, uid: int) -> Unit | None:
        u = self.units.get(uid)
        return u if (u is not None and u.alive) else None

    def all_heroes(self):
        return [h for h in self.heroes.values() if h.alive]

    def schedule(self, delay: float, fn) -> None:
        self._scheduled.append((self.time + max(0.0, delay), fn))

    def emit(self, _event: str, **kw) -> None:
        """Имя первого параметра с подчёркиванием намеренно: поля событий
        приходят через **kw, и обычное имя вроде kind столкнулось бы с ними.

        Ключ «t» зарезервирован под тип события — поле с таким именем
        будет затёрто, поэтому такие имена в событиях запрещены."""
        assert "t" not in kw, f"событие {_event}: поле «t» зарезервировано под тип"
        kw["t"] = _event
        self.events.append(kw)

    def emit_effect(self, fx_kind: str, x: float, y: float, radius: float,
                    key: str, team: int) -> None:
        self.emit("fx", fx=fx_kind, x=round(x), y=round(y), r=round(radius),
                  k=key, team=team)

    def drain_events(self) -> list[dict]:
        ev = self.events
        self.events = []
        return ev

    # --- постройка карты ---------------------------------------------------
    def _build_map(self) -> None:
        for team in (TEAM_DEV, TEAM_MGMT):
            ts = self.teams[team]
            ax, ay = gm.ANCIENT_POS[team]
            anc = self._make_building(E_ANCIENT, team, ax, ay, "ancient")
            ts.ancient_id = anc.id

            fx, fy = gm.FOUNTAIN_POS[team]
            self._make_building(E_FOUNTAIN, team, fx, fy, "fountain")

            for (t, lane, tier), (tx, ty) in gm.tower_positions().items():
                if t != team:
                    continue
                self._make_building(E_TOWER, team, tx, ty, f"tower_t{tier}",
                                    lane=lane, tier=tier)
            for (t, lane, kind), (bx, by) in gm.barracks_positions().items():
                if t != team:
                    continue
                self._make_building(E_BARRACKS, team, bx, by, f"barracks_{kind}",
                                    lane=lane, tier=0)
            for i, (tx, ty) in enumerate(gm.T4_POS[team]):
                self._make_building(E_TOWER, team, tx, ty, "tower_t4", lane="base", tier=4)

        self._link_invulnerability()

    def _make_building(self, etype: str, team: int, x: float, y: float, key: str,
                       lane: str = "", tier: int = 0) -> Building:
        d = C.building_def(key)
        b = Building(self.next_id(), etype, team, x, y, key, lane, tier,
                     name=d.get("name", key))
        b.base_max_hp = float(d.get("hp", 1000))
        dmg = d.get("damage", [0, 0])
        b.base_damage_min, b.base_damage_max = float(dmg[0]), float(dmg[1])
        b.base_armor = float(d.get("armor", 0))
        b.base_magic_resist = float(d.get("magic_resist", 0))
        b.base_attack_range = float(d.get("attack_range", 0))
        b.base_bat = float(d.get("bat", 1.0))
        b.base_hp_regen = float(d.get("hp_regen", 0))
        b.base_vision_day = float(d.get("vision", 1400))
        b.team_bounty = float(d.get("team_bounty", 0))
        b.killer_bounty = float(d.get("killer_bounty", 0))
        b.is_ranged = b.base_attack_range > 200
        b.projectile_speed = 1100.0
        b.attack_point = 0.25
        b.recompute()
        b.hp = b.max_hp
        return self.register(b)

    def _link_invulnerability(self) -> None:
        """Башня уязвима, только когда пала предыдущая по линии. Как в доте."""
        for team in (TEAM_DEV, TEAM_MGMT):
            for lane in gm.LANES:
                chain = sorted(
                    [b for b in self.units.values()
                     if isinstance(b, Building) and b.team == team
                     and b.lane == lane and b.tier in (1, 2, 3)],
                    key=lambda b: b.tier)
                for i, b in enumerate(chain):
                    b.invuln_until_alive = [chain[j].id for j in range(i)]
                rax = [b for b in self.units.values()
                       if isinstance(b, Building) and b.team == team
                       and b.lane == lane and b.etype == E_BARRACKS]
                t3 = [b.id for b in chain if b.tier == 3]
                for r in rax:
                    r.invuln_until_alive = t3
            t4 = [b for b in self.units.values()
                  if isinstance(b, Building) and b.team == team and b.tier == 4]
            all_rax = [b.id for b in self.units.values()
                       if isinstance(b, Building) and b.team == team and b.etype == E_BARRACKS]
            for b in t4:
                b.invuln_until_alive = all_rax
            anc = self.units[self.teams[team].ancient_id]
            anc.invuln_until_alive = [b.id for b in t4]

    def is_invulnerable_building(self, b: Building) -> bool:
        for gid in b.invuln_until_alive:
            g = self.units.get(gid)
            if g is not None and g.alive:
                return True
        return False

    # --- запросы -----------------------------------------------------------
    def units_in_radius(self, x: float, y: float, radius: float, team: int | None = None,
                        include_neutrals: bool = False, alive_only: bool = True) -> list:
        if radius <= 0:
            return []
        rr = radius * radius
        out = []
        for u in self.spatial.query(x, y, radius):
            if alive_only and not u.alive:
                continue
            if team is not None:
                if u.team != team and not (include_neutrals and u.team == TEAM_NEUTRAL):
                    continue
            if u.etype == E_FOUNTAIN:
                continue
            if vmath.dist_sq(x, y, u.x, u.y) <= rr:
                out.append(u)
        return out

    def enemies_in_radius(self, of_team: int, x: float, y: float, radius: float) -> list:
        return [u for u in self.units_in_radius(x, y, radius, team=None)
                if u.team != of_team and u.team != TEAM_NEUTRAL or
                (u.team == TEAM_NEUTRAL and of_team != TEAM_NEUTRAL)]

    # --- главный тик -------------------------------------------------------
    def tick(self, dt: float = TICK_DT) -> None:
        if self.phase == PHASE_FINISHED:
            return
        self.time += dt
        self.tick_count += 1
        self.last_damage_by.clear()

        alive = [u for u in self.units.values() if u.alive]
        self.spatial.rebuild(alive)

        self._run_scheduled()
        self._tick_modifiers(alive, dt)
        self._tick_cooldowns(dt)
        self._tick_toggles(dt)
        self._tick_regen(alive, dt)
        self._tick_auras(alive, dt)
        self._tick_forced_moves(dt)
        self._tick_channels(dt)
        self._tick_ai(alive, dt)
        self._tick_orders(alive, dt)
        self._tick_projectiles(dt)
        self._tick_respawn(dt)
        self._tick_waves()
        self._tick_buildings(dt)
        self.neutrals.tick(dt)
        self.bots.tick(dt)
        self._tick_passive_gold(dt)
        self._check_victory()

    def _run_scheduled(self) -> None:
        if not self._scheduled:
            return
        due = [(t, f) for t, f in self._scheduled if t <= self.time]
        if not due:
            return
        self._scheduled = [(t, f) for t, f in self._scheduled if t > self.time]
        for _t, fn in due:
            fn()

    def _tick_modifiers(self, alive, dt: float) -> None:
        for u in alive:
            fired = u.tick_modifiers(dt)
            for mod, times in fired:
                src = self.units.get(mod.source_id)
                ctx = ab.EffectContext(src if src is not None else u, u, u.x, u.y,
                                       1, mod.ability_key)
                for _ in range(times):
                    for eff in mod.tick_effects:
                        e = dict(eff)
                        e["target"] = "hit"
                        ab.execute(self, ab.EffectContext(
                            ctx.caster, u, u.x, u.y, 1, mod.ability_key), [e])
            if u.flags & F_TAUNTED and u.taunt_source_id:
                src = self.get_unit(u.taunt_source_id)
                if src is not None:
                    u.order_attack(src.id)

    def _tick_cooldowns(self, dt: float) -> None:
        for h in self.heroes.values():
            for a in h.abilities:
                a.tick(dt)
            for it in h.items:
                if it is not None:
                    it.tick(dt)
            if h.buyback_cooldown > 0:
                h.buyback_cooldown = max(0.0, h.buyback_cooldown - dt)
            for d in h.deliveries:
                d["t"] -= dt
            ready = [d for d in h.deliveries if d["t"] <= 0]
            if ready:
                h.deliveries = [d for d in h.deliveries if d["t"] > 0]
                for d in ready:
                    self.deliver_item(h, d["key"])

    def _tick_buildings(self, dt: float) -> None:
        """Защита от бэкдора, реген вне боя и таймер глифа.

        Без защиты от бэкдора один герой с ускорением тихо сносит трон,
        пока команда дерётся на другом конце карты. В доте это лечится
        тем, что строение без своих крипов рядом почти не получает урона
        и быстро восстанавливается.
        """
        rules = C.BUILDING_RULES
        delay = float(rules.get("out_of_combat_regen_delay_sec", 15.0))
        regen = float(rules.get("backdoor_regen_hp_per_sec", 25.0))
        self._backdoor_accum += dt
        recheck = self._backdoor_accum >= 0.5
        if recheck:
            self._backdoor_accum = 0.0
        self._reflecting = False

        for ts in self.teams.values():
            if ts.glyph_cooldown > 0:
                ts.glyph_cooldown = max(0.0, ts.glyph_cooldown - dt)

        for b in self.units.values():
            if not b.is_building or not b.alive or b.etype == E_FOUNTAIN:
                continue
            if recheck:
                b.backdoor_protected = self._is_backdoor(b)
            if b.hp < b.max_hp and self.time - b.last_attacked_time > delay:
                b.hp = min(b.max_hp, b.hp + regen * dt)

    def _is_backdoor(self, b: Building) -> bool:
        """Строение считается защищённым, если рядом нет своих линейных крипов."""
        for u in self.spatial.query(b.x, b.y, 1200.0):
            if u.alive and u.team == b.team and u.etype == E_CREEP:
                if b.dist_sq_to(u) <= 1200.0 ** 2:
                    return False
        return True

    def use_glyph(self, team: int) -> tuple[bool, str]:
        """Глиф укрепления: все строения команды неуязвимы несколько секунд."""
        ts = self.teams[team]
        if ts.glyph_cooldown > 0:
            return False, f"глиф откатится через {int(ts.glyph_cooldown)} с"
        rules = C.BUILDING_RULES
        ts.glyph_cooldown = float(rules.get("glyph_cooldown_sec", 180.0))
        duration = float(rules.get("glyph_duration_sec", 6.0))
        from .modifiers import invulnerable
        for b in self.units.values():
            if b.is_building and b.alive and b.team == team:
                b.add_modifier(invulnerable(duration, 0, "glyph"))
        self.emit("glyph", team=team, dur=duration)
        return True, ""

    def buyback(self, h: Hero) -> tuple[bool, str]:
        """Выкуп: вернуться в бой немедленно за деньги."""
        if h.alive:
            return False, "ты жив"
        if h.buyback_cooldown > 0:
            return False, f"выкуп откатится через {int(h.buyback_cooldown)} с"
        cost = self.buyback_cost(h)
        if h.gold < cost:
            return False, f"нужно {int(cost)} ₿"
        cfg = C.ECONOMY.get("buyback", {})
        h.gold -= cost
        h.buyback_cooldown = float(cfg.get("cooldown_sec", 240.0))
        self.respawn_hero(h)
        self.emit("buyback", id=h.id, cost=round(cost))
        return True, ""

    def buyback_cost(self, h: Hero) -> float:
        cfg = C.ECONOMY.get("buyback", {})
        return (float(cfg.get("base", 100.0))
                + (h.level ** 2) * float(cfg.get("level_sq_factor", 1.5))
                + self.time * float(cfg.get("time_factor", 0.5)))

    def _tick_toggles(self, dt: float) -> None:
        """Включённые способности применяются раз в интервал и жрут ману.

        Без этого не существуют «Духота в серверной» и «Начисление пени» —
        тоггл в спецификации срабатывал бы один раз при включении.
        """
        for h in self.heroes.values():
            if not h.alive:
                continue
            for i, a in enumerate(h.abilities):
                if not a.toggled:
                    continue
                if a.level <= 0 or (h.flags & IS_DISABLED_MASK):
                    a.toggled = False
                    continue
                interval = float(a.defn.get("toggle_interval", 1.0))
                a.charges = getattr(a, "charges", 0)
                key = f"_tg{i}"
                acc = self._toggle_acc.get((h.id, i), 0.0) + dt
                if acc < interval:
                    self._toggle_acc[(h.id, i)] = acc
                    continue
                self._toggle_acc[(h.id, i)] = acc - interval
                cost = a.mana_cost()
                if cost > 0:
                    if h.mana < cost:
                        a.toggled = False
                        self.emit("toggle", id=h.id, k=a.key, on=0)
                        continue
                    h.mana -= cost
                ctx = ab.EffectContext(
                    h, None, h.x, h.y, a.level, a.key,
                    pierces_mi=bool(a.defn.get("pierces_magic_immunity", False)))
                ab.execute(self, ctx, a.defn.get("effects", []))

    def _tick_regen(self, alive, dt: float) -> None:
        for u in alive:
            u.ensure_stats()
            if u.hp_regen:
                u.hp = min(u.max_hp, u.hp + u.hp_regen * dt)
            if u.mana_regen and u.max_mana > 0:
                u.mana = min(u.max_mana, u.mana + u.mana_regen * dt)
        # Фонтан лечит своих
        for team in (TEAM_DEV, TEAM_MGMT):
            fx, fy = gm.FOUNTAIN_POS[team]
            for u in self.units_in_radius(fx, fy, FOUNTAIN_HEAL_RADIUS, team=team):
                if u.etype in (E_HERO, E_SUMMON):
                    u.hp = min(u.max_hp, u.hp + u.max_hp * 0.06 * dt)
                    u.mana = min(u.max_mana, u.mana + u.max_mana * 0.055 * dt)

    def _tick_auras(self, alive, dt: float) -> None:
        """Ауры перевешиваются пачками, а не каждый тик — это заметно дешевле."""
        self._aura_accum += dt
        if self._aura_accum < 0.25:
            return
        self._aura_accum = 0.0
        from .modifiers import Modifier
        for h in self.heroes.values():
            if not h.alive:
                continue
            sources = []
            for a in h.abilities:
                if a.level > 0:
                    sources += ab.auras(a.defn.get("effects", []), a.level)
            for it in h.all_items():
                sources += ab.auras(it.defn.get("passives", []), 1)
            for au in sources:
                team = h.team if au["filter"] == "ally" else enemy_of(h.team)
                data = ({"unique": au["unique"], "unique_rank": au["unique_rank"]}
                        if au.get("unique") else {})
                for t in self.units_in_radius(h.x, h.y, au["radius"], team=team):
                    t.add_modifier(Modifier(
                        au["key"], 0.5, name=au["name"], stats=au["stats"],
                        source_id=h.id, is_aura_effect=True, dispellable=False,
                        data=data))

    def _tick_forced_moves(self, dt: float) -> None:
        if not self.forced_moves:
            return
        done = []
        for uid, fm in self.forced_moves.items():
            u = self.units.get(uid)
            if u is None or not u.alive:
                done.append(uid)
                continue
            fm.elapsed += dt
            t = min(1.0, fm.elapsed / fm.duration)
            nx = fm.sx + (fm.tx - fm.sx) * t
            ny = fm.sy + (fm.ty - fm.sy) * t
            if gm.is_walkable(nx, ny):
                u.x, u.y = nx, ny
            else:
                u.x, u.y = gm.nearest_walkable(nx, ny)
                done.append(uid)
                continue
            if t >= 1.0:
                done.append(uid)
        for uid in done:
            self.forced_moves.pop(uid, None)

    def _tick_channels(self, dt: float) -> None:
        if not self.channels:
            return
        from .consts import IS_DISABLED
        ended = []
        for uid, ch in self.channels.items():
            u = self.units.get(uid)
            if u is None or not u.alive or (u.flags & IS_DISABLED):
                ended.append(uid)
                continue
            if ch.break_on_move and vmath.dist(u.x, u.y, ch.start_x, ch.start_y) > 20.0:
                ended.append(uid)
                continue
            ch.remaining -= dt
            ch.accum += dt
            while ch.accum >= ch.interval:
                ch.accum -= ch.interval
                ab.execute(self, ch.ctx, ch.on_tick)
            if ch.remaining <= 0.0:
                if ch.on_finish:
                    ab.execute(self, ch.ctx, ch.on_finish)
                ended.append(uid)
        for uid in ended:
            ch = self.channels.pop(uid, None)
            u = self.units.get(uid)
            if u is not None:
                u.remove_modifier("_channeling")
            self._release_channel_bound(uid)

    # --- ИИ крипов, башен и нейтралов --------------------------------------
    def _tick_ai(self, alive, dt: float) -> None:
        for u in alive:
            if isinstance(u, Creep):
                self._creep_ai(u)
            elif isinstance(u, Building) and u.etype in (E_TOWER, E_FOUNTAIN):
                self._tower_ai(u)

    def _creep_ai(self, c: Creep) -> None:
        if c.flags & F_TAUNTED:
            return
        cur = self.get_unit(c.attack_target_id)
        if cur is not None and c.dist_sq_to(cur) <= (CREEP_AGGRO_RADIUS * 1.4) ** 2:
            return
        target = self._pick_creep_target(c)
        if target is not None:
            c.order_attack(target.id)
            return
        if c.is_neutral:
            if vmath.dist(c.x, c.y, c.spawn_x, c.spawn_y) > 60:
                c.order_move_to(c.spawn_x, c.spawn_y, [(c.spawn_x, c.spawn_y)])
            else:
                c.order_hold()
            return
        self._advance_lane(c)

    def _pick_creep_target(self, c: Creep):
        radius = CREEP_AGGRO_RADIUS if not c.is_neutral else c.leash_radius * 0.5
        best = None
        best_score = 1e18
        for u in self.spatial.query(c.x, c.y, radius):
            if not u.alive or u.etype == E_FOUNTAIN or not u.can_be_attacked:
                continue
            if c.is_neutral:
                if u.team == TEAM_NEUTRAL:
                    continue
            elif u.team == c.team or u.team == TEAM_NEUTRAL:
                continue
            if not u.is_visible_to(c.team):
                continue
            if isinstance(u, Building) and self.is_invulnerable_building(u):
                continue
            d = c.dist_sq_to(u)
            if d > radius * radius:
                continue
            # Приоритет как в доте: кто бьёт меня > крипы > герои > строения
            prio = 3
            if u.last_attacker_id == c.id or c.last_attacker_id == u.id:
                prio = 0
            elif u.etype in (E_CREEP, E_NEUTRAL, E_SUMMON):
                prio = 1
            elif u.etype == E_HERO:
                prio = 2
            score = prio * 1e7 + d
            if score < best_score:
                best_score, best = score, u
        return best

    def _advance_lane(self, c: Creep) -> None:
        if not c.waypoints:
            return
        if c.wp_idx >= len(c.waypoints):
            enemy_anc = self.units.get(self.teams[enemy_of(c.team)].ancient_id)
            if enemy_anc is not None and enemy_anc.alive:
                c.order_attack(enemy_anc.id)
            return
        wx, wy = c.waypoints[c.wp_idx]
        if vmath.dist_sq(c.x, c.y, wx, wy) < 140.0 ** 2:
            c.wp_idx += 1
            if c.wp_idx >= len(c.waypoints):
                return
            wx, wy = c.waypoints[c.wp_idx]
        c.order = ORDER_ATTACK_MOVE
        c.order_x, c.order_y = wx, wy
        c.path = [(wx, wy)]
        c.path_idx = 0

    def _tower_ai(self, t: Building) -> None:
        if t.base_damage_max <= 0:
            return
        cur = self.get_unit(t.attack_target_id)
        radius = t.attack_range + ATTACK_RANGE_BUFFER
        if cur is not None and t.dist_sq_to(cur) <= radius * radius and \
                cur.is_visible_to(t.team):
            return
        best, best_score = None, 1e18
        for u in self.spatial.query(t.x, t.y, radius):
            if not u.alive or u.team == t.team or u.team == TEAM_NEUTRAL:
                continue
            if not u.can_be_attacked:
                continue
            if u.is_building or not u.is_visible_to(t.team):
                continue
            if t.dist_sq_to(u) > radius * radius:
                continue
            # Башня переключается на героя, ударившего союзного героя рядом
            prio = 1 if u.etype == E_HERO and self._threatens_ally_hero(u, t.team) else 2
            if u.etype not in (E_HERO,):
                prio = 3
            score = prio * 1e7 + t.dist_sq_to(u)
            if score < best_score:
                best_score, best = score, u
        if best is not None:
            t.order_attack(best.id)
        else:
            t.attack_target_id = 0
            t.order = ORDER_NONE

    def _threatens_ally_hero(self, u: Unit, team: int) -> bool:
        if self.time - u.last_attacked_time > 3.0:
            return False
        victim = self.units.get(u.attack_target_id)
        return victim is not None and victim.team == team and victim.etype == E_HERO

    # --- исполнение приказов -----------------------------------------------
    def _tick_orders(self, alive, dt: float) -> None:
        for u in alive:
            if u.id in self.forced_moves or u.id in self.channels:
                continue
            if u.attack_windup > 0.0:
                self._progress_windup(u, dt)
                continue
            if u.attack_cd > 0.0:
                u.attack_cd = max(0.0, u.attack_cd - dt)

            order = u.order
            if order == ORDER_ATTACK_UNIT:
                self._do_attack_order(u, dt)
            elif order == ORDER_MOVE:
                self._do_move_order(u, dt)
            elif order == ORDER_ATTACK_MOVE:
                self._do_attack_move(u, dt)
            elif order == ORDER_HOLD:
                self._do_hold(u, dt)
            elif order == ORDER_NONE or order == ORDER_STOP:
                if u.etype == E_HERO:
                    self._auto_acquire(u)

    def _do_move_order(self, u: Unit, dt: float) -> None:
        if not u.can_move:
            return
        pend = u.pending_cast
        if pend is not None and isinstance(u, Hero):
            a = u.abilities[pend["idx"]]
            if vmath.dist(u.x, u.y, pend["x"], pend["y"]) <= a.cast_range + u.radius:
                u.pending_cast = None
                self.cast_ability(u, pend["idx"], pend["target"], pend["x"], pend["y"])
                return
        if not u.path:
            u.clear_order()
            return
        tx, ty = u.path[u.path_idx]
        if u.step_towards(tx, ty, dt):
            u.path_idx += 1
            if u.path_idx >= len(u.path):
                u.clear_order()

    def _do_attack_order(self, u: Unit, dt: float) -> None:
        target = self.get_unit(u.order_target_id)
        if target is None or not target.is_visible_to(u.team):
            u.clear_order()
            u.attack_target_id = 0
            return
        if isinstance(target, Building) and self.is_invulnerable_building(target):
            u.clear_order()
            return
        if u.in_attack_range(target):
            u.path = []
            if u.face_towards(target.x, target.y, dt) and u.attack_cd <= 0.0 and u.can_attack:
                self._begin_attack(u, target)
        elif u.can_move:
            self._chase(u, target, dt)

    def _chase(self, u: Unit, target: Unit, dt: float) -> None:
        if not u.path or vmath.dist_sq(u.path[-1][0], u.path[-1][1],
                                       target.x, target.y) > 220.0 ** 2:
            u.path = gm.find_path(u.x, u.y, target.x, target.y)
            u.path_idx = 0
        if not u.path:
            u.step_towards(target.x, target.y, dt)
            return
        tx, ty = u.path[min(u.path_idx, len(u.path) - 1)]
        if u.step_towards(tx, ty, dt):
            u.path_idx = min(u.path_idx + 1, len(u.path) - 1)

    def _do_attack_move(self, u: Unit, dt: float) -> None:
        target = self.get_unit(u.attack_target_id)
        if target is None or not u.in_attack_range(target) or not target.is_visible_to(u.team):
            target = self._nearest_enemy(u, u.attack_range + ATTACK_RANGE_BUFFER)
            if target is not None:
                u.attack_target_id = target.id
        if target is not None and u.in_attack_range(target):
            if u.face_towards(target.x, target.y, dt) and u.attack_cd <= 0.0 and u.can_attack:
                self._begin_attack(u, target)
            return
        near = self._nearest_enemy(u, CREEP_AGGRO_RADIUS)
        if near is not None and u.can_move:
            self._chase(u, near, dt)
            return
        if u.can_move and u.path:
            tx, ty = u.path[min(u.path_idx, len(u.path) - 1)]
            if u.step_towards(tx, ty, dt):
                u.path_idx += 1
                if u.path_idx >= len(u.path):
                    u.path = []

    def _do_hold(self, u: Unit, dt: float) -> None:
        target = self.get_unit(u.attack_target_id)
        if target is None or not u.in_attack_range(target):
            target = self._nearest_enemy(u, u.attack_range + ATTACK_RANGE_BUFFER)
            u.attack_target_id = target.id if target is not None else 0
        if target is not None and u.attack_cd <= 0.0 and u.can_attack:
            if u.face_towards(target.x, target.y, dt):
                self._begin_attack(u, target)

    def _auto_acquire(self, u: Unit) -> None:
        if u.attack_cd > 0.0 or not u.can_attack:
            return
        target = self.get_unit(u.attack_target_id)
        if target is not None and u.in_attack_range(target):
            self._begin_attack(u, target)
            return
        near = self._nearest_enemy(u, u.attack_range + ATTACK_RANGE_BUFFER)
        if near is not None:
            u.attack_target_id = near.id
            self._begin_attack(u, near)

    def _nearest_enemy(self, u: Unit, radius: float):
        best, best_d = None, radius * radius
        for e in self.spatial.query(u.x, u.y, radius):
            if not e.alive or e.team == u.team or e.etype == E_FOUNTAIN:
                continue
            if not e.can_be_attacked:
                continue
            if not e.is_visible_to(u.team):
                continue
            if isinstance(e, Building) and self.is_invulnerable_building(e):
                continue
            d = u.dist_sq_to(e)
            if d < best_d:
                best_d, best = d, e
        return best

    # --- атака -------------------------------------------------------------
    def _begin_attack(self, u: Unit, target: Unit) -> None:
        u.attack_target_id = target.id
        u.attack_windup = u.attack_point
        u.last_attacked_time = self.time

    def _progress_windup(self, u: Unit, dt: float) -> None:
        u.attack_windup -= dt
        if u.attack_windup > 0.0:
            return
        u.attack_windup = 0.0
        target = self.get_unit(u.attack_target_id)
        if target is None or not u.can_attack:
            return
        if not u.in_attack_range(target):
            return
        u.attack_cd = combat.attack_time(u.bat, u.attack_speed)
        if u.is_ranged and u.projectile_speed > 0:
            self._spawn_attack_projectile(u, target)
        else:
            self._land_attack(u, target)

    def _spawn_attack_projectile(self, u: Unit, target: Unit) -> None:
        dmg, crit, miss = combat.roll_attack_damage(u, target, self.rng)
        p = Projectile(self.next_id(), u.team, u.x, u.y, u.projectile_speed,
                       u.id, target.id, visual="attack")
        p.is_attack = True
        p.attack_damage = dmg
        p.is_crit = crit
        p.world = self
        if miss:
            p.attack_damage = 0.0
        self.projectiles.append(p)

    def _land_attack(self, u: Unit, target: Unit, predamage: float | None = None,
                     crit: bool = False) -> None:
        if not target.alive:
            return
        if predamage is None:
            dmg, crit, miss = combat.roll_attack_damage(u, target, self.rng)
            if miss:
                self.emit("miss", id=target.id)
                return
        else:
            dmg = predamage
            if dmg <= 0.0:
                self.emit("miss", id=target.id)
                return

        res = combat.apply_damage(self, target, dmg, DMG_PHYSICAL, u,
                                  SRC_TOWER if u.is_building else SRC_ATTACK)
        if crit:
            self.emit("crit", id=target.id, v=round(res.dealt))

        if u.lifesteal > 0 and res.dealt > 0 and not u.is_building:
            combat.heal(self, u, res.dealt * u.lifesteal, u, "lifesteal")

        if u.cleave_pct > 0 and u.cleave_radius > 0 and res.dealt > 0:
            for e in self.units_in_radius(target.x, target.y, u.cleave_radius,
                                          team=None):
                if e.team == u.team or e is target or e.is_building:
                    continue
                combat.apply_damage(self, e, res.dealt * u.cleave_pct, DMG_PHYSICAL,
                                    u, SRC_ATTACK)

        if u.bash_chance > 0 and self.rng.random() < u.bash_chance:
            from .modifiers import stun
            target.add_modifier(stun(target.scaled_duration(u.bash_duration), u.id, "bash"))

        for proc in getattr(u, "attack_procs", ()):
            if proc["cooldown"] > 0:
                gate = (u.id, proc["key"]) if not proc["once_per_target"] \
                    else (u.id, proc["key"], target.id)
                if self._proc_ready.get(gate, 0.0) > self.time:
                    continue
            if proc["chance"] < 1.0 and self.rng.random() >= proc["chance"]:
                continue
            if proc["cooldown"] > 0:
                self._proc_ready[gate] = self.time + proc["cooldown"]
            ab.execute(self, ab.EffectContext(u, target, target.x, target.y,
                                              proc["level"], "attack_proc"),
                       proc["effects"])

    def _tick_projectiles(self, dt: float) -> None:
        if not self.projectiles:
            return
        alive_p = []
        for p in self.projectiles:
            if self._advance_projectile(p, dt):
                alive_p.append(p)
        self.projectiles = alive_p

    def _advance_projectile(self, p: Projectile, dt: float) -> bool:
        """Шаг снаряда. False — снаряд отработал и снимается.

        Снаряд с наведением на юнита ведёт цель. Снаряд в точку — это скиллшот:
        он сталкивается с первым, кого заденет по пути, а с pierce задевает всех.
        """
        if p.target_id:
            target = self.get_unit(p.target_id)
            if target is None:
                return False
            tx, ty = target.x, target.y
        else:
            tx, ty = p.tx, p.ty

        step = p.speed * dt
        nx, ny, arrived = vmath.move_towards(p.x, p.y, tx, ty, step)
        p.traveled += vmath.dist(p.x, p.y, nx, ny)
        p.x, p.y = nx, ny

        if not p.target_id and p.radius_hit > 0:
            hits = [u for u in self.units_in_radius(p.x, p.y, p.radius_hit, team=None)
                    if u.team != p.team and u.team != TEAM_NEUTRAL
                    and u.id not in p.hit_ids
                    and not u.is_building and u.etype != E_FOUNTAIN]
            if hits:
                if p.pierce:
                    for u in hits:
                        p.hit_ids.add(u.id)
                        self._projectile_hit(p, u)
                else:
                    hits.sort(key=lambda u: vmath.dist_sq(p.x, p.y, u.x, u.y))
                    first = hits[0]
                    p.hit_ids.add(first.id)
                    self._projectile_hit(p, first)
                    return False

        if p.max_dist and p.traveled >= p.max_dist:
            return False

        if arrived:
            if p.target_id:
                target = self.get_unit(p.target_id)
                if target is not None:
                    self._projectile_hit(p, target)
            return False
        return True

    def _projectile_hit(self, p: Projectile, target: Unit) -> None:
        src = self.units.get(p.source_id)
        if p.is_attack:
            if src is not None:
                self._land_attack(src, target, p.attack_damage, p.is_crit)
            return
        if src is None or not p.on_hit:
            return
        ctx = ab.EffectContext(src, target, target.x, target.y,
                               p.level, p.ability_key)
        ab.execute(self, ctx, p.on_hit)

    # --- API для способностей ----------------------------------------------
    def teleport_unit(self, u: Unit, x: float, y: float) -> None:
        x, y = gm.nearest_walkable(x, y)
        u.x, u.y = x, y
        u.path = []
        self.emit("blink", id=u.id, x=round(x), y=round(y))

    def start_forced_move(self, u: Unit, tx: float, ty: float, duration: float) -> None:
        tx, ty = vmath.clamp(tx, 40, gm.SIZE - 40), vmath.clamp(ty, 40, gm.SIZE - 40)
        self.forced_moves[u.id] = ForcedMove(u.x, u.y, tx, ty, duration)

    def bind_to_channel(self, caster_id: int, target_id: int, key: str) -> None:
        self._channel_bound.setdefault(caster_id, []).append((target_id, key))

    def _release_channel_bound(self, caster_id: int) -> None:
        for target_id, key in self._channel_bound.pop(caster_id, ()):
            u = self.units.get(target_id)
            if u is not None:
                u.remove_modifier(key)

    def start_channel(self, u: Unit, ctx, duration: float, interval: float,
                      on_tick: list, break_on_move: bool, on_finish: list) -> None:
        from .modifiers import Modifier
        u.add_modifier(Modifier("_channeling", duration, name="Канал",
                                flags=F_CHANNELING, dispellable=False))
        self.channels[u.id] = Channel(ctx, duration, interval, on_tick,
                                      break_on_move, on_finish, u.x, u.y)

    def spawn_ability_projectile(self, caster, ctx, speed: float, target=None,
                                 tx: float = 0.0, ty: float = 0.0, on_hit=None,
                                 radius: float = 0.0, pierce: bool = False,
                                 max_dist: float = 0.0, visual: str = "bolt") -> None:
        p = Projectile(self.next_id(), caster.team, caster.x, caster.y, speed,
                       caster.id, target.id if target is not None else 0,
                       tx, ty, visual)
        p.on_hit = on_hit or []
        p.radius_hit = radius
        p.pierce = pierce
        p.max_dist = max_dist
        p.ability_key = ctx.ability_key
        p.level = ctx.level
        p.world = self
        self.projectiles.append(p)

    def spawn_summon(self, owner, unit_key: str, x: float, y: float,
                     duration: float) -> Creep:
        d = C.creep_def(unit_key)
        x, y = gm.nearest_walkable(x, y)
        s = Creep(self.next_id(), owner.team, x, y, unit_key, name=d.get("name", unit_key))
        s.etype = E_SUMMON
        self._apply_creep_stats(s, d)
        s.owner_id = owner.id
        self.register(s)
        if duration > 0:
            self.schedule(duration, lambda u=s: self.kill_unit(u, None, "expire"))
        return s

    def spawn_illusions(self, owner: Hero, count: int, duration: float,
                        out_pct: float, in_pct: float) -> None:
        from .modifiers import Modifier
        existing = [u for u in self.units.values()
                    if u.alive and u.etype == E_ILLUSION and u.owner_id == owner.id]
        cap = 8
        while len(existing) + count > cap and existing:
            self.kill_unit(existing.pop(0), None, "illusion_cap")
        for i in range(count):
            ang = self.rng.random() * math.tau
            dx, dy = vmath.from_angle(ang, 110.0)
            x, y = gm.nearest_walkable(owner.x + dx, owner.y + dy)
            il = Hero(self.next_id(), owner.team, x, y, owner.hero_key,
                      name=owner.name)
            il.etype = E_ILLUSION
            for attr in ("base_str", "base_agi", "base_int", "str_gain", "agi_gain",
                         "int_gain", "base_max_hp", "base_max_mana", "base_damage_min",
                         "base_damage_max", "base_armor", "base_move_speed",
                         "base_attack_range", "base_bat", "is_ranged",
                         "projectile_speed", "primary", "level"):
                setattr(il, attr, getattr(owner, attr))
            il.owner_id = owner.id
            il.is_bot = True
            il.add_modifier(Modifier("illusion", duration, name="Иллюзия",
                                     stats={"damage_taken_pct": in_pct - 100.0},
                                     dispellable=False, permanent=False))
            il.recompute()
            il.hp = il.max_hp
            il.damage_min *= out_pct / 100.0
            il.damage_max *= out_pct / 100.0
            self.register(il)
            self.schedule(duration, lambda u=il: self.kill_unit(u, None, "expire"))

    def run_damage_reactions(self, target, attacker, amount: float, dtype: str) -> None:
        """Срабатывания «когда меня бьют»: возврат урона, блокировка телепорта."""
        if attacker is None or attacker is target:
            return
        reactions = []
        for eff, _src in getattr(target, "on_damaged_procs", ()) or ():
            reactions.append((eff.get("effects") or [],
                              float(eff.get("reflect_pct", 0))))
        for m in target.modifiers:
            if m.data and "reflect_effects" in m.data:
                reactions.append((m.data["reflect_effects"],
                                  float(m.data.get("reflect_pct", 0))))
        if not reactions:
            return
        # Отражённый урон сам не отражается. Иначе два предмета возврата
        # друг против друга уходят в бесконечную рекурсию и роняют матч.
        if self._reflecting:
            return
        self._reflecting = True
        try:
            for inner, pct in reactions:
                if pct and not inner:
                    # Одного процента достаточно: описывать операцию урона
                    # в данных не нужно
                    scaled = [{"op": "damage", "dtype": DMG_PURE,
                               "amount": amount * pct / 100.0, "target": "hit"}]
                elif pct:
                    scaled = [dict(e, amount=amount * pct / 100.0)
                              if e.get("op") == "damage" else e for e in inner]
                elif inner:
                    scaled = inner
                else:
                    continue
                ctx = ab.EffectContext(target, attacker, attacker.x, attacker.y,
                                       1, "reflect", source=SRC_ITEM)
                ab.execute(self, ctx, scaled)
        finally:
            self._reflecting = False
        # Телепорт блокируется уроном от героя — как кинжал в доте
        if attacker.etype == E_HERO and isinstance(target, Hero):
            for it in target.all_items():
                if it.defn.get("blocked_by_damage") or _has_blink(it.defn):
                    it.disabled_until = self.time + float(
                        it.defn.get("damage_block_sec", 3.0))

    def record_damage(self, attacker, target, amount: float, dtype: str, key: str) -> None:
        if attacker is not None:
            self.last_damage_by[attacker.id] = \
                self.last_damage_by.get(attacker.id, 0.0) + amount
            if isinstance(attacker, Hero):
                if target.etype == E_HERO:
                    attacker.hero_damage += amount
                elif target.is_building:
                    attacker.tower_damage += amount
        if target.etype == E_HERO and attacker is not None and \
                attacker.team != target.team:
            self._credit_assist(target, attacker)
        self.emit("dmg", id=target.id, v=round(amount), dt=dtype)
        if attacker is not None and attacker.etype == E_HERO:
            self._break_fragile_buffs(target)
        self.run_damage_reactions(target, attacker, amount, dtype)

    def record_heal(self, healer, target, amount: float, key: str) -> None:
        if isinstance(healer, Hero):
            healer.healing_done += amount
        self.emit("heal", id=target.id, v=round(amount))

    def _break_fragile_buffs(self, u: Unit) -> None:
        """Реген от бутылки и мази сбивается уроном героя, как в доте."""
        fragile = [m.key for m in u.modifiers if m.data.get("break_on_damage")]
        for key in fragile:
            u.remove_modifier(key)

    def _run_death_marks(self, victim: Unit, killer) -> None:
        """Метки вроде Track платят команде, когда помеченный умирает
        от чьей угодно руки, а не только от руки поставившего метку."""
        for m in list(victim.modifiers):
            effects = m.data.get("on_death_effects")
            if not effects:
                continue
            src = self.units.get(m.source_id)
            if src is None:
                continue
            level = int(m.data.get("on_death_level", 1))
            ctx = ab.EffectContext(src, victim, victim.x, victim.y, level,
                                   m.ability_key)
            ab.execute(self, ctx, effects)

    def _credit_assist(self, victim: Hero, attacker) -> None:
        owner = attacker
        if getattr(attacker, "owner_id", 0):
            owner = self.units.get(attacker.owner_id) or attacker
        if isinstance(owner, Hero):
            victim.assist_credit[owner.id] = self.time

    # ======================================================================
    #  Спавн юнитов
    # ======================================================================
    def _apply_creep_stats(self, c: Creep, d: dict) -> None:
        c.base_max_hp = float(d["hp"])
        c.base_damage_min, c.base_damage_max = d["damage"]
        c.base_armor = float(d["armor"])
        c.base_magic_resist = float(d["magic_resist"])
        c.base_attack_range = float(d["attack_range"])
        c.base_bat = float(d["bat"])
        c.base_move_speed = float(d["move_speed"])
        c.base_hp_regen = float(d.get("hp_regen", 0.0))
        c.base_vision_day = float(d["vision"])
        c.bounty_gold = self.rng.uniform(*d["bounty_gold"])
        c.bounty_xp = float(d["bounty_xp"])
        c.is_ranged = c.base_attack_range > 200
        c.projectile_speed = 900.0
        c.attack_point = 0.3
        c.recompute()
        c.hp = c.max_hp
        c.mana = c.max_mana

    def spawn_hero(self, team: int, hero_key: str, player_id: int = 0,
                   name: str = "", is_bot: bool = False) -> Hero:
        d = C.hero_def(hero_key)
        sx, sy = gm.SPAWN_POS[team]
        sx += self.rng.uniform(-90, 90)
        sy += self.rng.uniform(-90, 90)
        sx, sy = gm.nearest_walkable(sx, sy)
        h = Hero(self.next_id(), team, sx, sy, hero_key, name=name or d.get("name", hero_key))
        h.player_id = player_id
        h.is_bot = is_bot
        h.primary = d.get("primary", "str")
        h.base_str, h.str_gain = float(d["base_str"]), float(d["str_gain"])
        h.base_agi, h.agi_gain = float(d["base_agi"]), float(d["agi_gain"])
        h.base_int, h.int_gain = float(d["base_int"]), float(d["int_gain"])
        h.base_damage_min, h.base_damage_max = [float(v) for v in d["base_damage"]]
        h.base_armor = float(d.get("base_armor", 0))
        h.base_hp_regen = float(d.get("base_hp_regen", 0.5))
        h.base_mana_regen = float(d.get("base_mana_regen", 0.9))
        h.base_move_speed = float(d.get("move_speed", 300))
        h.base_attack_range = float(d.get("attack_range", 150))
        h.base_bat = float(d.get("bat", 1.7))
        h.base_vision_day = float(d.get("vision_day", 1800))
        h.base_vision_night = float(d.get("vision_night", 800))
        h.base_max_hp = 200.0
        h.base_max_mana = 75.0
        h.is_ranged = d.get("attack_type") == "ranged"
        h.projectile_speed = float(d.get("projectile_speed", 0)) or 900.0
        h.attack_point = 0.35

        from .abilities import Ability
        h.abilities = [Ability(a, h.id) for a in d.get("abilities", [])]
        h.gold = float(C.ECONOMY.get("starting_gold", 800))
        h.recompute()
        h.hp, h.mana = h.max_hp, h.max_mana
        self.register(h)
        self.emit("hero_spawn", id=h.id, team=team, key=hero_key, name=h.name)
        return h

    # --- волны крипов ------------------------------------------------------
    def _lane_waypoints(self, team: int, lane: str) -> list[tuple[float, float]]:
        pts = list(gm.LANE_PATHS[lane])
        if team == TEAM_MGMT:
            pts.reverse()
        enemy_anc = gm.ANCIENT_POS[enemy_of(team)]
        return pts[1:] + [enemy_anc]

    def _tick_waves(self) -> None:
        if self.time < self.next_wave_time:
            return
        self.next_wave_time += C.WAVES["interval"]
        self.wave_number += 1
        for team in (TEAM_DEV, TEAM_MGMT):
            for lane in gm.LANES:
                self._spawn_wave(team, lane)
        self.emit("wave", n=self.wave_number)

    def _spawn_wave(self, team: int, lane: str) -> None:
        ts = self.teams[team]
        rax_down = ts.barracks_down[lane]
        melee_key = "super_melee" if "melee" in rax_down else "melee_creep"
        ranged_key = "super_ranged" if "ranged" in rax_down else "ranged_creep"

        t = 0.05 if team == TEAM_DEV else 0.95
        bx, by = gm.point_at_t(gm.LANE_PATHS[lane], t)
        waypoints = self._lane_waypoints(team, lane)

        plan = ([melee_key] * C.WAVES["melee_per_wave"] +
                [ranged_key] * C.WAVES["ranged_per_wave"])
        if (self.time >= C.WAVES["siege_first_time"]
                and self.wave_number % max(1, C.WAVES["siege_every_n"]) == 0):
            plan += [C.WAVES["siege_unit"]] * C.WAVES["siege_count"]

        for i, key in enumerate(plan):
            ang = (i / max(1, len(plan))) * math.tau
            dx, dy = vmath.from_angle(ang, 70.0 + 18.0 * (i % 3))
            x, y = gm.nearest_walkable(bx + dx, by + dy)
            d = C.creep_def(key)
            c = Creep(self.next_id(), team, x, y, key, lane, name=d["name"])
            self._apply_creep_stats(c, d)
            c.waypoints = waypoints
            c.wp_idx = 0
            if ts.mega_creeps:
                c.is_super = True
                c.add_modifier(self._mega_buff())
            self.register(c)

    def _mega_buff(self):
        from .modifiers import Modifier
        return Modifier("mega", 0.0, name="Мега-крип", permanent=True,
                        stats={"hp": 200, "damage": 15, "armor": 3},
                        dispellable=False)

    # --- смерть и награды --------------------------------------------------
    def kill_unit(self, u: Unit, killer, reason: str = "") -> None:
        if not u.alive:
            return
        u.alive = False
        u.hp = 0.0
        u.clear_order()
        u.attack_target_id = 0
        self.forced_moves.pop(u.id, None)
        self.channels.pop(u.id, None)

        owner = killer
        if killer is not None and getattr(killer, "owner_id", 0):
            owner = self.units.get(killer.owner_id) or killer

        # Метки читаются ДО обработки смерти: она снимает все модификаторы,
        # и метка исчезла бы, не успев выплатить награду.
        self._run_death_marks(u, owner)

        if u.etype == E_HERO:
            self._on_hero_death(u, owner)
        elif u.is_building:
            self._on_building_death(u, owner)
        elif u.etype in (E_CREEP, E_NEUTRAL, E_SUMMON):
            self._on_creep_death(u, owner)
            if u.etype == E_NEUTRAL:
                self.neutrals.on_camp_unit_died(u)

        u.on_death(killer)
        self.emit("death", id=u.id, killer=owner.id if owner is not None else 0)

        # Строения остаются в реестре навсегда: на них ссылается цепочка
        # неуязвимости соседних башен, и клиенту нужно показать руины.
        # Герои остаются, потому что возрождаются. Удаляются только крипы.
        if not u.is_building and u.etype != E_HERO:
            self.schedule(0.6, lambda uid=u.id: self.units.pop(uid, None))

    def _income_mult(self, team: int) -> float:
        if not C.DYNAMIC_ECONOMY_ENABLED:
            return 1.0
        own = [h for h in self.heroes.values() if h.team == team and h.etype == E_HERO]
        enemy = [h for h in self.heroes.values()
                 if h.team == enemy_of(team) and h.etype == E_HERO]
        if not own:
            return 1.0
        own_p = sum(C.BOT_POWER if h.is_bot else C.HUMAN_POWER for h in own)
        enemy_p = sum(C.BOT_POWER if h.is_bot else C.HUMAN_POWER for h in enemy)
        return (C.team_income_multiplier(len(own))
                * C.underdog_multiplier(own_p, enemy_p or own_p))

    def grant_gold(self, hero: Hero, amount: float, reason: str = "",
                   apply_mult: bool = True) -> float:
        if hero is None or hero.etype != E_HERO:
            return 0.0
        if apply_mult:
            amount *= self._income_mult(hero.team)
        hero.gold += amount
        hero.total_gold_earned += amount
        self.teams[hero.team].gold_earned += amount
        self.emit("gold", id=hero.id, v=round(amount), why=reason)
        return amount

    def grant_xp(self, hero: Hero, amount: float, apply_mult: bool = True) -> None:
        if hero is None or hero.etype != E_HERO or not hero.alive:
            return
        if apply_mult:
            amount *= self._income_mult(hero.team)
        hero.xp += amount
        new_level = C.level_for_xp(hero.xp)
        while hero.level < new_level:
            hero.level += 1
            hero.ability_points += 1
            hero._stats_dirty = True
            hero.ensure_stats()
            hero.hp = min(hero.max_hp, hero.hp + 100)
            self.emit("levelup", id=hero.id, lvl=hero.level)

    def _share_xp(self, x: float, y: float, team: int, total_xp: float) -> None:
        radius = float(C.ECONOMY.get("xp_share_radius", 1300))
        near = [h for h in self.heroes.values()
                if h.alive and h.team == team and h.etype == E_HERO
                and vmath.dist_sq(x, y, h.x, h.y) <= radius * radius]
        if not near:
            return
        each = total_xp / len(near)
        for h in near:
            self.grant_xp(h, each)

    def _on_creep_death(self, c: Creep, killer) -> None:
        if isinstance(killer, Hero) and killer.team != c.team:
            killer.last_hits += 1
            self.grant_gold(killer, c.bounty_gold, "creep")
        elif isinstance(killer, Hero) and killer.team == c.team:
            killer.denies += 1
        enemy_team = enemy_of(c.team) if c.team != TEAM_NEUTRAL else \
            (killer.team if killer is not None else TEAM_DEV)
        self._share_xp(c.x, c.y, enemy_team, c.bounty_xp)

    def _on_building_death(self, b: Building, killer) -> None:
        ts = self.teams[b.team]
        enemy = enemy_of(b.team)
        if b.team_bounty:
            for h in self.heroes.values():
                if h.team == enemy and h.etype == E_HERO:
                    self.grant_gold(h, b.team_bounty, "building_team", apply_mult=False)
        if isinstance(killer, Hero) and b.killer_bounty:
            self.grant_gold(killer, b.killer_bounty, "building", apply_mult=False)

        if b.etype == E_TOWER:
            self.teams[enemy].tower_kills += 1
            self.emit("tower_down", team=b.team, lane=b.lane, tier=b.tier)
        elif b.etype == E_BARRACKS:
            kind = "melee" if "melee" in b.kind else "ranged"
            ts.barracks_down[b.lane].add(kind)
            self.emit("rax_down", team=b.team, lane=b.lane, kind=kind)
            if all(len(ts.barracks_down[l]) >= 2 for l in gm.LANES):
                ts.mega_creeps = True
                self.emit("mega", team=enemy)
        elif b.etype == E_ANCIENT:
            self.phase = PHASE_FINISHED
            self.winner = enemy
            self.emit("victory", team=enemy, name=TEAM_NAMES[enemy])

    def _on_hero_death(self, h: Hero, killer) -> None:
        for i, it in enumerate(h.items):
            if it is not None and it.defn.get("drop_on_death"):
                h.items[i] = None
                h._stats_dirty = True
                self.emit("item_drop", id=h.id, k=it.key,
                          x=round(h.x), y=round(h.y))
        h.deaths += 1
        h.kill_streak = 0
        h.respawn_timer = C.respawn_time(h.level)
        h.purge(True)
        h.modifiers = [m for m in h.modifiers if m.permanent]
        h._stats_dirty = True

        eco = C.ECONOMY.get("hero_kill", {})
        base_gold = float(eco.get("base_gold", C.ECONOMY.get("hero_kill_base", 120)))
        per_level = float(eco.get("gold_per_level", C.ECONOMY.get("hero_kill_per_level", 18)))
        xp_base = float(eco.get("xp_base", 60))
        xp_per_level = float(eco.get("xp_per_level", 12))
        bounty = base_gold + per_level * h.level
        xp_reward = xp_base + xp_per_level * h.level

        streaks = eco.get("streak_bounty_gold") or C.ECONOMY.get("streak_bonus") or []
        if streaks and h.kill_streak < len(streaks):
            bounty += float(streaks[min(h.kill_streak, len(streaks) - 1)])

        if isinstance(killer, Hero) and killer.team != h.team:
            killer.kills += 1
            killer.kill_streak += 1
            self.grant_gold(killer, bounty, "kill")
            self.emit("kill", killer=killer.id, victim=h.id)
        else:
            self.emit("kill", killer=0, victim=h.id)

        share = float(C.ECONOMY.get("assist_gold_share",
                                    C.ECONOMY.get("assist_share", 0.45)))
        now = self.time
        for hid, t in list(h.assist_credit.items()):
            if now - t > 18.0:
                continue
            a = self.heroes.get(hid)
            if a is None or a is killer or a.team == h.team:
                continue
            a.assists += 1
            self.grant_gold(a, bounty * share, "assist")
        h.assist_credit.clear()
        self._share_xp(h.x, h.y, enemy_of(h.team), xp_reward)

    def _tick_respawn(self, dt: float) -> None:
        for h in self.heroes.values():
            if h.alive or h.etype != E_HERO:
                continue
            h.respawn_timer -= dt
            if h.respawn_timer <= 0.0:
                self.respawn_hero(h)

    def respawn_hero(self, h: Hero) -> None:
        sx, sy = gm.SPAWN_POS[h.team]
        h.x, h.y = gm.nearest_walkable(sx + self.rng.uniform(-80, 80),
                                       sy + self.rng.uniform(-80, 80))
        h.alive = True
        h.respawn_timer = 0.0
        h._stats_dirty = True
        h.ensure_stats()
        h.hp, h.mana = h.max_hp, h.max_mana
        h.clear_order()
        self.emit("respawn", id=h.id)

    def _tick_passive_gold(self, dt: float) -> None:
        rate = float(C.ECONOMY.get("passive_gold_per_sec", 2.5))
        if rate <= 0:
            return
        for h in self.heroes.values():
            if h.etype == E_HERO:
                h.gold += rate * dt
                h.total_gold_earned += rate * dt

    def _check_victory(self) -> None:
        if self.phase == PHASE_FINISHED:
            return
        for team in (TEAM_DEV, TEAM_MGMT):
            anc = self.units.get(self.teams[team].ancient_id)
            if anc is None or not anc.alive:
                self.phase = PHASE_FINISHED
                self.winner = enemy_of(team)
                return

    # --- магазин -----------------------------------------------------------
    def buy_item(self, h: Hero, key: str) -> tuple[bool, str]:
        from .items import Item, missing_components, try_assemble
        d = C.item_def(key)
        if d is None:
            return False, "нет такого предмета"

        missing = missing_components(h, key)
        if missing is not None:
            price = sum(int(C.item_def(m).get("cost", 0)) for m in missing
                        if C.item_def(m)) + int(d.get("recipe_cost", 0))
        else:
            price = int(d.get("cost", 0))

        if h.gold < price:
            return False, "не хватает бюджета"
        if h.free_item_slot() < 0 and h.free_backpack_slot() < 0 and missing is None:
            return False, "нет свободных слотов"

        h.gold -= price
        if missing is not None:
            for m in missing:
                self._give_item(h, m, instant=True)
            if not try_assemble(h, key):
                self._give_item(h, key)
        else:
            self._give_item(h, key)
        self.emit("buy", id=h.id, k=key, cost=price)
        return True, ""

    def _in_base(self, h: Hero) -> bool:
        x0, y0, x1, y1 = gm.BASE_RECT[h.team]
        return x0 <= h.x <= x1 and y0 <= h.y <= y1

    def _give_item(self, h: Hero, key: str, instant: bool = False) -> None:
        if instant or self._in_base(h):
            self.deliver_item(h, key)
        else:
            h.deliveries.append({"key": key, "t": DELIVERY_TIME})
            self.emit("delivery", id=h.id, k=key, sec=DELIVERY_TIME)

    def deliver_item(self, h: Hero, key: str) -> None:
        from .items import Item, try_assemble
        slot = h.free_item_slot()
        if slot >= 0:
            h.items[slot] = Item(key)
        else:
            bslot = h.free_backpack_slot()
            if bslot >= 0:
                h.backpack[bslot] = Item(key)
            else:
                h.stash.append(key)
                return
        h._stats_dirty = True
        # Попробовать собрать всё, во что входит этот предмет
        from .items import UPGRADES_INTO
        for up in UPGRADES_INTO.get(key, []):
            ud = C.item_def(up) or {}
            if int(ud.get("recipe_cost", 0)) == 0 and try_assemble(h, up):
                self.emit("assemble", id=h.id, k=up)
                break

    def sell_item(self, h: Hero, slot: int) -> bool:
        if not (0 <= slot < len(h.items)) or h.items[slot] is None:
            return False
        it = h.items[slot]
        h.gold += it.cost * 0.5
        h.items[slot] = None
        h._stats_dirty = True
        return True

    # ======================================================================
    #  Применение способностей и предметов
    # ======================================================================
    def cast_ability(self, h: Hero, idx: int, target_id: int = 0,
                     px: float = 0.0, py: float = 0.0) -> tuple[bool, str]:
        if not (0 <= idx < len(h.abilities)):
            return False, "нет такой способности"
        a = h.abilities[idx]
        ok, why = a.ready(h)
        if not ok and not (a.targeting == "toggle" and why == "мало маны"):
            return False, why

        target = self.get_unit(target_id) if target_id else None
        tgt = a.targeting
        if tgt in ("unit_enemy", "unit_ally", "unit_any"):
            if target is None:
                return False, "нужна цель"
            allowed = a.defn.get("target_types")
            if allowed and target.etype not in allowed:
                return False, "неподходящая цель"
            if tgt == "unit_enemy" and target.team == h.team:
                return False, "цель должна быть вражеской"
            if tgt == "unit_ally" and target.team != h.team:
                return False, "цель должна быть союзной"
            px, py = target.x, target.y

        rng_limit = a.cast_range
        if rng_limit > 0:
            d = vmath.dist(h.x, h.y, px, py)
            if d > rng_limit + h.radius:
                # Подходим ближе и кастуем по прибытии
                h.pending_cast = {"idx": idx, "target": target_id, "x": px, "y": py}
                h.path = gm.find_path(h.x, h.y, px, py)
                h.path_idx = 0
                h.order = ORDER_MOVE
                h.order_x, h.order_y = px, py
                return True, ""

        if tgt == "toggle":
            a.toggled = not a.toggled
            self._toggle_acc[(h.id, idx)] = 0.0
            self.emit("toggle", id=h.id, k=a.key, on=1 if a.toggled else 0)
            return True, ""

        h.pending_cast = None
        h.mana -= a.mana_cost()
        a.start_cooldown(h)
        h.clear_order()
        h.face_towards(px if not target else target.x, py if not target else target.y, 1.0)

        self._charge_nearby_wands(h)
        cp = a.cast_point
        fire = lambda: self._fire_ability(h, a, target_id, px, py)
        if cp > 0.0:
            self.emit("cast", id=h.id, k=a.key, x=round(px), y=round(py), cp=cp)
            self.schedule(cp, fire)
        else:
            self.emit("cast", id=h.id, k=a.key, x=round(px), y=round(py), cp=0)
            fire()
        return True, ""

    def _charge_nearby_wands(self, caster: Hero) -> None:
        """Предметы, копящие заряды от чужих применений."""
        for e in self.units_in_radius(caster.x, caster.y, 1200.0,
                                      team=enemy_of(caster.team)):
            if e.etype != E_HERO:
                continue
            for it in e.all_items():
                if not it.defn.get("gain_charge_on_enemy_cast"):
                    continue
                cap = int(it.defn.get("max_charges", 20))
                if it.charges < cap:
                    it.charges += 1

    def _fire_ability(self, h: Hero, a, target_id: int, px: float, py: float) -> None:
        from .consts import IS_DISABLED
        if not h.alive or (h.flags & IS_DISABLED):
            return
        target = self.get_unit(target_id) if target_id else None
        ctx = ab.EffectContext(
            h, target, px, py, a.level, a.key,
            pierces_mi=bool(a.defn.get("pierces_magic_immunity", False)))
        ab.execute(self, ctx, a.defn.get("effects", []))

    def use_item(self, h: Hero, slot: int, target_id: int = 0,
                 px: float = 0.0, py: float = 0.0) -> tuple[bool, str]:
        if not (0 <= slot < len(h.items)) or h.items[slot] is None:
            return False, "пустой слот"
        it = h.items[slot]
        ok, why = it.ready(h, self.time)
        if not ok:
            return False, why
        a = it.active
        target = self.get_unit(target_id) if target_id else None
        if a.get("targeting") in ("unit_enemy", "unit_ally", "unit_any"):
            if target is None:
                return False, "нужна цель"
            allowed = a.get("target_types") or it.defn.get("target_types")
            if allowed and target.etype not in allowed:
                return False, "неподходящая цель"
            px, py = target.x, target.y
        rng_limit = float(a.get("cast_range", 0))
        if rng_limit > 0 and vmath.dist(h.x, h.y, px, py) > rng_limit + h.radius:
            return False, "слишком далеко"

        h.mana -= float(a.get("mana_cost", 0))
        it.cooldown = float(a.get("cooldown", 0)) * (1.0 - h.cooldown_reduction)
        ctx = ab.EffectContext(h, target, px, py, 1, it.key, source="item")
        ab.execute(self, ctx, a.get("effects", []))
        self.emit("item_use", id=h.id, k=it.key)

        if it.is_consumable:
            it.charges -= 1
            if it.charges <= 0:
                h.items[slot] = None
                h._stats_dirty = True
        return True, ""

    def level_ability(self, h: Hero, idx: int) -> tuple[bool, str]:
        if h.ability_points <= 0:
            return False, "нет очков способностей"
        if not (0 <= idx < len(h.abilities)):
            return False, "нет такой способности"
        a = h.abilities[idx]
        if not a.can_level(h.level):
            return False, "пока нельзя повысить"
        a.level += 1
        h.ability_points -= 1
        h._stats_dirty = True
        self.emit("skill_up", id=h.id, k=a.key, lvl=a.level)
        return True, ""

    def issue_order(self, u: Unit, kind: str, x: float = 0.0, y: float = 0.0,
                    target_id: int = 0) -> None:
        if kind == "move":
            x, y = gm.nearest_walkable(x, y)
            u.order_move_to(x, y, gm.find_path(u.x, u.y, x, y) or [(x, y)])
        elif kind == "attack_unit":
            t = self.get_unit(target_id)
            if t is not None and t.team != u.team:
                u.order_attack(target_id)
        elif kind == "attack_move":
            x, y = gm.nearest_walkable(x, y)
            u.order_attack_move(x, y, gm.find_path(u.x, u.y, x, y) or [(x, y)])
        elif kind == "hold":
            u.order_hold()
        elif kind == "stop":
            u.order_stop()
