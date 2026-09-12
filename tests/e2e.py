"""Сквозная проверка клиента в настоящем браузере.

Поднимает сервер, заходит двумя вкладками, выбирает героев, начинает матч,
играет, ставит паузу и проверяет реконнект. Любая ошибка в консоли браузера
роняет тест — молча сломанный клиент хуже, чем упавший.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8899
URL = f"http://127.0.0.1:{PORT}/"
SHOTS = os.path.join(ROOT, "tests", "shots")


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    srv = subprocess.Popen(
        [sys.executable, "play.py", "--port", str(PORT), "--no-browser",
         "--no-announce", "--name", "E2E"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.5)
    errors: list[str] = []
    failures: list[str] = []

    def check(label: str, cond: bool, extra: str = "") -> None:
        print(f"  {'OK  ' if cond else 'СБОЙ'} {label}{(' — ' + extra) if extra else ''}")
        if not cond:
            failures.append(label)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                args=["--no-sandbox"])
            ctx = browser.new_context(viewport={"width": 1440, "height": 860})

            def wire(page, tag):
                page.on("console", lambda m: errors.append(f"[{tag}] {m.type}: {m.text}")
                        if m.type == "error" else None)
                page.on("pageerror", lambda e: errors.append(f"[{tag}] pageerror: {e}"))

            # --- игрок 1 ---
            p1 = ctx.new_page(); wire(p1, "Аня")
            p1.goto(URL, wait_until="networkidle")
            check("меню открылось", p1.is_visible("#screen-menu"))
            p1.fill("#inp-name", "Аня")
            p1.click("#btn-host")
            p1.wait_for_selector("#screen-lobby.active", timeout=5000)
            check("лобби открылось у первого игрока", True)
            p1.screenshot(path=f"{SHOTS}/01-lobby.png")

            # --- игрок 2 в отдельном контексте (свой localStorage) ---
            ctx2 = browser.new_context(viewport={"width": 1280, "height": 800})
            p2 = ctx2.new_page(); wire(p2, "Боря")
            p2.goto(URL, wait_until="networkidle")
            p2.fill("#inp-name", "Боря")
            p2.click("#btn-host")
            p2.wait_for_selector("#screen-lobby.active", timeout=5000)

            p1.wait_for_timeout(600)
            roster = p1.inner_text("#roster-0") + p1.inner_text("#roster-1")
            check("второй игрок виден в лобби первого", "Боря" in roster, roster.replace("\n", " | "))

            # --- выбор героев ---
            p2.click('[data-join-team="1"]')
            p2.wait_for_timeout(300)
            cards1 = p1.query_selector_all(".hero-card")
            check("сетка героев отрисована", len(cards1) == 8, f"{len(cards1)} карточек")
            cards1[0].click()
            p1.wait_for_timeout(300)
            check("детали героя раскрылись", p1.is_visible("#hero-detail.on"))
            p2.query_selector_all(".hero-card")[1].click()
            p1.wait_for_timeout(400)
            p1.screenshot(path=f"{SHOTS}/02-picked.png")

            # --- старт матча ---
            p1.click("#btn-start")
            p1.wait_for_selector("#screen-game.active", timeout=6000)
            p2.wait_for_selector("#screen-game.active", timeout=6000)
            check("матч начался у обоих", True)

            # Справка показывается новичку сама — закрываем её
            p1.wait_for_timeout(500)
            check("справка показана при первом входе", p1.is_visible("#help"))
            p1.screenshot(path=f"{SHOTS}/09-help.png")
            for pg in (p1, p2):
                if pg.is_visible("#help"):
                    pg.click("#help-close")
            p1.wait_for_timeout(300)
            check("справка закрылась", not p1.is_visible("#help"))
            p1.wait_for_timeout(3000)
            p1.screenshot(path=f"{SHOTS}/03-game.png")

            # --- HUD наполнен ---
            gold = p1.inner_text("#gold")
            abil = p1.query_selector_all("#abilities .ab")
            items = p1.query_selector_all("#items .it")
            check("золото показано", "₿" in gold, gold)
            check("4 способности в панели", len(abil) == 4, str(len(abil)))
            check("6 слотов предметов", len(items) == 6, str(len(items)))

            # --- приказ движения правым кликом ---
            before = p1.evaluate("() => { const m = window.__G?.me; return m ? m.id : 0 }")
            p1.mouse.click(720, 430, button="right")
            p1.wait_for_timeout(1800)

            # --- изучение способности и каст ---
            p1.keyboard.press("Q")           # первый Q поднимает уровень скилла
            p1.wait_for_timeout(400)
            lvl = p1.evaluate("() => window.__G?.me?.abil?.[0]?.lvl ?? -1")
            check("способность изучена по Q", lvl >= 1, f"уровень {lvl}")
            p1.keyboard.press("Q")           # второй Q входит в прицеливание
            p1.wait_for_timeout(200)
            p1.mouse.click(800, 400)
            p1.wait_for_timeout(600)

            # --- магазин ---
            p1.keyboard.press("P")
            p1.wait_for_timeout(500)
            check("магазин открылся", p1.is_visible("#shop"))
            cats = p1.query_selector_all(".shop-cat")
            check("категории магазина отрисованы", len(cats) >= 3, f"{len(cats)} категорий")
            p1.screenshot(path=f"{SHOTS}/04-shop.png")
            first_item = p1.query_selector(".si")
            if first_item:
                first_item.click()
                p1.wait_for_timeout(700)
            p1.keyboard.press("Escape")

            # --- таблица счёта ---
            p1.keyboard.down("Tab"); p1.wait_for_timeout(400)
            check("таблица счёта открылась", p1.is_visible("#scoreboard"))
            p1.screenshot(path=f"{SHOTS}/05-score.png")
            p1.keyboard.up("Tab")

            # --- пауза по F9 ---
            p1.keyboard.press("F9")
            p1.wait_for_timeout(800)
            check("пауза показана", p1.is_visible("#pause-overlay"))
            p1.screenshot(path=f"{SHOTS}/06-pause.png")
            p1.click("#btn-unpause")
            p1.wait_for_timeout(3600)
            check("пауза снята", not p1.is_visible("#pause-overlay"))

            # --- дисконнект второго -> авто-пауза у первого ---
            p2.close()
            p1.wait_for_timeout(7000)
            paused = p1.evaluate("() => window.__G?.state?.paused ?? 0")
            check("отключение коллеги дало авто-паузу", bool(paused))
            p1.screenshot(path=f"{SHOTS}/07-autopause.png")

            # --- он возвращается -> матч продолжается ---
            p2b = ctx2.new_page(); wire(p2b, "Боря-2")
            p2b.goto(URL, wait_until="networkidle")
            p2b.wait_for_timeout(500)
            if p2b.is_visible("#screen-menu"):
                p2b.click("#btn-host")
            p1.wait_for_timeout(5000)
            still = p1.evaluate("() => window.__G?.state?.paused ?? 0")
            check("после возвращения пауза снята", not still)
            hero_back = p2b.evaluate("() => window.__G?.me?.id ?? 0")
            check("вернувшийся получил своего героя обратно", hero_back > 0, f"id={hero_back}")
            p2b.screenshot(path=f"{SHOTS}/08-reconnect.png")

            browser.close()
    finally:
        srv.terminate()
        try:
            out = srv.communicate(timeout=5)[0]
        except Exception:
            out = ""
        if "Traceback" in (out or ""):
            print("\n--- ОШИБКИ СЕРВЕРА ---")
            print(out[-2500:])
            failures.append("сервер упал с исключением")

    print("\n--- ОШИБКИ В КОНСОЛИ БРАУЗЕРА ---")
    real = [e for e in errors if "favicon" not in e.lower()]
    if real:
        for e in real[:25]:
            print("  " + e[:200])
        failures.append(f"{len(real)} ошибок JS")
    else:
        print("  нет")

    print()
    if failures:
        print(f"ИТОГ: провалено {len(failures)} — " + "; ".join(failures))
        return 1
    print("ИТОГ: все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
