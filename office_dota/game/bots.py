"""Боты для героев.

Бот нужен не чтобы выигрывать, а чтобы линия не разваливалась, пока человека
нет за компом. Поэтому цель поведения — «играет как средний коллега, который
отвлёкся»: фармит свою линию, бьёт по возможности, отступает при низком
здоровье и не творит глупостей.

Сознательно просто: конечный автомат, а не дерево поведения. Чинить и
настраивать такую логику можно на ходу, между матчами.
"""
from __future__ import annotations

from . import content as C, gamemap as gm, vmath
from .consts import (
    E_CREEP, E_HERO, E_NEUTRAL, E_TOWER, ORDER_ATTACK_MOVE, TEAM_DEV, enemy_of,
)

THINK_INTERVAL = 0.35        # с, как часто бот принимает решения
RETREAT_HP = 0.32
RESUME_HP = 0.72
ENGAGE_RADIUS = 900.0
LASTHIT_RADIUS = 420.0
TOWER_FEAR_RADIUS = 780.0

# Порядок покупок: дёшево и универсально. Ключи сверяются с магазином,
# отсутствующие молча пропускаются — контент может меняться без правки ботов.
BUY_ORDER = [
    "coffee_mug", "boots", "magic_wand", "sticky_notes",
    "power_treads", "blink_dagger", "bkb", "heart",
]
BUY_FALLBACK_BY_TIER = [1, 2, 3]


class BotBrain:
    """Состояние одного бота. Живёт рядом с героем, а не внутри него."""

    __slots__ = ("hero_id", "lane", "next_think", "retreating", "buy_idx", "home_t")

    def __init__(self, hero_id: int, lane: str) -> None:
        self.hero_id = hero_id
        self.lane = lane
        self.next_think = 0.0
        self.retreating = False
        self.buy_idx = 0
        self.home_t = 0.0


class BotDirector:
    """Раздаёт линии и думает за всех ботов сразу."""

    def __init__(self, world) -> None:
        self.world = world
        self.brains: dict[int, BotBrain] = {}
        self._lane_cursor = {0: 0, 1: 0}
        self._shop_keys: list[str] = []

    def _pick_lane(self, team: int) -> str:
        lanes = [gm.LANE_MID, gm.LANE_BOT, gm.LANE_TOP]
        lane = lanes[self._lane_cursor[team] % len(lanes)]
        self._lane_cursor[team] += 1
        return lane

    def ensure(self, hero) -> BotBrain:
        b = self.brains.get(hero.id)
        if b is None:
            b = BotBrain(hero.id, self._pick_lane(hero.team))
            self.brains[hero.id] = b
        return b

    def tick(self, dt: float) -> None:
        w = self.world
        for h in list(w.heroes.values()):
            if h.etype != E_HERO or not h.is_bot:
                continue
            brain = self.ensure(h)
            if not h.alive:
                continue
            if w.time < brain.next_think:
                continue
            brain.next_think = w.time + THINK_INTERVAL
            try:
                self._think(h, brain)
            except Exception:
                # Бот не должен ронять матч. Молча пропускаем такт раздумий.
                brain.next_think = w.time + 2.0

    # ------------------------------------------------------------------
    def _think(self, h, brain: BotBrain) -> None:
        w = self.world
        self._spend_gold(h, brain)
        self._level_skills(h)

        hp = h.hp_pct
        if brain.retreating and hp >= RESUME_HP:
            brain.retreating = False
        elif not brain.retreating and hp <= RETREAT_HP:
            brain.retreating = True

        if brain.retreating:
            fx, fy = gm.FOUNTAIN_POS[h.team]
            w.issue_order(h, "move", fx, fy)
            return

        enemy_hero = self._nearest_enemy_hero(h)
        if enemy_hero is not None and not self._under_enemy_tower(h, enemy_hero):
            self._use_abilities(h, enemy_hero)
            w.issue_order(h, "attack_unit", enemy_hero.x, enemy_hero.y, enemy_hero.id)
            return

        victim = self._lasthit_target(h)
        if victim is not None:
            w.issue_order(h, "attack_unit", victim.x, victim.y, victim.id)
            return

        self._push_lane(h, brain)

    def _nearest_enemy_hero(self, h):
        w = self.world
        best, bd = None, ENGAGE_RADIUS ** 2
        for e in w.spatial.query(h.x, h.y, ENGAGE_RADIUS):
            if e.etype != E_HERO or e.team == h.team or not e.alive:
                continue
            if not e.is_visible_to(h.team):
                continue
            d = h.dist_sq_to(e)
            if d < bd:
                bd, best = d, e
        return best

    def _under_enemy_tower(self, h, target) -> bool:
        """Не лезть под вражескую башню — главная ошибка плохого бота."""
        w = self.world
        for u in w.spatial.query(target.x, target.y, TOWER_FEAR_RADIUS):
            if u.etype == E_TOWER and u.alive and u.team != h.team:
                if vmath.dist_sq(target.x, target.y, u.x, u.y) <= TOWER_FEAR_RADIUS ** 2:
                    return True
        return False

    def _lasthit_target(self, h):
        """Добить того, кто вот-вот умрёт, иначе просто бить ближайшего."""
        w = self.world
        best, best_hp = None, 1e18
        fallback = None
        for u in w.spatial.query(h.x, h.y, LASTHIT_RADIUS):
            if not u.alive or u.team == h.team:
                continue
            if u.etype not in (E_CREEP, E_NEUTRAL):
                continue
            if h.dist_sq_to(u) > LASTHIT_RADIUS ** 2:
                continue
            if fallback is None:
                fallback = u
            if u.hp <= h.damage_max * 1.1 and u.hp < best_hp:
                best_hp, best = u.hp, u
        return best or fallback

    def _push_lane(self, h, brain: BotBrain) -> None:
        w = self.world
        pts = gm.LANE_PATHS[brain.lane]
        # Идём к самой дальней своей башне по линии, а оттуда — вперёд
        t = 0.5 if h.team == TEAM_DEV else 0.5
        target = gm.point_at_t(pts, 0.62 if h.team == TEAM_DEV else 0.38)
        w.issue_order(h, "attack_move", target[0], target[1])

    def _use_abilities(self, h, target) -> None:
        w = self.world
        d = vmath.dist(h.x, h.y, target.x, target.y)
        for i, a in enumerate(h.abilities):
            if a.level <= 0 or a.cooldown > 0 or a.targeting == "passive":
                continue
            if h.mana < a.mana_cost():
                continue
            rng = a.cast_range
            if a.targeting in ("unit_enemy", "unit_any"):
                if rng and d > rng:
                    continue
                w.cast_ability(h, i, target.id, target.x, target.y)
                return
            if a.targeting == "point":
                if rng and d > rng:
                    continue
                w.cast_ability(h, i, 0, target.x, target.y)
                return
            if a.targeting == "none" and d < 450:
                w.cast_ability(h, i, 0, h.x, h.y)
                return

    def _level_skills(self, h) -> None:
        if h.ability_points <= 0:
            return
        w = self.world
        # Ульт при первой возможности, дальше — по кругу, ровно
        order = sorted(range(len(h.abilities)),
                       key=lambda i: (not h.abilities[i].is_ultimate,
                                      h.abilities[i].level))
        for i in order:
            a = h.abilities[i]
            if a.targeting == "passive" and a.level == 0 and h.level < 4:
                continue
            if a.can_level(h.level):
                w.level_ability(h, i)
                return
        for i in range(len(h.abilities)):
            if h.abilities[i].can_level(h.level):
                w.level_ability(h, i)
                return

    def _spend_gold(self, h, brain: BotBrain) -> None:
        w = self.world
        if h.free_item_slot() < 0:
            return
        if not self._shop_keys:
            self._shop_keys = [k for k, d in C.ITEMS.items()
                               if d.get("shop") != "consumable"]
        while brain.buy_idx < len(BUY_ORDER):
            key = BUY_ORDER[brain.buy_idx]
            if key not in C.ITEMS:
                brain.buy_idx += 1
                continue
            cost = int(C.ITEMS[key].get("cost", 0))
            if h.gold < cost:
                return
            ok, _ = w.buy_item(h, key)
            brain.buy_idx += 1
            if ok:
                return
            return
        # Список кончился — берём что-то по карману, чтобы золото не лежало
        if h.gold > 3000:
            affordable = [k for k in self._shop_keys
                          if int(C.ITEMS[k].get("cost", 0)) <= h.gold]
            if affordable:
                affordable.sort(key=lambda k: -int(C.ITEMS[k].get("cost", 0)))
                w.buy_item(h, affordable[0])
