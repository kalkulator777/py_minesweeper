"""Геометрия карты: линии, башни, стены, лес, поиск пути.

Принцип: описывается только половина Разработки. Половина Менеджмента
получается зеркалом через центр карты (x, y) -> (SIZE-x, SIZE-y).
Симметрия гарантирована построением, а не аккуратностью при наборе координат.

Стены — сетка «офисных комнат» на решётке. Комнаты, попавшие на линию,
на реку, в базу или в лагерь нейтралов, удаляются. Получается план этажа,
через который проходят три линии и лес между ними.
"""
from __future__ import annotations

import heapq
import math
import random

from .consts import TEAM_DEV, TEAM_MGMT
from .vmath import dist, point_segment_dist_sq

SIZE = 7200.0
CENTER = SIZE / 2.0

CELL = 60.0                      # сторона клетки сетки проходимости
GRID_N = int(SIZE / CELL)        # 120x120

LANE_TOP = "top"
LANE_MID = "mid"
LANE_BOT = "bot"
LANES = (LANE_TOP, LANE_MID, LANE_BOT)

LANE_NAMES = {LANE_TOP: "Коридор", LANE_MID: "Опенспейс", LANE_BOT: "Подвал"}

LANE_WIDTH = 460.0               # полная ширина проходимого коридора линии
RIVER_WIDTH = 520.0
CAMP_CLEARANCE = 420.0           # радиус, который вычищается вокруг лагеря нейтралов


def mirror(p: tuple[float, float]) -> tuple[float, float]:
    """Точка на половине Менеджмента, соответствующая точке Разработки."""
    return (SIZE - p[0], SIZE - p[1])


def mirror_path(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Зеркалит полилинию И разворачивает её, чтобы она снова шла Dev -> Mgmt."""
    return [mirror(p) for p in reversed(pts)]


# --- Линии ----------------------------------------------------------------
# Задаётся только «Коридор». «Подвал» — его зеркало, «Опенспейс» самосимметричен.
_TOP_PATH: list[tuple[float, float]] = [
    (980, 6060), (620, 5200), (620, 2400), (700, 1250),
    (1250, 700), (2400, 620), (5200, 620), (6060, 980),
]
_MID_PATH: list[tuple[float, float]] = [
    (1320, 5880), (2400, 4800), (3600, 3600), (4800, 2400), (5880, 1320),
]

LANE_PATHS: dict[str, list[tuple[float, float]]] = {
    LANE_TOP: _TOP_PATH,
    LANE_MID: _MID_PATH,
    LANE_BOT: mirror_path(_TOP_PATH),
}

# Река — коридор по диагонали y = x, разделяющий половины команд.
RIVER_PATH: list[tuple[float, float]] = [(520, 520), (3600, 3600), (6680, 6680)]

# --- База -----------------------------------------------------------------
DEV_ANCIENT = (780.0, 6420.0)
DEV_FOUNTAIN = (430.0, 6770.0)
MGMT_ANCIENT = mirror(DEV_ANCIENT)
MGMT_FOUNTAIN = mirror(DEV_FOUNTAIN)

ANCIENT_POS = {TEAM_DEV: DEV_ANCIENT, TEAM_MGMT: MGMT_ANCIENT}
FOUNTAIN_POS = {TEAM_DEV: DEV_FOUNTAIN, TEAM_MGMT: MGMT_FOUNTAIN}

# Прямоугольник базы: внутри работает мгновенная покупка и реген фонтана.
BASE_RECT = {
    TEAM_DEV: (150.0, 5750.0, 1550.0, 7050.0),
    TEAM_MGMT: (SIZE - 1550.0, SIZE - 7050.0, SIZE - 150.0, SIZE - 5750.0),
}

# Точка спавна героя у фонтана
SPAWN_POS = {
    TEAM_DEV: (640.0, 6560.0),
    TEAM_MGMT: mirror((640.0, 6560.0)),
}

# --- Позиции башен вдоль линий -------------------------------------------
# t — доля пути от базы Разработки (0.0) до базы Менеджмента (1.0).
TOWER_T = {1: 0.325, 2: 0.195, 3: 0.095}


def _path_length(pts: list[tuple[float, float]]) -> float:
    return sum(dist(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def point_at_t(pts: list[tuple[float, float]], t: float) -> tuple[float, float]:
    """Точка на полилинии по нормированному параметру t в [0, 1]."""
    total = _path_length(pts)
    want = max(0.0, min(1.0, t)) * total
    acc = 0.0
    for i in range(len(pts) - 1):
        seg = dist(*pts[i], *pts[i + 1])
        if acc + seg >= want or i == len(pts) - 2:
            f = 0.0 if seg < 1e-9 else (want - acc) / seg
            f = max(0.0, min(1.0, f))
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            return (ax + (bx - ax) * f, ay + (by - ay) * f)
        acc += seg
    return pts[-1]


def tower_positions() -> dict[tuple[int, str, int], tuple[float, float]]:
    """(команда, линия, тир) -> позиция. Тиры 1..3, строго симметрично."""
    out: dict[tuple[int, str, int], tuple[float, float]] = {}
    for lane, pts in LANE_PATHS.items():
        for tier, t in TOWER_T.items():
            out[(TEAM_DEV, lane, tier)] = point_at_t(pts, t)
            out[(TEAM_MGMT, lane, tier)] = point_at_t(pts, 1.0 - t)
    return out


# Бараки — сразу за башней третьего тира, смещены к базе.
BARRACKS_T = 0.062
# Два турникета (T4) по бокам от трона.
_DEV_T4 = [(1090.0, 6280.0), (900.0, 6810.0)]
T4_POS = {TEAM_DEV: _DEV_T4, TEAM_MGMT: [mirror(p) for p in _DEV_T4]}


def barracks_positions() -> dict[tuple[int, str, str], tuple[float, float]]:
    """(команда, линия, вид) -> позиция. Вид: 'melee' | 'ranged'."""
    out: dict[tuple[int, str, str], tuple[float, float]] = {}
    for lane, pts in LANE_PATHS.items():
        for team, t in ((TEAM_DEV, BARRACKS_T), (TEAM_MGMT, 1.0 - BARRACKS_T)):
            bx, by = point_at_t(pts, t)
            # Ближние и дальние бараки стоят рядом, поперёк линии.
            nx, ny = _lane_normal(pts, t)
            out[(team, lane, "melee")] = (bx + nx * 95, by + ny * 95)
            out[(team, lane, "ranged")] = (bx - nx * 95, by - ny * 95)
    return out


def _lane_normal(pts: list[tuple[float, float]], t: float) -> tuple[float, float]:
    """Единичная нормаль к линии в точке t — чтобы расставлять объекты поперёк."""
    a = point_at_t(pts, max(0.0, t - 0.01))
    b = point_at_t(pts, min(1.0, t + 0.01))
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 1.0)
    return (-dy / d, dx / d)


# --- Лагеря нейтралов -----------------------------------------------------
# Задаётся только сторона Разработки, Менеджмент получает зеркало.
# size: small | medium | large | ancient
_DEV_CAMPS: list[tuple[str, tuple[float, float]]] = [
    ("small",   (1750.0, 5150.0)),   # лёгкий лагерь у безопасной линии
    ("medium",  (2650.0, 5450.0)),
    ("large",   (3250.0, 4750.0)),
    ("small",   (1500.0, 3950.0)),   # лес на сложной линии
    ("medium",  (1900.0, 2950.0)),
    ("ancient", (2850.0, 3900.0)),   # древние — ближе к реке
]
CAMPS: list[tuple[int, str, tuple[float, float]]] = (
    [(TEAM_DEV, s, p) for s, p in _DEV_CAMPS]
    + [(TEAM_MGMT, s, mirror(p)) for s, p in _DEV_CAMPS]
)

ROSHAN_POS = (2700.0, 3150.0)        # «Легаси» — в овраге у реки

# --- Руны -----------------------------------------------------------------
POWER_RUNE_POS = [(2450.0, 2900.0), mirror((2450.0, 2900.0))]
BOUNTY_RUNE_POS = [
    (1620.0, 4450.0), mirror((1620.0, 4450.0)),
    (1250.0, 2050.0), mirror((1250.0, 2050.0)),
]

# --- Магазины -------------------------------------------------------------
SECRET_SHOP_POS = [(2150.0, 4200.0), mirror((2150.0, 4200.0))]
SHOP_RADIUS = 420.0


# ==========================================================================
#  Стены: сетка офисных комнат
# ==========================================================================

_LATTICE_STEP = 720.0
_LATTICE_K = 4                   # k in [-4..4] -> 9 узлов на ось, 81 комната
_ROOM_MIN, _ROOM_MAX = 220.0, 470.0
_SHRINK_STEPS = 9                # сколько раз пробуем ужать комнату, прежде чем выбросить


def _near_any_corridor(px: float, py: float) -> bool:
    """True, если точка лежит в коридоре, на базе, в лагере или у руны."""
    half_lane = LANE_WIDTH / 2 + 30.0
    for pts in LANE_PATHS.values():
        if _dist_to_polyline_sq(px, py, pts) <= half_lane * half_lane:
            return True
    half_river = RIVER_WIDTH / 2 + 30.0
    if _dist_to_polyline_sq(px, py, RIVER_PATH) <= half_river * half_river:
        return True
    for team in (TEAM_DEV, TEAM_MGMT):
        bx0, by0, bx1, by1 = BASE_RECT[team]
        if bx0 - 120 <= px <= bx1 + 120 and by0 - 120 <= py <= by1 + 120:
            return True
    for _team, _size, (cx, cy) in CAMPS:
        if (px - cx) ** 2 + (py - cy) ** 2 <= CAMP_CLEARANCE ** 2:
            return True
    for cx, cy in (ROSHAN_POS, *POWER_RUNE_POS, *BOUNTY_RUNE_POS, *SECRET_SHOP_POS):
        if (px - cx) ** 2 + (py - cy) ** 2 <= 300.0 ** 2:
            return True
    return False


def _dist_to_polyline_sq(px: float, py: float, pts: list[tuple[float, float]]) -> float:
    best = float("inf")
    for i in range(len(pts) - 1):
        d = point_segment_dist_sq(px, py, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        if d < best:
            best = d
    return best


def _room_fits(cx: float, cy: float, w: float, h: float) -> bool:
    hw, hh = w / 2, h / 2
    probes = (
        (cx, cy),
        (cx - hw, cy - hh), (cx + hw, cy - hh),
        (cx - hw, cy + hh), (cx + hw, cy + hh),
        (cx, cy - hh), (cx, cy + hh), (cx - hw, cy), (cx + hw, cy),
    )
    return not any(_near_any_corridor(px, py) for px, py in probes)


def _fit_room(cx: float, cy: float, w: float, h: float):
    """Ужимает комнату, пока она не перестанет задевать коридор. None — выбросить.

    Детерминировано: при симметричных входных данных даёт симметричный результат.
    """
    for step in range(_SHRINK_STEPS + 1):
        f = 1.0 - 0.13 * step
        ww, hh = w * f, h * f
        if ww < 105.0 or hh < 105.0:
            return None
        if _room_fits(cx, cy, ww, hh):
            return (cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2)
    return None


def _sym_sizes(nodes, anti, rng) -> dict:
    """Размеры комнат, одинаковые у каждой пары узлов, переходящих друг в друга
    при отражении через центр. Без этого карта получается несимметричной."""
    out: dict = {}
    for n in nodes:
        a = anti(n)
        if a in out:
            out[n] = out[a]
        else:
            out[n] = (rng.uniform(_ROOM_MIN, _ROOM_MAX), rng.uniform(_ROOM_MIN, _ROOM_MAX))
    return out


def _room_rects() -> list[tuple[float, float, float, float]]:
    """Комнаты-препятствия. Симметричны относительно центра по построению.

    Две решётки: основная с целыми индексами и сдвинутая с полуцелыми.
    Обе симметричны относительно нуля, поэтому итог тоже симметричен.
    """
    rng = random.Random(0xC0FFEE)
    rects: list[tuple[float, float, float, float]] = []
    K = _LATTICE_K

    # Основная решётка: k = -K..K, отражение (kx,ky) -> (-kx,-ky)
    main_nodes = [(kx, ky) for kx in range(-K, K + 1) for ky in range(-K, K + 1)]
    for (kx, ky), (w, h) in _sym_sizes(main_nodes, lambda n: (-n[0], -n[1]), rng).items():
        r = _fit_room(CENTER + kx * _LATTICE_STEP, CENTER + ky * _LATTICE_STEP, w, h)
        if r is not None:
            rects.append(r)

    # Сдвинутая решётка: центры в (k + 0.5) * шаг, k = -K..K-1.
    # Множество {k + 0.5} симметрично относительно нуля, отражение (kx,ky) -> (-kx-1,-ky-1).
    off_nodes = [(kx, ky) for kx in range(-K, K) for ky in range(-K, K)]
    for (kx, ky), (w, h) in _sym_sizes(off_nodes, lambda n: (-n[0] - 1, -n[1] - 1), rng).items():
        r = _fit_room(CENTER + (kx + 0.5) * _LATTICE_STEP,
                      CENTER + (ky + 0.5) * _LATTICE_STEP,
                      w * 0.85, h * 0.85)
        if r is not None:
            rects.append(r)

    return rects


WALL_RECTS: list[tuple[float, float, float, float]] = _room_rects()


# ==========================================================================
#  Сетка проходимости и поиск пути
# ==========================================================================

UNIT_CLEARANCE = 48.0            # на столько «раздуваем» стены под радиус юнита

_DIAG = math.sqrt(2.0)
_NEIGHBORS = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, _DIAG), (1, -1, _DIAG), (-1, 1, _DIAG), (-1, -1, _DIAG),
)


def _build_grid() -> bytearray:
    """1 = непроходимо. Стены раздуты на UNIT_CLEARANCE, чтобы юниты не липли к углам."""
    g = bytearray(GRID_N * GRID_N)
    pad = UNIT_CLEARANCE
    for x0, y0, x1, y1 in WALL_RECTS:
        cx0 = max(0, int((x0 - pad) / CELL))
        cy0 = max(0, int((y0 - pad) / CELL))
        cx1 = min(GRID_N - 1, int((x1 + pad) / CELL))
        cy1 = min(GRID_N - 1, int((y1 + pad) / CELL))
        for cy in range(cy0, cy1 + 1):
            row = cy * GRID_N
            for cx in range(cx0, cx1 + 1):
                g[row + cx] = 1
    # Внешняя рамка карты
    for i in range(GRID_N):
        g[i] = 1
        g[(GRID_N - 1) * GRID_N + i] = 1
        g[i * GRID_N] = 1
        g[i * GRID_N + GRID_N - 1] = 1
    return g


GRID: bytearray = _build_grid()


def cell_of(x: float, y: float) -> tuple[int, int]:
    cx = int(x / CELL)
    cy = int(y / CELL)
    if cx < 0:
        cx = 0
    elif cx >= GRID_N:
        cx = GRID_N - 1
    if cy < 0:
        cy = 0
    elif cy >= GRID_N:
        cy = GRID_N - 1
    return cx, cy


def is_walkable(x: float, y: float) -> bool:
    cx, cy = cell_of(x, y)
    return GRID[cy * GRID_N + cx] == 0


def nearest_walkable(x: float, y: float, max_rings: int = 12) -> tuple[float, float]:
    """Ближайшая проходимая точка. Нужна, когда юнита вытолкнуло в стену."""
    if is_walkable(x, y):
        return x, y
    cx, cy = cell_of(x, y)
    for r in range(1, max_rings + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < GRID_N and 0 <= ny < GRID_N and GRID[ny * GRID_N + nx] == 0:
                    return (nx + 0.5) * CELL, (ny + 0.5) * CELL
    return CENTER, CENTER


def has_line_of_sight(ax: float, ay: float, bx: float, by: float) -> bool:
    """Проверка прямой видимости по сетке. Используется и для сглаживания пути."""
    d = math.hypot(bx - ax, by - ay)
    steps = int(d / (CELL * 0.5)) + 1
    for i in range(steps + 1):
        t = i / steps
        if not is_walkable(ax + (bx - ax) * t, ay + (by - ay) * t):
            return False
    return True


def find_path(sx: float, sy: float, tx: float, ty: float,
              max_nodes: int = 9000) -> list[tuple[float, float]]:
    """A* по сетке. Возвращает сглаженную полилинию без стартовой точки.

    Пустой список — путь не найден. Если цель видна напрямую, сразу [цель].
    """
    if has_line_of_sight(sx, sy, tx, ty):
        return [(tx, ty)]

    sx_, sy_ = nearest_walkable(sx, sy)
    tx_, ty_ = nearest_walkable(tx, ty)
    start = cell_of(sx_, sy_)
    goal = cell_of(tx_, ty_)
    if start == goal:
        return [(tx, ty)]

    gx, gy = goal
    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, 0, start))
    came: dict[tuple[int, int], tuple[int, int]] = {}
    gscore: dict[tuple[int, int], float] = {start: 0.0}
    counter = 0
    expanded = 0
    found = False

    while open_heap:
        _, _, cur = heapq.heappop(open_heap)
        if cur == goal:
            found = True
            break
        expanded += 1
        if expanded > max_nodes:
            break
        cx, cy = cur
        base = gscore[cur]
        for dx, dy, cost in _NEIGHBORS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < GRID_N and 0 <= ny < GRID_N):
                continue
            if GRID[ny * GRID_N + nx]:
                continue
            if dx and dy:  # диагональ запрещена, если оба ортогональных соседа заняты
                if GRID[cy * GRID_N + nx] and GRID[ny * GRID_N + cx]:
                    continue
            ng = base + cost
            nxt = (nx, ny)
            if ng < gscore.get(nxt, 1e18):
                gscore[nxt] = ng
                came[nxt] = cur
                h = math.hypot(gx - nx, gy - ny)
                counter += 1
                heapq.heappush(open_heap, (ng + h, counter, nxt))

    if not found:
        return []

    cells: list[tuple[int, int]] = [goal]
    cur = goal
    while cur != start:
        cur = came[cur]
        cells.append(cur)
    cells.reverse()

    pts = [((cx + 0.5) * CELL, (cy + 0.5) * CELL) for cx, cy in cells]
    pts[-1] = (tx, ty)
    return _smooth(sx, sy, pts)


def _smooth(sx: float, sy: float, pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Выбрасывает промежуточные точки, если между соседями есть прямая видимость."""
    out: list[tuple[float, float]] = []
    cx, cy = sx, sy
    i = 0
    n = len(pts)
    while i < n:
        j = n - 1
        while j > i and not has_line_of_sight(cx, cy, pts[j][0], pts[j][1]):
            j -= 1
        out.append(pts[j])
        cx, cy = pts[j]
        i = j + 1
    return out


# ==========================================================================
#  Самопроверка карты
# ==========================================================================

def validate_map() -> list[str]:
    """Возвращает список проблем. Пустой список — карта корректна."""
    problems: list[str] = []

    # 1. Симметрия стен
    have = {(round(a), round(b), round(c), round(d)) for a, b, c, d in WALL_RECTS}
    mirrored = {(round(SIZE - c), round(SIZE - d), round(SIZE - a), round(SIZE - b))
                for a, b, c, d in WALL_RECTS}
    if have != mirrored:
        problems.append(f"стены несимметричны: расхождений {len(have ^ mirrored)}")

    # 2. Каждая линия проходима от базы до базы без обхода
    for lane, pts in LANE_PATHS.items():
        for i in range(len(pts) - 1):
            if not has_line_of_sight(*pts[i], *pts[i + 1]):
                problems.append(f"линия {lane}: сегмент {i} перекрыт стеной")

    # 3. Ключевые точки стоят на проходимой земле
    named: list[tuple[str, tuple[float, float]]] = [
        ("трон Разработки", DEV_ANCIENT), ("трон Менеджмента", MGMT_ANCIENT),
        ("фонтан Разработки", DEV_FOUNTAIN), ("фонтан Менеджмента", MGMT_FOUNTAIN),
        ("Легаси", ROSHAN_POS),
    ]
    named += [(f"спавн {t}", p) for t, p in SPAWN_POS.items()]
    named += [(f"лагерь {s}@{int(p[0])},{int(p[1])}", p) for _t, s, p in CAMPS]
    named += [(f"руна силы {i}", p) for i, p in enumerate(POWER_RUNE_POS)]
    named += [(f"башня {k}", v) for k, v in tower_positions().items()]
    named += [(f"бараки {k}", v) for k, v in barracks_positions().items()]
    for label, (px, py) in named:
        if not is_walkable(px, py):
            problems.append(f"{label} стоит в стене ({px:.0f},{py:.0f})")

    # 4. Связность: от фонтана Разработки достижимо всё важное
    for label, (px, py) in named:
        if not find_path(*DEV_FOUNTAIN, px, py):
            problems.append(f"{label} недостижим от фонтана Разработки")

    return problems
