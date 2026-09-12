"""Прогон матча без клиента — для проверки темпа и баланса."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from office_dota.game import content as C
from office_dota.game.consts import E_CREEP, E_TOWER
from office_dota.game.world import World


def main(minutes: float = 12.0, per_team: int = 3) -> int:
    keys = list(C.HEROES)
    w = World(seed=2024)
    for i in range(per_team):
        w.spawn_hero(0, keys[i % len(keys)], name=f"Dev{i}", is_bot=True)
        w.spawn_hero(1, keys[(i + per_team) % len(keys)], name=f"Mgmt{i}", is_bot=True)

    steps = int(minutes * 60 * 20)
    t0 = time.perf_counter()
    for step in range(steps):
        w.tick()
        if step % (20 * 60) == 0 and step:
            towers = sum(1 for u in w.units.values() if u.etype == E_TOWER and u.alive)
            creeps = sum(1 for u in w.units.values() if u.etype == E_CREEP and u.alive)
            lv = sum(h.level for h in w.heroes.values()) / max(1, len(w.heroes))
            gold = sum(h.gold for h in w.heroes.values()) / max(1, len(w.heroes))
            print(f"  {w.time/60:5.1f} мин | башен {towers:2d}/22 | крипов {creeps:3d} "
                  f"| ср. уровень {lv:4.1f} | ср. бюджет {gold:6.0f}")
        if w.phase == "finished":
            print(f"  матч окончен на {w.time/60:.1f} мин, победа команды {w.winner}")
            break
    el = time.perf_counter() - t0
    print(f"\n{w.time/60:.1f} игровых минут за {el:.1f}с (ускорение x{w.time/el:.0f}), "
          f"{el/max(1,w.tick_count)*1000:.2f} мс/тик")
    return 0


if __name__ == "__main__":
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    sys.exit(main(mins))
