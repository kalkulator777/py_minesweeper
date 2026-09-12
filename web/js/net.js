// Связь с сервером и хранилище состояния.
//
// Клиент не предсказывает ничего: он показывает то, что прислал сервер,
// с задержкой в INTERP_MS и плавной интерполяцией между снапшотами.
// В локальной сети эта задержка незаметна, зато картинка не дёргается.

const INTERP_MS = 100;
const HIST_MAX = 8;

export const G = {
  pid: '', name: '',
  ws: null, connected: false, reconnectTimer: null,
  map: null, heroDefs: {}, itemDefs: {}, shopLayout: {},
  you: null,
  state: { phase: 'lobby', players: [], paused: 0 },
  units: new Map(),
  projectiles: [],
  me: null,
  score: null,
  chat: [],
  fx: [],
  floaters: [],
  killfeed: [],
  serverTime: 0,
  latency: 0,
  onState: null, onWelcome: null, onChat: null, onScore: null, onError: null,
  onSaves: null,
};

export function playerId() {
  let id = null;
  try { id = localStorage.getItem('od_pid'); } catch (e) { /* приватное окно */ }
  if (!id) {
    id = 'p' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
    try { localStorage.setItem('od_pid', id); } catch (e) { /* переживём */ }
  }
  return id;
}

export function savedName() {
  try { return localStorage.getItem('od_name') || ''; } catch (e) { return ''; }
}

export function saveName(n) {
  try { localStorage.setItem('od_name', n); } catch (e) { /* переживём */ }
}

export function connect(name) {
  G.pid = playerId();
  G.name = name;
  saveName(name);
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  G.ws = ws;

  ws.onopen = () => {
    G.connected = true;
    send({ t: 'hello', pid: G.pid, name: G.name });
    pingLoop();
  };
  ws.onclose = () => {
    G.connected = false;
    // Сервер мог перезапуститься или сеть моргнуть — пробуем вернуться сами
    if (G.reconnectTimer) clearTimeout(G.reconnectTimer);
    G.reconnectTimer = setTimeout(() => connect(G.name), 1200);
  };
  ws.onerror = () => { /* onclose разберётся */ };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  return ws;
}

export function send(msg) {
  if (G.ws && G.ws.readyState === WebSocket.OPEN) {
    G.ws.send(JSON.stringify(msg));
  }
}

let pingSent = 0;
function pingLoop() {
  if (!G.connected) return;
  pingSent = performance.now();
  send({ t: 'ping', c: pingSent });
  setTimeout(pingLoop, 2000);
}

function handle(m) {
  switch (m.t) {
    case 'welcome':
      G.map = m.map; G.heroDefs = m.heroes; G.itemDefs = m.items;
      G.shopLayout = m.shop; G.you = m.you; G.chat = m.chat || [];
      G.onWelcome && G.onWelcome();
      break;

    case 'state':
      G.state = m;
      for (const p of m.players) if (p.pid === G.pid) G.you = p;
      G.onState && G.onState(m);
      break;

    case 's':
      applySnapshot(m);
      break;

    case 'score':
      G.score = m;
      G.onScore && G.onScore(m);
      break;

    case 'chat':
      G.chat.push(m.m);
      if (G.chat.length > 80) G.chat.shift();
      G.onChat && G.onChat(m.m);
      break;

    case 'saves':
      G.onSaves && G.onSaves(m.list);
      break;

    case 'saved':
      G.onError && G.onError(`Матч сохранён как «${m.name}»`, false);
      break;

    case 'pong':
      G.latency = Math.round(performance.now() - m.c);
      break;

    case 'err':
      G.onError && G.onError(m.m, m.quiet);
      break;
  }
}

function applySnapshot(m) {
  const now = performance.now();
  G.serverTime = m.time;

  if (m.new) {
    for (const s of m.new) {
      const u = G.units.get(s.id) || { hist: [] };
      Object.assign(u, s);
      G.units.set(s.id, u);
    }
  }

  for (const d of m.u) {
    const [id, x, y, facing, hp, mhp, mana, mmana, flags, level, alive] = d;
    let u = G.units.get(id);
    if (!u) { u = { id, hist: [] }; G.units.set(id, u); }
    u.x = x; u.y = y; u.facing = facing * Math.PI / 180;
    u.hp = hp; u.mhp = mhp; u.mana = mana; u.mmana = mmana;
    u.flags = flags; u.level = level; u.alive = !!alive;
    u.hist.push({ t: now, x, y });
    if (u.hist.length > HIST_MAX) u.hist.shift();
  }

  if (m.gone) for (const id of m.gone) G.units.delete(id);

  G.projectiles = (m.p || []).map(([id, x, y, visual, team]) => ({ id, x, y, visual, team }));
  if (m.me) G.me = m.me;
  if (m.ev) ingestEvents(m.ev);
}

// Позиция юнита на момент отрисовки: между двумя снапшотами, с задержкой.
export function interpolated(u) {
  const h = u.hist;
  if (!h || h.length === 0) return { x: u.x || 0, y: u.y || 0 };
  if (h.length === 1) return { x: h[0].x, y: h[0].y };
  const target = performance.now() - INTERP_MS;
  for (let i = h.length - 1; i > 0; i--) {
    const b = h[i], a = h[i - 1];
    if (a.t <= target && target <= b.t) {
      const span = b.t - a.t;
      const k = span > 0 ? (target - a.t) / span : 1;
      return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
    }
  }
  const last = h[h.length - 1];
  return { x: last.x, y: last.y };
}

function ingestEvents(evs) {
  const now = performance.now();
  for (const e of evs) {
    switch (e.t) {
      case 'dmg':
        pushFloater(e.id, '-' + e.v, e.dt === 'magical' ? '#8ab4ff'
          : e.dt === 'pure' ? '#e0a0ff' : '#ffd9a0');
        break;
      case 'heal': pushFloater(e.id, '+' + e.v, '#7ce6a0'); break;
      case 'crit': pushFloater(e.id, e.v + '!', '#ff9a4d', 1.5); break;
      case 'miss': pushFloater(e.id, 'мимо', '#9aa7b8', .8); break;
      case 'gold': if (e.v >= 12) pushFloater(e.id, '+' + e.v + '₿', '#f0c04a', .9); break;
      case 'fx': G.fx.push({ ...e, born: now }); break;
      case 'levelup': pushFloater(e.id, 'ур. ' + e.lvl, '#f0c04a', 1.4); break;
      case 'kill': G.killfeed.push({ ...e, born: now }); break;
      case 'tower_down': G.killfeed.push({ ...e, born: now }); break;
      case 'rax_down': G.killfeed.push({ ...e, born: now }); break;
      case 'mega': G.killfeed.push({ ...e, born: now }); break;
      case 'victory': G.killfeed.push({ ...e, born: now }); break;
    }
  }
  const cutoff = now - 7000;
  G.fx = G.fx.filter(f => now - f.born < 900);
  G.floaters = G.floaters.filter(f => now - f.born < 1300);
  G.killfeed = G.killfeed.filter(k => k.born > cutoff);
}

function pushFloater(id, text, color, scale = 1) {
  const u = G.units.get(id);
  if (!u) return;
  G.floaters.push({
    x: u.x, y: u.y, text, color, scale,
    born: performance.now(), jx: (Math.random() - .5) * 26,
  });
  if (G.floaters.length > 120) G.floaters.shift();
}

export function myHero() {
  return G.me ? G.units.get(G.me.id) : null;
}

export function myTeam() {
  return G.you ? G.you.team : 0;
}
