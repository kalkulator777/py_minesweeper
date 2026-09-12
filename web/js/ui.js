// Интерфейс: меню, лобби, HUD, магазин, таблица, пауза.

import { G, send, connect, savedName, myHero } from './net.js';
import { ui, pressAbility, pressItem } from './input.js';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
};

const ABIL_HOTKEY = ['Q', 'W', 'E', 'R'];
const ITEM_HOTKEY = ['Z', 'X', 'C', 'V', 'B', 'N'];
const HERO_GLYPH = {
  sysadmin: '🖥', senior: '👨‍💻', analyst: '📈', hr: '📋',
  scrum_master: '🔁', security: '🛡', accountant: '🧮', junior: '🐣',
};
const ITEM_GLYPH_FALLBACK = '📦';

let selectedHero = '';

export function showScreen(name) {
  for (const s of document.querySelectorAll('.screen')) s.classList.remove('active');
  $('screen-' + name).classList.add('active');
}

// ==========================================================================
//  Меню
// ==========================================================================
export function initMenu() {
  $('inp-name').value = savedName() || '';
  $('inp-name').focus();

  $('btn-host').onclick = () => {
    const name = ($('inp-name').value || '').trim() || 'Аноним';
    connect(name);
    showScreen('lobby');
  };
  $('inp-name').addEventListener('keydown', e => {
    if (e.key === 'Enter') $('btn-host').click();
  });
  $('btn-connect').onclick = () => {
    let a = ($('inp-addr').value || '').trim();
    if (!a) return;
    if (!/^https?:\/\//.test(a)) a = 'http://' + a;
    if (!/:\d+/.test(a)) a += ':8888';
    location.href = a;
  };

  pollGames();
  setInterval(pollGames, 3000);
}

async function pollGames() {
  const list = $('lan-list'), status = $('lan-status');
  try {
    const r = await fetch('/api/games', { cache: 'no-store' });
    const d = await r.json();
    list.innerHTML = '';
    if (!d.discovery) {
      status.textContent = 'поиск недоступен';
      status.title = d.note || '';
    } else {
      status.textContent = d.games.length ? `найдено: ${d.games.length}` : 'пока пусто';
    }
    if (!d.games.length) {
      const li = el('li');
      li.className = 'lan-empty';
      li.textContent = 'Матчей в сети не видно. Создай свой — коллеги увидят его здесь.';
      list.appendChild(li);
      return;
    }
    for (const g of d.games) {
      const li = el('li');
      const left = el('div');
      left.appendChild(el('div', 'who', g.name));
      const phase = g.phase === 'lobby' ? 'набор игроков'
        : g.phase === 'finished' ? 'завершён' : 'идёт матч';
      left.appendChild(el('div', 'meta', `${phase} · игроков: ${g.players} · ${g.ip}:${g.port}`));
      li.appendChild(left);
      const b = el('button', 'btn small', 'Зайти');
      b.onclick = () => { location.href = g.url; };
      li.appendChild(b);
      list.appendChild(li);
    }
  } catch (e) {
    status.textContent = 'сервер недоступен';
  }
}

// ==========================================================================
//  Лобби
// ==========================================================================
export function initLobby() {
  for (const b of document.querySelectorAll('[data-join-team]')) {
    b.onclick = () => send({ t: 'set_team', team: +b.dataset.joinTeam });
  }
  for (const b of document.querySelectorAll('[data-add-bot]')) {
    b.onclick = () => send({ t: 'add_bot', team: +b.dataset.addBot });
  }
  $('btn-start').onclick = () => send({ t: 'start' });
}

export function renderLobby() {
  const st = G.state;
  $('lobby-title').textContent = st.room || 'Лобби';
  fetch('/api/info', { cache: 'no-store' })
    .then(r => r.json())
    .then(d => { $('lobby-url').textContent = `${d.ip}:${d.port}`; })
    .catch(() => {});

  for (const team of [0, 1]) {
    const ul = $('roster-' + team);
    ul.innerHTML = '';
    for (const p of st.players.filter(p => p.team === team)) {
      const li = el('li');
      const nm = el('span', p.connected ? '' : 'off',
        p.name + (p.pid === G.pid ? ' (ты)' : '') + (p.bot ? ' 🤖' : ''));
      li.appendChild(nm);
      const hn = p.hero && G.heroDefs[p.hero] ? G.heroDefs[p.hero].name : 'не выбран';
      li.appendChild(el('span', 'hero-tag', hn));
      ul.appendChild(li);
    }
  }
  renderHeroGrid();
  const picked = st.players.filter(p => p.hero).length;
  $('lobby-hint').textContent = picked
    ? `Готовы: ${picked}. Начать может любой.`
    : 'Выберите героя, чтобы начать.';
  $('btn-start').disabled = !picked;
}

let gridBuilt = false;

function renderHeroGrid() {
  const grid = $('hero-grid');
  const myTeam = G.you ? G.you.team : 0;
  const taken = new Set(G.state.players
    .filter(p => p.team === myTeam && p.pid !== G.pid && p.hero)
    .map(p => p.hero));

  // Сетку строим один раз. Перестройка на каждом обновлении состояния
  // отбирала бы у карточек фокус и ломала клик, начатый до обновления.
  if (!gridBuilt) {
    grid.innerHTML = '';
    for (const [key, h] of Object.entries(G.heroDefs)) {
      const card = el('div', 'hero-card');
      card.dataset.hero = key;
      card.appendChild(el('div', 'glyph', HERO_GLYPH[key] || '\u25cf'));
      card.appendChild(el('div', 'hname', h.name));
      card.appendChild(el('div', 'role', h.archetype || (h.roles || []).join('/')));
      card.appendChild(el('div', 'proto', 'как ' + h.prototype));
      card.onclick = () => {
        if (card.classList.contains('taken')) return;
        selectedHero = key;
        send({ t: 'pick_hero', hero: key });
        showHeroDetail(key);
        refreshHeroCards();
      };
      card.onmouseenter = () => showHeroDetail(key);
      grid.appendChild(card);
    }
    gridBuilt = true;
  }
  refreshHeroCards();
  if (selectedHero) showHeroDetail(selectedHero);
}

function refreshHeroCards() {
  const myTeam = G.you ? G.you.team : 0;
  const taken = new Set(G.state.players
    .filter(p => p.team === myTeam && p.pid !== G.pid && p.hero)
    .map(p => p.hero));
  const mine = (G.you && G.you.hero) || selectedHero;
  for (const card of document.querySelectorAll('.hero-card')) {
    const key = card.dataset.hero;
    card.classList.toggle('taken', taken.has(key));
    card.classList.toggle('sel', key === mine);
  }
}

function showHeroDetail(key) {
  const h = G.heroDefs[key];
  if (!h) return;
  const box = $('hero-detail');
  box.className = 'hero-detail on';
  box.innerHTML = '';
  box.appendChild(el('h4', '', `${h.name} — ${h.title || ''}`));
  box.appendChild(el('div', 'muted',
    `${h.archetype} · прототип: ${h.prototype} · ${h.attack_type === 'melee' ? 'ближний бой' : 'дальний бой'} · сложность ${h.difficulty}/3`));
  if (h.lore) box.appendChild(el('div', 'muted', h.lore));
  (h.abilities || []).forEach((a, i) => {
    const row = el('div', 'ab-row');
    row.appendChild(el('div', 'ab-key', a.hotkey || ABIL_HOTKEY[i]));
    const t = el('div', 'ab-txt');
    t.appendChild(el('b', '', a.name));
    t.appendChild(el('p', '', a.desc || ''));
    row.appendChild(t);
    box.appendChild(row);
  });
}

// ==========================================================================
//  HUD
// ==========================================================================
export function initHud() {
  $('btn-shop').onclick = () => toggleShop(!ui.shop);
  $('shop-close').onclick = () => toggleShop(false);
  $('btn-pause').onclick = () => send({ t: G.state.paused ? 'unpause' : 'pause' });
  $('btn-unpause').onclick = () => send({ t: 'unpause' });
  $('shop-search').addEventListener('input', renderShop);
}

export function renderHud() {
  const me = G.me;
  if (!me) return;

  $('portrait').innerHTML = `${HERO_GLYPH[heroKeyOfMe()] || '●'}<span class="lvl">${me.lvl}</span>`;

  pct('bar-hp', me.hp / Math.max(1, me.mhp));
  $('txt-hp').textContent = `${me.hp} / ${me.mhp}`;
  pct('bar-mana', me.mana / Math.max(1, me.mmana));
  $('txt-mana').textContent = `${me.mana} / ${me.mmana}`;
  const span = Math.max(1, me.xp1 - me.xp0);
  pct('bar-xp', (me.xp - me.xp0) / span);

  $('hero-stats').innerHTML =
    `<div>СИЛ <b>${me.str}</b> ЛОВ <b>${me.agi}</b> ИНТ <b>${me.int}</b></div>` +
    `<div>урон <b>${me.dmg[0]}-${me.dmg[1]}</b></div>` +
    `<div>броня <b>${me.armor}</b> маг <b>${me.mres}%</b></div>` +
    `<div>скор <b>${me.ms}</b></div>`;

  $('gold').textContent = `${me.gold} ₿`;
  renderAbilities(me);
  renderItems(me);
  renderBuffs(me);
  renderRespawn(me);
}

function heroKeyOfMe() {
  const h = myHero();
  return h ? h.hero : '';
}

function pct(id, v) {
  $(id).style.width = Math.max(0, Math.min(1, v)) * 100 + '%';
}

function renderAbilities(me) {
  const box = $('abilities');
  box.innerHTML = '';
  me.abil.forEach((a, i) => {
    const d = el('div', 'ab');
    if (a.ult) d.classList.add('ult');
    const usable = a.lvl > 0 && a.cd <= 0 && me.mana >= a.mana && a.tgt !== 'passive';
    d.classList.add(usable ? 'ready' : 'no');
    d.innerHTML = `<span class="hk">${a.h || ABIL_HOTKEY[i]}</span><span class="g">${glyphForAbility(a, i)}</span>`;

    const pip = el('div', 'pip');
    for (let k = 0; k < a.max; k++) {
      const p = el('i');
      if (k < a.lvl) p.classList.add('on');
      pip.appendChild(p);
    }
    d.appendChild(pip);

    if (a.cd > 0) d.appendChild(el('div', 'cd', Math.ceil(a.cd)));
    if (me.ap > 0 && a.lvl < a.max) {
      const up = el('div', 'up', '+');
      up.onclick = (e) => { e.stopPropagation(); send({ t: 'level_up', i }); };
      d.appendChild(up);
    }
    d.onclick = () => pressAbility(i, false);
    d.title = `${a.n}\n${a.desc || ''}\nмана: ${a.mana} · откат: ${a.cdmax}с`;
    box.appendChild(d);
  });
}

// Иконку выводим из того, что способность реально делает: у клиента есть
// полные определения героев, так что гадать по номеру слота незачем.
const OP_GLYPH = [
  ['taunt', '📣'], ['pull', '🪝'], ['push', '💨'], ['cyclone', '🌪'],
  ['hex', '🐣'], ['stun', '💫'], ['silence', '🤐'], ['root', '⛓'],
  ['execute', '🪓'], ['heal', '💚'], ['shield', '🛡'], ['cheat_death', '⏳'],
  ['invisible', '👻'], ['magic_immune', '🏖'], ['invulnerable', '✨'],
  ['blink', '🌀'], ['leap', '🦘'], ['illusion', '👥'], ['summon', '🐾'],
  ['chain', '🔗'], ['global', '🌍'], ['channel', '⏱'], ['slow', '🐌'],
  ['mana_burn', '🔥'], ['true_sight', '👁'], ['dot', '☠'],
  ['crit', '🎯'], ['evasion', '🍃'], ['lifesteal', '🩸'], ['cleave', '🌊'],
  ['damage', '💥'], ['stat_buff', '⬆'], ['aura', '🔆'],
];

function collectOps(effects, acc) {
  for (const e of effects || []) {
    acc.add(e.op);
    for (const k of ['on_hit', 'effects', 'on_tick', 'on_kill', 'on_finish']) {
      if (Array.isArray(e[k])) collectOps(e[k], acc);
    }
  }
  return acc;
}

function glyphForAbility(a, i) {
  if (a.tgt === 'passive') {
    const def = findAbilityDef(a.k);
    const ops = def ? collectOps(def.effects, new Set()) : new Set();
    for (const [op, g] of OP_GLYPH) if (ops.has(op)) return g;
    return '🔒';
  }
  const def = findAbilityDef(a.k);
  if (def) {
    const ops = collectOps(def.effects, new Set());
    for (const [op, g] of OP_GLYPH) if (ops.has(op)) return g;
  }
  return a.ult ? '🔱' : '✴';
}

function findAbilityDef(key) {
  for (const h of Object.values(G.heroDefs)) {
    for (const a of h.abilities || []) if (a.key === key) return a;
  }
  return null;
}

function renderItems(me) {
  const box = $('items');
  box.innerHTML = '';
  me.items.forEach((it, i) => {
    const d = el('div', 'it' + (it ? '' : ' empty'));
    d.innerHTML = `<span class="hk">${ITEM_HOTKEY[i]}</span>`;
    if (it) {
      d.appendChild(el('span', '', itemGlyph(it.k)));
      if (it.cd > 0) d.appendChild(el('div', 'cd', Math.ceil(it.cd)));
      d.title = `${it.n}${it.tgt ? '\nактивный' : ''}`;
      d.onclick = () => pressItem(i);
      d.oncontextmenu = (e) => { e.preventDefault(); send({ t: 'sell', slot: i }); };
    }
    box.appendChild(d);
  });
  const dv = me.deliv || [];
  if (dv.length) {
    const note = el('div', 'muted', 'едет: ' + dv.map(d => Math.ceil(d.t) + 'с').join(', '));
    note.style.gridColumn = '1 / -1';
    note.style.fontSize = '10px';
    box.appendChild(note);
  }
}

const ITEM_GLYPHS = {
  boots: '👟', vpn: '🔐', day_off: '🏖', corporate_card: '💳',
  coffee_mug: '☕', energy_drink: '🥤', headphones: '🎧',
  mech_keyboard: '⌨️', ergo_chair: '🪑', annual_bonus: '💎',
  sick_leave: '🤒', blacklist: '🚫', deadline_kick: '⏰',
  teambuilding: '🤝', second_monitor: '🖥', observer_ward: '📹',
  corporate_taxi: '🚕', dnd_status: '🔕',
};
function itemGlyph(key) {
  if (ITEM_GLYPHS[key]) return ITEM_GLYPHS[key];
  const d = G.itemDefs[key];
  if (!d) return ITEM_GLYPH_FALLBACK;
  return ITEM_GLYPH_FALLBACK;
}

function renderBuffs(me) {
  const box = $('buffs');
  box.innerHTML = '';
  for (const m of (me.mods || [])) {
    const d = el('div', 'bf');
    d.textContent = m.n + (m.r != null ? ` ${Math.ceil(m.r)}с` : '');
    box.appendChild(d);
  }
}

function renderRespawn(me) {
  const box = $('respawn');
  if (me.alive) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  box.innerHTML = `<div class="muted">Возрождение через</div>
    <div class="big">${Math.ceil(me.resp)}</div>
    <div class="muted">Магазин работает и пока ты мёртв</div>`;
}

// ==========================================================================
//  Магазин
// ==========================================================================
export function toggleShop(on) {
  ui.shop = on;
  $('shop').classList.toggle('hidden', !on);
  if (on) renderShop();
}

function renderShop() {
  const body = $('shop-body');
  const q = ($('shop-search').value || '').trim().toLowerCase();
  const gold = G.me ? G.me.gold : 0;
  body.innerHTML = '';

  const layout = Object.keys(G.shopLayout).length
    ? G.shopLayout
    : { 'Все предметы': Object.keys(G.itemDefs) };

  for (const [cat, keys] of Object.entries(layout)) {
    const shown = keys.filter(k => {
      const d = G.itemDefs[k];
      if (!d) return false;
      if (!q) return true;
      return (d.name || '').toLowerCase().includes(q) ||
             (d.prototype || '').toLowerCase().includes(q);
    });
    if (!shown.length) continue;

    const sec = el('div', 'shop-cat');
    sec.appendChild(el('h4', '', cat));
    const grid = el('div', 'shop-grid');
    for (const k of shown) {
      const d = G.itemDefs[k];
      const card = el('div', 'si ' + (gold >= d.cost ? 'rich' : 'poor'));
      card.innerHTML = `<span class="n">${itemGlyph(k)} ${d.name}</span>
        <span class="c">${d.cost} ₿</span>`;
      if (d.prototype) card.appendChild(el('span', 'p', 'как ' + d.prototype));
      card.title = (d.desc || '') + (d.components && d.components.length
        ? '\n\nиз: ' + d.components.map(c => (G.itemDefs[c] || {}).name || c).join(' + ')
        : '');
      card.onclick = () => send({ t: 'buy', k });
      grid.appendChild(card);
    }
    sec.appendChild(grid);
    body.appendChild(sec);
  }
}

// ==========================================================================
//  Таблица счёта
// ==========================================================================
export function toggleScore(on) {
  $('scoreboard').classList.toggle('hidden', !on);
  if (on) renderScore();
}

export function renderScore() {
  const sb = G.score;
  if (!sb) return;
  const box = $('scoreboard');
  box.innerHTML = '';
  for (const team of ['0', '1']) {
    const t = sb.teams[team];
    if (!t) continue;
    const h = el('div', 'tname', `${t.name} — ${t.score}`);
    h.style.color = team === '0' ? 'var(--dev)' : 'var(--mgmt)';
    box.appendChild(h);
    const tb = el('table');
    tb.innerHTML = `<tr><th>Игрок</th><th>Герой</th><th>Ур</th><th>У/С/П</th>
      <th>Ластхиты</th><th>Бюджет</th><th>Урон</th></tr>`;
    for (const p of t.players) {
      const tr = el('tr');
      if (!p.alive) tr.className = 'dead';
      const hd = G.heroDefs[p.hero];
      tr.innerHTML = `<td>${p.n}${p.bot ? ' 🤖' : ''}</td>
        <td>${hd ? hd.name : p.hero}</td><td>${p.lvl}</td>
        <td>${p.k}/${p.d}/${p.a}</td><td>${p.lh}</td>
        <td>${p.net}</td><td>${p.hdmg}</td>`;
      tb.appendChild(tr);
    }
    box.appendChild(tb);
  }
}

// ==========================================================================
//  Верхняя панель, чат, пауза, конец
// ==========================================================================
export function renderTop() {
  const t = G.serverTime || 0;
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  $('clock').textContent = `${m}:${String(s).padStart(2, '0')}`;
  if (G.score) {
    $('score-dev').textContent = G.score.teams['0'].score;
    $('score-mgmt').textContent = G.score.teams['1'].score;
  }
  const st = G.state;
  $('wave-note').textContent = st.phase === 'pregame'
    ? `старт через ${Math.ceil(st.pregame)}` : `пинг ${G.latency} мс`;
}

export function pushChat(m) {
  const log = $('chat-log');
  const d = el('div', 'cm' + (m.sys ? ' sys' : ''));
  if (m.sys) d.textContent = m.text;
  else {
    const au = el('span', 'au', m.from + ': ');
    au.style.color = m.team === 1 ? 'var(--mgmt)' : 'var(--dev)';
    d.appendChild(au);
    d.appendChild(document.createTextNode(m.text));
  }
  log.appendChild(d);
  while (log.children.length > 40) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

export function renderPause() {
  const st = G.state;
  const box = $('pause-overlay');
  if (!st.paused) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');

  if (st.countdown > 0) {
    $('pause-title').textContent = 'Продолжаем';
    $('pause-sub').textContent = '';
    $('pause-waiting').innerHTML = `<div class="countdown">${Math.ceil(st.countdown)}</div>`;
    $('btn-unpause').classList.add('hidden');
    return;
  }
  $('btn-unpause').classList.remove('hidden');

  const waiting = st.waiting || [];
  if (st.pause_reason === 'disconnect' && waiting.length) {
    $('pause-title').textContent = 'Ждём своих';
    $('pause-sub').textContent = 'Матч замер. Никто ничего не теряет.';
    const w = $('pause-waiting');
    w.innerHTML = '';
    for (const p of waiting) {
      const row = el('div', 'waiting-row');
      row.appendChild(el('span', '', p.name + ' — отключился'));
      const b = el('button', 'btn small', 'Играть без него');
      b.onclick = () => send({ t: 'play_without', pid: p.pid });
      row.appendChild(b);
      w.appendChild(row);
    }
    $('btn-unpause').classList.add('hidden');
  } else {
    $('pause-title').textContent = 'Пауза';
    $('pause-sub').textContent = st.pause_by ? `Поставил ${st.pause_by}` : '';
    $('pause-waiting').innerHTML = '';
  }
}

export function renderKillfeed() {
  const box = $('killfeed');
  box.innerHTML = '';
  for (const k of G.killfeed.slice(-6)) {
    const d = el('div', 'kf');
    if (k.t === 'kill') {
      const v = G.units.get(k.victim), a = G.units.get(k.killer);
      d.textContent = `${a ? a.n : 'Кто-то'} ⚔ ${v ? v.n : '?'}`;
    } else if (k.t === 'tower_down') {
      d.textContent = `Пала башня T${k.tier} (${k.lane})`;
    } else if (k.t === 'rax_down') {
      d.textContent = `Пали бараки (${k.lane})`;
    } else if (k.t === 'mega') {
      d.textContent = 'Мега-крипы!';
    } else if (k.t === 'victory') {
      d.textContent = `Победа: ${k.name}`;
    }
    box.appendChild(d);
  }
}

export function toast(text) {
  const box = $('toast');
  const d = el('div', 'tst', text);
  box.appendChild(d);
  setTimeout(() => d.remove(), 2600);
}

export function renderLateJoin() {
  const box = $('latejoin');
  const needs = G.state.phase !== 'lobby' && G.state.phase !== 'finished'
    && G.you && !G.you.hero;
  box.classList.toggle('hidden', !needs);
  if (!needs || box.dataset.built) return;
  box.dataset.built = '1';
  const grid = $('late-grid');
  grid.innerHTML = '';
  for (const [key, h] of Object.entries(G.heroDefs)) {
    const card = el('div', 'hero-card');
    card.appendChild(el('div', 'glyph', HERO_GLYPH[key] || '\u25cf'));
    card.appendChild(el('div', 'hname', h.name));
    card.appendChild(el('div', 'proto', 'как ' + h.prototype));
    card.onclick = () => { send({ t: 'pick_hero', hero: key }); box.classList.add('hidden'); };
    grid.appendChild(card);
  }
}

export function renderEnd() {
  const st = G.state;
  const box = $('endscreen');
  if (st.phase !== 'finished') { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  const won = st.winner === (G.you ? G.you.team : -1);
  box.innerHTML = `<div class="end-card">
    <h1>${won ? 'Победа' : 'Поражение'}</h1>
    <p class="muted">${st.winner === 0 ? 'Разработка' : 'Менеджмент'} снесли трон</p>
    <button class="btn primary big" onclick="location.reload()">В меню</button>
  </div>`;
}
