// Управление. Раскладка дотовская: правый клик — идти/атаковать,
// QWER — способности, ZXCVBN — предметы, A — атака по земле, S — стоп.

import { G, send, myHero } from './net.js';
import { cam, s2w, w2s, pickUnitAt, markOrder, zoomBy, centerOnHero, panBy, drawMinimap } from './render.js';

const ITEM_KEYS = ['KeyZ', 'KeyX', 'KeyC', 'KeyV', 'KeyB', 'KeyN'];
const ABIL_KEYS = ['KeyQ', 'KeyW', 'KeyE', 'KeyR'];
// Раскладка может быть русской — код клавиши от языка не зависит,
// поэтому везде используем event.code, а не event.key.

export const targeting = { active: false, kind: '', idx: 0, range: 0, aoe: 0, mx: null, my: null };
export const ui = { scoreboard: false, shop: false, chatFocus: false };

let cv, onToggleShop, onToggleScore, edgePan = { x: 0, y: 0 };

export function initInput(canvas, hooks) {
  cv = canvas;
  onToggleShop = hooks.toggleShop;
  onToggleScore = hooks.toggleScore;

  cv.addEventListener('contextmenu', e => e.preventDefault());
  cv.addEventListener('mousedown', onMouseDown);
  cv.addEventListener('mousemove', onMouseMove);
  cv.addEventListener('wheel', onWheel, { passive: false });
  addEventListener('keydown', onKeyDown);
  addEventListener('keyup', onKeyUp);
  addEventListener('blur', () => { edgePan.x = edgePan.y = 0; });

  const mm = document.getElementById('minimap');
  mm.addEventListener('mousedown', e => {
    const r = mm.getBoundingClientRect();
    const k = (G.map ? G.map.size : 7200) / mm.width;
    const wx = (e.clientX - r.left) * (mm.width / r.width) * k;
    const wy = (e.clientY - r.top) * (mm.height / r.height) * k;
    if (e.button === 2) issueOrder('move', wx, wy, 0);
    else { cam.x = wx; cam.y = wy; cam.follow = false; }
    e.preventDefault();
  });
  mm.addEventListener('contextmenu', e => e.preventDefault());
}

function localXY(e) {
  const r = cv.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}

function onMouseMove(e) {
  const [mx, my] = localXY(e);
  targeting.mx = mx; targeting.my = my;
  // Прокрутка камеры краем экрана, как в доте
  const edge = 16;
  edgePan.x = mx < edge ? -1 : mx > cv.clientWidth - edge ? 1 : 0;
  edgePan.y = my < edge ? -1 : my > cv.clientHeight - edge ? 1 : 0;
}

function onMouseDown(e) {
  const [mx, my] = localXY(e);
  const [wx, wy] = s2w(mx, my);
  const unit = pickUnitAt(mx, my);

  if (targeting.active) {
    // В режиме прицеливания оба клика подтверждают, Escape отменяет
    if (e.button === 2) { cancelTargeting(); return; }
    confirmCast(wx, wy, unit);
    return;
  }

  if (e.button === 2) {
    if (unit && unit.team !== myTeamId() && unit.alive !== false) {
      issueOrder('attack_unit', unit.x, unit.y, unit.id);
      markOrder(unit.x, unit.y, true);
    } else {
      issueOrder('move', wx, wy, 0);
      markOrder(wx, wy, false);
    }
  }
}

function onWheel(e) {
  e.preventDefault();
  zoomBy(e.deltaY > 0 ? 0.9 : 1.1);
}

function myTeamId() { return G.you ? G.you.team : 0; }

function onKeyDown(e) {
  const chat = document.getElementById('chat-input');
  if (document.activeElement === chat) {
    if (e.code === 'Enter') {
      const v = chat.value.trim();
      if (v) send({ t: 'chat', text: v });
      chat.value = ''; chat.blur();
    } else if (e.code === 'Escape') { chat.value = ''; chat.blur(); }
    return;
  }
  const search = document.getElementById('shop-search');
  if (document.activeElement === search && e.code !== 'Escape') return;

  switch (e.code) {
    case 'Enter': chat.focus(); e.preventDefault(); return;
    case 'Escape':
      if (targeting.active) cancelTargeting();
      else if (ui.shop) onToggleShop(false);
      if (document.activeElement === search) search.blur();
      return;
    case 'Space': centerOnHero(); cam.follow = true; e.preventDefault(); return;
    case 'Tab': ui.scoreboard = true; onToggleScore(true); e.preventDefault(); return;
    case 'F9': send({ t: G.state.paused ? 'unpause' : 'pause' }); e.preventDefault(); return;
    case 'KeyP': onToggleShop(!ui.shop); return;
    case 'KeyS': issueOrder('stop', 0, 0, 0); return;
    case 'KeyH': issueOrder('hold', 0, 0, 0); return;
    case 'KeyA': startGroundTarget('attack_move'); return;
    case 'KeyF': cam.follow = !cam.follow; return;
  }

  const ai = ABIL_KEYS.indexOf(e.code);
  if (ai >= 0) { pressAbility(ai, e.shiftKey); return; }

  const ii = ITEM_KEYS.indexOf(e.code);
  if (ii >= 0) { pressItem(ii); return; }

  if (e.code.startsWith('Digit')) {
    const n = +e.code.slice(5);
    if (n >= 1 && n <= 6) pressItem(n - 1);
  }
}

function onKeyUp(e) {
  if (e.code === 'Tab') { ui.scoreboard = false; onToggleScore(false); }
}

// --- способности -----------------------------------------------------------
export function pressAbility(idx, shift) {
  const me = G.me;
  if (!me || !me.abil[idx]) return;
  const a = me.abil[idx];

  if (shift || (me.ap > 0 && a.lvl === 0 && a.tgt === 'passive')) {
    send({ t: 'level_up', i: idx });
    return;
  }
  if (a.lvl === 0) {
    if (me.ap > 0) send({ t: 'level_up', i: idx });
    return;
  }
  if (a.tgt === 'passive') return;
  if (a.cd > 0) return;

  if (a.tgt === 'none' || a.tgt === 'toggle') {
    send({ t: 'cast', i: idx, target: 0, x: 0, y: 0 });
    return;
  }
  targeting.active = true;
  targeting.kind = 'ability';
  targeting.idx = idx;
  targeting.range = a.range || 0;
  targeting.aoe = a.aoe || 60;
  targeting.need = a.tgt;
}

export function pressItem(slot) {
  const me = G.me;
  if (!me) return;
  const it = me.items[slot];
  if (!it || !it.tgt) return;
  if (it.cd > 0) return;
  if (it.tgt === 'none' || it.tgt === 'toggle') {
    send({ t: 'item', slot, target: 0, x: 0, y: 0 });
    return;
  }
  targeting.active = true;
  targeting.kind = 'item';
  targeting.idx = slot;
  targeting.range = it.range || 0;
  targeting.aoe = 60;
  targeting.need = it.tgt;
}

function startGroundTarget(kind) {
  targeting.active = true;
  targeting.kind = kind;
  targeting.range = 0;
  targeting.aoe = 40;
  targeting.need = 'point';
}

function confirmCast(wx, wy, unit) {
  const need = targeting.need;
  const wantsUnit = need && need.startsWith('unit_');
  const targetId = wantsUnit ? (unit ? unit.id : 0) : (unit ? unit.id : 0);
  if (wantsUnit && !targetId) return;      // цель обязательна — ждём клика по юниту

  if (targeting.kind === 'ability') {
    send({ t: 'cast', i: targeting.idx, target: targetId, x: wx, y: wy });
  } else if (targeting.kind === 'item') {
    send({ t: 'item', slot: targeting.idx, target: targetId, x: wx, y: wy });
  } else if (targeting.kind === 'attack_move') {
    issueOrder('attack_move', wx, wy, 0);
    markOrder(wx, wy, true);
  }
  cancelTargeting();
}

export function cancelTargeting() {
  targeting.active = false;
  targeting.kind = '';
  targeting.need = '';
}

function issueOrder(kind, x, y, target) {
  send({ t: 'order', kind, x, y, target });
}

export function tickCamera(dt) {
  if (edgePan.x || edgePan.y) {
    panBy(edgePan.x * 900 * dt, edgePan.y * 900 * dt);
  }
}

export function castPreview() {
  if (!targeting.active) return null;
  return { range: targeting.range, aoe: targeting.aoe, mx: targeting.mx, my: targeting.my };
}
