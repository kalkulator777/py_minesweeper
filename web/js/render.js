// Отрисовка мира на Canvas2D.
//
// Рисуем в порядке: земля -> туман -> сущности -> эффекты -> полоски и цифры.
// Туман кладётся до сущностей: сервер и так не присылает невидимых юнитов,
// поэтому затемнять нужно только землю, а не то, что мы честно видим.

import { G, interpolated, myHero, myTeam } from './net.js';

export const cam = { x: 3600, y: 3600, zoom: 0.58, follow: true };

let cv, ctx, fog, fctx, W = 0, H = 0, dpr = 1;

const TEAM_COLOR = ['#3fbf6f', '#d94c4c', '#b0a080'];
const TEAM_DARK = ['#1d5a34', '#6b2323', '#4d4436'];

const HERO_GLYPH = {
  sysadmin: '🖥', senior: '👨‍💻', analyst: '📈', hr: '📋',
  scrum_master: '🔁', security: '🛡', accountant: '🧮', junior: '🐣',
};
const BUILDING_GLYPH = {
  tower_t1: '🥤', tower_t2: '🖨', tower_t3: '☕', tower_t4: '🚪',
  barracks_melee: '🏢', barracks_ranged: '🏬', ancient: '🗄', fountain: '🍽',
};
const CAMP_GLYPH = { small: '🧹', medium: '🧮', large: '⚖️', ancient: '🔐' };

export function initRender(canvas) {
  cv = canvas;
  ctx = cv.getContext('2d', { alpha: false });
  fog = document.createElement('canvas');
  fctx = fog.getContext('2d');
  resize();
  addEventListener('resize', resize);
}

export function resize() {
  dpr = Math.min(devicePixelRatio || 1, 2);
  W = cv.clientWidth; H = cv.clientHeight;
  // Экран игры может быть ещё скрыт — тогда размеры нулевые и рисовать нечего
  if (W < 2 || H < 2) { W = 0; H = 0; return; }
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  fog.width = cv.width; fog.height = cv.height;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// --- преобразования координат ---------------------------------------------
export function w2s(x, y) {
  return [(x - cam.x) * cam.zoom + W / 2, (y - cam.y) * cam.zoom + H / 2];
}
export function s2w(sx, sy) {
  return [(sx - W / 2) / cam.zoom + cam.x, (sy - H / 2) / cam.zoom + cam.y];
}
export function viewSize() { return { W, H }; }

export function centerOnHero() {
  const h = myHero();
  if (h) { const p = interpolated(h); cam.x = p.x; cam.y = p.y; }
}

export function panBy(dx, dy) {
  cam.follow = false;
  cam.x += dx / cam.zoom; cam.y += dy / cam.zoom;
  clampCam();
}

export function zoomBy(f) {
  cam.zoom = Math.max(0.18, Math.min(1.4, cam.zoom * f));
}

function clampCam() {
  const s = G.map ? G.map.size : 7200;
  cam.x = Math.max(-400, Math.min(s + 400, cam.x));
  cam.y = Math.max(-400, Math.min(s + 400, cam.y));
}

// --- главный проход --------------------------------------------------------
export function draw(castPreview) {
  if (!ctx) return;
  if (W < 2 || H < 2) { resize(); if (W < 2 || H < 2) return; }
  if (cam.follow) centerOnHero();

  ctx.fillStyle = '#0b0f14';
  ctx.fillRect(0, 0, W, H);
  if (!G.map) return;

  drawGround();
  drawFog();
  drawOrderMarker();
  if (castPreview) drawCastPreview(castPreview);
  drawEntities();
  drawProjectiles();
  drawFx();
  drawOverheads();
  drawFloaters();
}

// --- земля -----------------------------------------------------------------
function drawGround() {
  const M = G.map;
  const [x0, y0] = w2s(0, 0);
  const size = M.size * cam.zoom;

  ctx.fillStyle = '#1a212a';
  ctx.fillRect(x0, y0, size, size);

  // ковролин: едва заметная сетка, чтобы читалось движение
  const step = 600 * cam.zoom;
  if (step > 12) {
    ctx.strokeStyle = '#212a35'; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let gx = 0; gx <= M.size; gx += 600) {
      const [sx] = w2s(gx, 0);
      ctx.moveTo(sx, y0); ctx.lineTo(sx, y0 + size);
    }
    for (let gy = 0; gy <= M.size; gy += 600) {
      const [, sy] = w2s(0, gy);
      ctx.moveTo(x0, sy); ctx.lineTo(x0 + size, sy);
    }
    ctx.stroke();
  }

  // зоны баз — лёгкий намёк плюс рамка, а не заливка на пол-экрана
  for (const [team, r] of Object.entries(M.bases)) {
    const [bx, by] = w2s(r[0], r[1]);
    const bw = (r[2] - r[0]) * cam.zoom, bh = (r[3] - r[1]) * cam.zoom;
    ctx.fillStyle = team === '0' ? 'rgba(63,191,111,.07)' : 'rgba(217,76,76,.07)';
    ctx.fillRect(bx, by, bw, bh);
    ctx.strokeStyle = team === '0' ? 'rgba(63,191,111,.35)' : 'rgba(217,76,76,.35)';
    ctx.setLineDash([10, 8]); ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, bw, bh);
    ctx.setLineDash([]);
  }

  // река
  ctx.strokeStyle = '#22384a'; ctx.lineWidth = 520 * cam.zoom;
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  poly(M.river); ctx.stroke();

  // линии
  ctx.strokeStyle = '#27313d'; ctx.lineWidth = 440 * cam.zoom;
  for (const pts of Object.values(M.lanes)) { poly(pts); ctx.stroke(); }
  ctx.strokeStyle = '#2e3a48'; ctx.lineWidth = 300 * cam.zoom;
  for (const pts of Object.values(M.lanes)) { poly(pts); ctx.stroke(); }

  // стены — офисные комнаты
  ctx.lineWidth = 1;
  for (const [a, b, c, d] of M.walls) {
    const [sx, sy] = w2s(a, b);
    const w = (c - a) * cam.zoom, h = (d - b) * cam.zoom;
    ctx.fillStyle = '#323d4c';
    ctx.fillRect(sx, sy, w, h);
    ctx.strokeStyle = '#4a5a70';
    ctx.strokeRect(sx + .5, sy + .5, w - 1, h - 1);
  }

  // лагеря, легаси, руны, магазины
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const gs = Math.max(9, 22 * cam.zoom);
  ctx.font = `${gs}px serif`;
  for (const [, size, cx, cy] of M.camps) {
    const [sx, sy] = w2s(cx, cy);
    ring(sx, sy, 46 * cam.zoom, '#3a4352');
    ctx.fillText(CAMP_GLYPH[size] || '•', sx, sy);
  }
  const [rx, ry] = w2s(M.roshan[0], M.roshan[1]);
  ring(rx, ry, 90 * cam.zoom, '#6b4a2a');
  ctx.font = `${Math.max(12, 34 * cam.zoom)}px serif`;
  ctx.fillText('🗿', rx, ry);
  ctx.font = `${gs}px serif`;
  for (const [px, py] of M.runes) {
    const [sx, sy] = w2s(px, py); ring(sx, sy, 40 * cam.zoom, '#5a4a8a');
    ctx.fillText('✨', sx, sy);
  }
  for (const [px, py] of M.bounty) {
    const [sx, sy] = w2s(px, py); ring(sx, sy, 34 * cam.zoom, '#7a6a2a');
    ctx.fillText('💰', sx, sy);
  }
  for (const [px, py] of M.shops) {
    const [sx, sy] = w2s(px, py); ring(sx, sy, 52 * cam.zoom, '#2a5a5a');
    ctx.fillText('🛒', sx, sy);
  }
}

function poly(pts) {
  ctx.beginPath();
  pts.forEach(([x, y], i) => {
    const [sx, sy] = w2s(x, y);
    i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy);
  });
}

function ring(x, y, r, color) {
  if (r < 2) return;
  ctx.strokeStyle = color; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.stroke();
}

// --- туман войны -----------------------------------------------------------
function drawFog() {
  const team = myTeam();
  fctx.clearRect(0, 0, W, H);
  fctx.fillStyle = 'rgba(5,8,13,.72)';
  fctx.fillRect(0, 0, W, H);
  fctx.globalCompositeOperation = 'destination-out';
  for (const u of G.units.values()) {
    if (u.team !== team || u.alive === false) continue;
    const p = interpolated(u);
    const [sx, sy] = w2s(p.x, p.y);
    const vision = (u.vis || 900) * cam.zoom;
    if (sx < -vision || sy < -vision || sx > W + vision || sy > H + vision) continue;
    const g = fctx.createRadialGradient(sx, sy, vision * 0.45, sx, sy, vision);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    fctx.fillStyle = g;
    fctx.beginPath(); fctx.arc(sx, sy, vision, 0, 6.2832); fctx.fill();
  }
  fctx.globalCompositeOperation = 'source-over';
  ctx.drawImage(fog, 0, 0, W, H);
}

// --- сущности --------------------------------------------------------------
function drawEntities() {
  const list = [...G.units.values()];
  // Сначала строения, потом мелочь, потом герои — герои всегда сверху
  list.sort((a, b) => rank(a) - rank(b) || a.y - b.y);
  for (const u of list) drawUnit(u);
}

function rank(u) {
  if (u.e === 'fountain' || u.e === 'ancient') return 0;
  if (u.e === 'tower' || u.e === 'barracks') return 1;
  if (u.e === 'hero' || u.e === 'illusion') return 3;
  return 2;
}

function drawUnit(u) {
  const p = interpolated(u);
  const [sx, sy] = w2s(p.x, p.y);
  const r = Math.max(3, (u.r || 24) * cam.zoom);
  if (sx < -80 || sy < -80 || sx > W + 80 || sy > H + 80) return;

  const dead = u.alive === false;
  const col = dead ? '#3a4048' : TEAM_COLOR[u.team] ?? '#999';

  if (u.e === 'tower' || u.e === 'barracks' || u.e === 'ancient' || u.e === 'fountain') {
    ctx.fillStyle = dead ? '#1a1d22' : TEAM_DARK[u.team];
    ctx.strokeStyle = col; ctx.lineWidth = 2;
    roundRect(sx - r, sy - r, r * 2, r * 2, r * .3);
    ctx.fill(); ctx.stroke();
    if (r > 11) {
      ctx.font = `${r * 1.15}px serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.globalAlpha = dead ? .3 : 1;
      ctx.fillText(BUILDING_GLYPH[u.kind] || '▪', sx, sy);
      ctx.globalAlpha = 1;
    }
    return;
  }

  if (dead) return;

  const isHero = u.e === 'hero' || u.e === 'illusion';
  const invis = (u.flags & (1 << 8)) !== 0;
  ctx.globalAlpha = invis ? .45 : 1;

  ctx.fillStyle = isHero ? col : TEAM_DARK[u.team];
  ctx.strokeStyle = col;
  ctx.lineWidth = isHero ? 2.5 : 1.2;
  ctx.beginPath(); ctx.arc(sx, sy, r, 0, 6.2832); ctx.fill(); ctx.stroke();

  // направление взгляда
  if (r > 5) {
    const fx = sx + Math.cos(u.facing || 0) * r * 1.35;
    const fy = sy + Math.sin(u.facing || 0) * r * 1.35;
    ctx.strokeStyle = '#0009'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(fx, fy); ctx.stroke();
  }

  if (isHero && r > 9) {
    ctx.font = `${r * 1.1}px serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(HERO_GLYPH[u.hero] || '●', sx, sy);
  }
  ctx.globalAlpha = 1;

  // свой герой — золотое кольцо и круг дальности атаки
  if (G.me && u.id === G.me.id) {
    ring(sx, sy, r + 5, '#f0c04a');
    const ar = (G.me.arange || 0) * cam.zoom;
    if (ar > r + 8) {
      ctx.setLineDash([3, 7]);
      ring(sx, sy, ar, 'rgba(240,192,74,.22)');
      ctx.setLineDash([]);
    }
  }
}

function roundRect(x, y, w, h, rad) {
  ctx.beginPath();
  ctx.moveTo(x + rad, y);
  ctx.arcTo(x + w, y, x + w, y + h, rad);
  ctx.arcTo(x + w, y + h, x, y + h, rad);
  ctx.arcTo(x, y + h, x, y, rad);
  ctx.arcTo(x, y, x + w, y, rad);
  ctx.closePath();
}

// --- полоски здоровья и подписи -------------------------------------------
function drawOverheads() {
  const team = myTeam();
  for (const u of G.units.values()) {
    if (u.alive === false) continue;
    if (!u.mhp) continue;
    const p = interpolated(u);
    const [sx, sy] = w2s(p.x, p.y);
    if (sx < -60 || sy < -60 || sx > W + 60 || sy > H + 60) continue;
    const r = Math.max(3, (u.r || 24) * cam.zoom);
    const isHero = u.e === 'hero' || u.e === 'illusion';
    const bw = isHero ? Math.max(34, r * 2.6) : Math.max(16, r * 2.1);
    const bh = isHero ? 5 : 3;
    const by = sy - r - bh - 5;
    const frac = Math.max(0, Math.min(1, u.hp / u.mhp));

    ctx.fillStyle = '#000a';
    ctx.fillRect(sx - bw / 2 - 1, by - 1, bw + 2, bh + 2);
    ctx.fillStyle = u.team === team ? '#4fd07a' : '#e05555';
    ctx.fillRect(sx - bw / 2, by, bw * frac, bh);

    if (isHero && u.mmana > 0) {
      const mf = Math.max(0, Math.min(1, u.mana / u.mmana));
      ctx.fillStyle = '#000a';
      ctx.fillRect(sx - bw / 2 - 1, by + bh, bw + 2, 4);
      ctx.fillStyle = '#5fa3f0';
      ctx.fillRect(sx - bw / 2, by + bh + 1, bw * mf, 2);
    }

    if (isHero && cam.zoom > 0.3) {
      ctx.font = '11px ' + getComputedStyle(document.body).fontFamily;
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
      ctx.fillStyle = '#000'; ctx.fillText(u.n, sx + 1, by - 4);
      ctx.fillStyle = u.team === team ? '#bfe8cd' : '#f0bcbc';
      ctx.fillText(u.n, sx, by - 5);
    }
  }
}

// --- снаряды, эффекты, цифры ----------------------------------------------
function drawProjectiles() {
  for (const p of G.projectiles) {
    const [sx, sy] = w2s(p.x, p.y);
    ctx.fillStyle = p.visual === 'attack' ? '#e8d7a0' : '#9fd0ff';
    ctx.beginPath();
    ctx.arc(sx, sy, Math.max(2, (p.visual === 'attack' ? 6 : 10) * cam.zoom), 0, 6.2832);
    ctx.fill();
  }
}

function drawFx() {
  const now = performance.now();
  for (const f of G.fx) {
    const age = (now - f.born) / 900;
    const [sx, sy] = w2s(f.x, f.y);
    ctx.strokeStyle = `rgba(150,200,255,${(1 - age) * .8})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(sx, sy, f.r * cam.zoom * (0.5 + age * 0.5), 0, 6.2832);
    ctx.stroke();
  }
}

function drawFloaters() {
  const now = performance.now();
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (const f of G.floaters) {
    const age = (now - f.born) / 1300;
    const [sx, sy] = w2s(f.x, f.y);
    const y = sy - 26 - age * 42 - (f.jy || 0);
    ctx.globalAlpha = Math.max(0, 1 - age);
    ctx.font = `${Math.round(13 * f.scale)}px ${getComputedStyle(document.body).fontFamily}`;
    // Обводка, а не тень: на светлой земле тень сливается
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(0,0,0,.85)';
    ctx.strokeText(f.text, sx + f.jx, y);
    ctx.fillStyle = f.color;
    ctx.fillText(f.text, sx + f.jx, y);
  }
  ctx.globalAlpha = 1;
}

// --- индикаторы приказа и прицеливания -------------------------------------
let orderMark = null;
export function markOrder(x, y, hostile) {
  orderMark = { x, y, hostile, born: performance.now() };
}

function drawOrderMarker() {
  if (!orderMark) return;
  const age = (performance.now() - orderMark.born) / 600;
  if (age > 1) { orderMark = null; return; }
  const [sx, sy] = w2s(orderMark.x, orderMark.y);
  ctx.strokeStyle = orderMark.hostile ? '#e05555' : '#4fd07a';
  ctx.lineWidth = 2; ctx.globalAlpha = 1 - age;
  ctx.beginPath(); ctx.arc(sx, sy, 6 + age * 22, 0, 6.2832); ctx.stroke();
  ctx.globalAlpha = 1;
}

function drawCastPreview(pv) {
  const h = myHero();
  if (!h) return;
  const p = interpolated(h);
  const [hx, hy] = w2s(p.x, p.y);
  if (pv.range > 0) {
    ctx.strokeStyle = 'rgba(120,180,255,.35)';
    ctx.setLineDash([6, 6]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(hx, hy, pv.range * cam.zoom, 0, 6.2832); ctx.stroke();
    ctx.setLineDash([]);
  }
  if (pv.mx == null) return;
  const [mwx, mwy] = s2w(pv.mx, pv.my);
  let tx = mwx, ty = mwy;
  if (pv.range > 0) {
    const dx = mwx - p.x, dy = mwy - p.y;
    const d = Math.hypot(dx, dy);
    if (d > pv.range) { tx = p.x + dx / d * pv.range; ty = p.y + dy / d * pv.range; }
  }
  const [sx, sy] = w2s(tx, ty);
  ctx.strokeStyle = 'rgba(140,200,255,.9)'; ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(sx, sy, Math.max(8, (pv.aoe || 60) * cam.zoom), 0, 6.2832);
  ctx.stroke();
  ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(sx, sy);
  ctx.strokeStyle = 'rgba(140,200,255,.25)'; ctx.stroke();
}

// --- миникарта -------------------------------------------------------------
export function drawMinimap(mm) {
  if (!G.map) return;
  const c = mm.getContext('2d');
  const S = mm.width, k = S / G.map.size;
  c.fillStyle = '#0b0f14'; c.fillRect(0, 0, S, S);

  c.strokeStyle = '#1e2833'; c.lineWidth = 10 * k * 3;
  for (const pts of Object.values(G.map.lanes)) {
    c.beginPath();
    pts.forEach(([x, y], i) => i ? c.lineTo(x * k, y * k) : c.moveTo(x * k, y * k));
    c.stroke();
  }
  c.fillStyle = '#222b36';
  for (const [a, b, cc, d] of G.map.walls) {
    c.fillRect(a * k, b * k, (cc - a) * k, (d - b) * k);
  }

  const team = myTeam();
  for (const u of G.units.values()) {
    if (u.alive === false) continue;
    const p = interpolated(u);
    const isHero = u.e === 'hero';
    const isB = u.e === 'tower' || u.e === 'barracks' || u.e === 'ancient';
    if (!isHero && !isB && u.team !== team) continue;
    c.fillStyle = TEAM_COLOR[u.team] ?? '#888';
    const s = isHero ? 4.5 : isB ? 3.5 : 2;
    if (isB) c.fillRect(p.x * k - s / 2, p.y * k - s / 2, s, s);
    else { c.beginPath(); c.arc(p.x * k, p.y * k, s, 0, 6.2832); c.fill(); }
    if (G.me && u.id === G.me.id) {
      c.strokeStyle = '#f0c04a'; c.lineWidth = 1.5;
      c.beginPath(); c.arc(p.x * k, p.y * k, s + 2.5, 0, 6.2832); c.stroke();
    }
  }

  // рамка видимой области
  const vw = W / cam.zoom * k, vh = H / cam.zoom * k;
  c.strokeStyle = '#ffffff44'; c.lineWidth = 1;
  c.strokeRect(cam.x * k - vw / 2, cam.y * k - vh / 2, vw, vh);
}

export function pickUnitAt(sx, sy) {
  let best = null, bestD = 1e9;
  for (const u of G.units.values()) {
    if (u.alive === false) continue;
    const p = interpolated(u);
    const [ux, uy] = w2s(p.x, p.y);
    const r = Math.max(8, (u.r || 24) * cam.zoom) + 4;
    const d = Math.hypot(ux - sx, uy - sy);
    if (d <= r && d < bestD) { bestD = d; best = u; }
  }
  return best;
}
