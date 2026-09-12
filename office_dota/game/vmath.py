"""Векторная математика. Функции над парами float, без классов.

Сознательно без класса Vec2: в горячем цикле симуляции на 20 Гц аллокации
объектов на каждое сложение векторов обходятся дороже, чем читаемость,
которую они дают. Координаты лежат прямо на сущностях как .x / .y.
"""
from __future__ import annotations

import math

TAU = math.tau
EPS = 1e-9


def length(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)


def length_sq(x: float, y: float) -> float:
    return x * x + y * y


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    return math.sqrt(dx * dx + dy * dy)


def dist_sq(ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    return dx * dx + dy * dy


def normalize(x: float, y: float) -> tuple[float, float]:
    d = math.sqrt(x * x + y * y)
    if d < EPS:
        return 0.0, 0.0
    return x / d, y / d


def direction(ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    """Единичный вектор из A в B. Нулевой вектор, если точки совпадают."""
    return normalize(bx - ax, by - ay)


def move_towards(
    x: float, y: float, tx: float, ty: float, step: float
) -> tuple[float, float, bool]:
    """Сдвигает точку к цели не дальше чем на step.

    Возвращает (новый_x, новый_y, достигли_ли_цели).
    """
    dx = tx - x
    dy = ty - y
    d = math.sqrt(dx * dx + dy * dy)
    if d <= step or d < EPS:
        return tx, ty, True
    inv = step / d
    return x + dx * inv, y + dy * inv, False


def angle_of(x: float, y: float) -> float:
    return math.atan2(y, x)


def from_angle(a: float, radius: float = 1.0) -> tuple[float, float]:
    return math.cos(a) * radius, math.sin(a) * radius


def angle_diff(a: float, b: float) -> float:
    """Кратчайшая разница углов в диапазоне (-pi, pi]."""
    d = (b - a) % TAU
    if d > math.pi:
        d -= TAU
    return d


def rotate_towards(cur: float, target: float, max_step: float) -> float:
    d = angle_diff(cur, target)
    if abs(d) <= max_step:
        return target % TAU
    return (cur + math.copysign(max_step, d)) % TAU


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def in_radius(ax: float, ay: float, bx: float, by: float, r: float) -> bool:
    dx = bx - ax
    dy = by - ay
    return dx * dx + dy * dy <= r * r


def point_segment_dist_sq(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Квадрат расстояния от точки до отрезка AB. Нужен для линейных способностей."""
    abx = bx - ax
    aby = by - ay
    denom = abx * abx + aby * aby
    if denom < EPS:
        return dist_sq(px, py, ax, ay)
    t = ((px - ax) * abx + (py - ay) * aby) / denom
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    cx = ax + abx * t
    cy = ay + aby * t
    dx = px - cx
    dy = py - cy
    return dx * dx + dy * dy


def clamp_to_circle(
    x: float, y: float, cx: float, cy: float, radius: float
) -> tuple[float, float]:
    """Зажимает точку внутрь круга. Используется для ограничения дальности каста."""
    dx = x - cx
    dy = y - cy
    d = math.sqrt(dx * dx + dy * dy)
    if d <= radius or d < EPS:
        return x, y
    inv = radius / d
    return cx + dx * inv, cy + dy * inv
