// Точка входа клиента: связывает сеть, ввод, отрисовку и интерфейс.

import { G } from './net.js';
import { initRender, draw, drawMinimap, resize } from './render.js';
import { initInput, tickCamera, castPreview, ui } from './input.js';
import {
  showScreen, initMenu, initLobby, renderLobby, initHud, renderHud,
  renderTop, renderScore, renderPause, renderKillfeed, renderEnd, renderLateJoin,
  pushChat, toggleShop, toggleScore, toast, renderSaves,
} from './ui.js';

// Доступ к состоянию из консоли и автотестов
window.__G = G;

const cv = document.getElementById('cv');
const mm = document.getElementById('minimap');

initRender(cv);
initInput(cv, { toggleShop, toggleScore });
initMenu();
initLobby();
initHud();

let inGame = false;

G.onWelcome = () => {
  for (const m of G.chat) pushChat(m);
};

G.onState = (st) => {
  if (st.phase === 'lobby') {
    if (inGame) { inGame = false; showScreen('lobby'); }
    else if (document.getElementById('screen-menu').classList.contains('active')) {
      showScreen('lobby');
    }
    renderLobby();
  } else if (!inGame) {
    inGame = true;
    showScreen('game');
    // Холст был скрыт и не имел размеров — теперь он виден
    requestAnimationFrame(() => resize());
  }
  renderPause();
  renderEnd();
  renderLateJoin();
};

G.onChat = (m) => pushChat(m);
G.onSaves = (list) => renderSaves(list);
G.onScore = () => { if (ui.scoreboard) renderScore(); };
G.onError = (msg, quiet) => { if (!quiet || true) toast(msg); };

// --- цикл ------------------------------------------------------------------
let last = performance.now();
let mmAccum = 0, hudAccum = 0;

function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;

  if (inGame) {
    tickCamera(dt);
    draw(castPreview());

    hudAccum += dt;
    if (hudAccum > 0.08) {
      hudAccum = 0;
      renderHud();
      renderTop();
      renderKillfeed();
      renderPause();
    }
    mmAccum += dt;
    if (mmAccum > 0.12) { mmAccum = 0; drawMinimap(mm); }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Сообщаем причину ухода: сервер поставит паузу, а не выкинет из матча
addEventListener('beforeunload', () => {
  if (G.ws) try { G.ws.close(); } catch (e) { /* всё равно уходим */ }
});
