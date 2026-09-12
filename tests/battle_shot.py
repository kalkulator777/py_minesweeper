"""Снимок настоящего боя: матч с ботами, крипами и дракой на линии.

Нужен, чтобы смотреть на игру в рабочем состоянии, а не на пустую карту
в фазе подготовки.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8901
URL = f"http://127.0.0.1:{PORT}/"
SHOTS = os.path.join(ROOT, "tests", "shots")


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    srv = subprocess.Popen(
        [sys.executable, "play.py", "--port", str(PORT), "--no-browser",
         "--no-announce", "--name", "Бой"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.5)
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(
                executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1600, "height": 900})
            p = ctx.new_page()
            p.on("pageerror", lambda e: errors.append(str(e)))
            p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            p.goto(URL, wait_until="networkidle")
            p.fill("#inp-name", "Наблюдатель")
            p.click("#btn-host")
            p.wait_for_selector("#screen-lobby.active")

            # Полный состав: человек плюс боты с обеих сторон
            p.query_selector_all(".hero-card")[0].click()
            p.wait_for_timeout(300)
            for team in (0, 0, 1, 1, 1):
                p.click(f'[data-add-bot="{team}"]')
                p.wait_for_timeout(200)
            p.click("#btn-start")
            p.wait_for_selector("#screen-game.active", timeout=6000)

            # Ждём, пока волны встретятся и начнётся драка
            print("  идёт матч, ждём боя на линии…")
            p.wait_for_timeout(115000)

            # Ставим камеру в центр карты, где идёт замес
            # Ищем плотный замес ТАМ, ГДЕ У НАС ЕСТЬ ОБЗОР: вокруг своего
            # героя или бота. Иначе камера уедет в туман и снимок будет пустой.
            p.evaluate("""() => {
                const G = window.__G;
                const myTeam = G.you ? G.you.team : 0;
                let best = null, bestN = 0;
                for (const u of G.units.values()) {
                    if (u.alive === false || u.e !== 'hero' || u.team !== myTeam) continue;
                    let n = 0;
                    for (const v of G.units.values()) {
                        if (v.alive === false) continue;
                        const dx = v.x - u.x, dy = v.y - u.y;
                        if (dx*dx + dy*dy < 1100*1100) n++;
                    }
                    if (n > bestN) { bestN = n; best = u; }
                }
                if (best) { window.__focus = [best.x, best.y, bestN]; }
            }""")
            focus = p.evaluate("() => window.__focus")
            if focus:
                print(f"  самая плотная точка: {int(focus[0])},{int(focus[1])} "
                      f"— {focus[2]} юнитов рядом")
                p.evaluate("""(f) => {
                    window.__cam.follow = false;
                    window.__cam.x = f[0];
                    window.__cam.y = f[1];
                    window.__cam.zoom = 0.75;
                }""", focus)
            p.wait_for_timeout(1500)
            p.screenshot(path=f"{SHOTS}/10-battle.png")

            # И миникарта с полной картиной
            state = p.evaluate("""() => {
                const G = window.__G;
                let creeps = 0, heroes = 0, towers = 0;
                for (const u of G.units.values()) {
                    if (u.alive === false) continue;
                    if (u.e === 'creep') creeps++;
                    else if (u.e === 'hero') heroes++;
                    else if (u.e === 'tower') towers++;
                }
                return {creeps, heroes, towers, time: G.serverTime,
                        me: G.me ? {lvl: G.me.lvl, gold: G.me.gold, hp: G.me.hp} : null};
            }""")
            print(f"  на {state['time']:.0f}-й секунде видно: крипов {state['creeps']}, "
                  f"героев {state['heroes']}, башен {state['towers']}")
            print(f"  мой герой: {state['me']}")
            b.close()
    finally:
        srv.terminate()
    real = [e for e in errors if "favicon" not in e.lower()]
    print("  ошибок JS:", real[:3] if real else "нет")
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
