"""Пространственный индекс для запросов «кто в радиусе».

Перестраивается целиком каждый тик. Для двух сотен юнитов это дешевле
и надёжнее, чем инкрементальное обновление с его классом ошибок
«юнит остался в старой клетке».
"""
from __future__ import annotations

from .vmath import dist_sq

CELL = 400.0


class SpatialHash:
    __slots__ = ("cells",)

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list] = {}

    def rebuild(self, units) -> None:
        cells: dict[tuple[int, int], list] = {}
        for u in units:
            key = (int(u.x / CELL), int(u.y / CELL))
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [u]
            else:
                bucket.append(u)
        self.cells = cells

    def query(self, x: float, y: float, radius: float) -> list:
        """Кандидаты в радиусе. Может вернуть лишних — вызывающий фильтрует точно."""
        if radius <= 0:
            return []
        r = int(radius / CELL) + 1
        cx, cy = int(x / CELL), int(y / CELL)
        out: list = []
        cells = self.cells
        for gy in range(cy - r, cy + r + 1):
            for gx in range(cx - r, cx + r + 1):
                bucket = cells.get((gx, gy))
                if bucket:
                    out.extend(bucket)
        return out

    def query_exact(self, x: float, y: float, radius: float) -> list:
        rr = radius * radius
        return [u for u in self.query(x, y, radius) if dist_sq(x, y, u.x, u.y) <= rr]
