'use strict';
/* Rubik's Cube Race - frontend.
 * No build step, no external libraries.  The browser never sees the OpenRouter key:
 * it only talks to this app's own backend (/api/*).
 *
 * One pipeline renders everything: live runs arrive as server-sent events, replays are
 * synthesised from the saved per-turn log.  Both feed process(ev).
 */

const $ = (s, r = document) => r.querySelector(s);
const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const FACE_COLORS = { U: '#f4f4f2', R: '#d9302c', F: '#1ea84b', D: '#f4c60b', L: '#f27d1d', B: '#2063d8' };
const NORMALS = { U: [0, 1, 0], R: [1, 0, 0], F: [0, 0, 1], D: [0, -1, 0], L: [-1, 0, 0], B: [0, 0, -1] };
const CELL = 36;                 // sticker size in px
const HOLD_MS = 3800;            // how long a finished puzzle stays on screen before the next one
const FINAL_HOLD_MS = 4500;      // after the last puzzle, before the statistics slide opens
const STATUS_TEXT = {
  SOLVED: 'SOLVED ✓', RAN_OUT_OF_MOVES: 'RAN OUT OF MOVES', OUT_OF_TIME: 'OUT OF TIME', ERROR: 'ERROR', CALL_LIMIT: 'API CALL LIMIT', STALLED_LOOP: 'REPEATED MOVE LOOP',
};

/* ---------------------------------------------------------------- virtual clock */
const clock = {
  speed: 1, vBase: 0, rBase: performance.now(),
  now() { return this.vBase + (performance.now() - this.rBase) / 1000 * this.speed; },
  rebase(v = 0) { this.vBase = v; this.rBase = performance.now(); },
  setSpeed(s) { const n = this.now(); this.speed = s; this.vBase = n; this.rBase = performance.now(); },
};

/* ------------------------------------------------------------------- 3D cube */
class Cube3D {
  constructor(host, geo) {
    this.geo = geo;
    host.innerHTML = '';
    const scene = h('div', 'scene');
    this.cube = h('div', 'cube3d');
    scene.appendChild(this.cube);
    host.appendChild(scene);
    const half = CELL * 1.5;
    for (const [face, n] of Object.entries(NORMALS)) {   // opaque core so the inside never shows
      const c = h('div', 'core');
      c.style.width = c.style.height = (CELL * 3) + 'px';
      c.style.marginLeft = c.style.marginTop = (-CELL * 1.5) + 'px';
      c.style.transform = this.rot(n) + ` translateZ(${half - 1.5}px)`;
      this.cube.appendChild(c);
    }
    this.stickers = geo.facelets.map(f => {
      const e = h('div', 'sticker');
      e.style.width = e.style.height = CELL + 'px';
      e.style.marginLeft = e.style.marginTop = (-CELL / 2) + 'px';
      e.style.transform = `translate3d(${f.pos[0] * CELL}px,${-f.pos[1] * CELL}px,${f.pos[2] * CELL}px) ${this.rot(f.normal)} translateZ(${CELL / 2}px)`;
      this.cube.appendChild(e);
      return e;
    });
    this.state = geo.solved;
    this.setState(this.state);
  }
  rot(n) {
    if (n[0] === 1) return 'rotateY(90deg)';
    if (n[0] === -1) return 'rotateY(-90deg)';
    if (n[1] === 1) return 'rotateX(90deg)';
    if (n[1] === -1) return 'rotateX(-90deg)';
    if (n[2] === -1) return 'rotateY(180deg)';
    return '';
  }
  setState(st) {
    this.state = st;
    for (let i = 0; i < 54; i++) this.stickers[i].style.backgroundColor = FACE_COLORS[st[i]];
  }
  /* Rotate the affected layer, then swap in the new colours. */
  async animateMove(move, newState, ms) {
    const n = NORMALS[move[0]];
    const axis = n.findIndex(v => v !== 0), sign = n[axis];
    const layer = h('div', 'layer');
    this.cube.appendChild(layer);
    const moved = [];
    this.geo.facelets.forEach((f, i) => { if (f.pos[axis] === sign) { layer.appendChild(this.stickers[i]); moved.push(i); } });
    const turns = move.endsWith('2') ? 2 : move.endsWith("'") ? -1 : 1;
    layer.style.transition = `transform ${ms}ms ease-in-out`;
    void layer.offsetWidth;
    layer.style.transform = `rotate3d(${n[0]}, ${-n[1]}, ${n[2]}, ${90 * turns}deg)`;
    await sleep(ms + 15);
    moved.forEach(i => this.cube.appendChild(this.stickers[i]));
    layer.remove();
    this.setState(newState);
  }
}

/* ---------------------------------------------------------------------- Card */
function fmtClock(s) {
  s = Math.max(0, s);
  const m = Math.floor(s / 60), r = s - m * 60;
  return `${m}:${r.toFixed(2).padStart(5, '0')}`;
}

class Card {
  constructor(spec, geo, grid) {
    this.spec = spec;
    this.el = h('article', 'card');
    this.el.dataset.key = spec.key;
    this.el.innerHTML = `
      <header>
        <span class="dot" style="background:${spec.color}"></span>
        <h3>${esc(spec.name)}</h3>
        <span class="cat ${spec.category}">${esc(spec.badge)}</span>
        <span class="mid">${esc(spec.model_id)}</span>
      </header>
      <div class="body">
        <div class="cubewrap"><div class="medal"></div><div class="cubehost"></div></div>
        <div class="metrics">
          <div class="metric"><label>TIME</label><div class="time">0:00.00</div></div>
          <div class="metric"><label>MOVES</label><div class="mv">0</div></div>
          <div class="state">waiting&hellip;</div>
          <div class="distance-progress" hidden>
            <label>SHORTEST DISTANCE TO SOLVED</label>
            <strong class="dist-number">3</strong>
            <span class="dist-trend">Starting state</span>
          </div>
          <div class="verdict"></div>
        </div>
      </div>
      <footer>
        <div class="cur"><label>CURRENT MOVE</label><span class="curmove">&ndash;</span><span class="curmeta">&nbsp;</span></div>
        <div class="hist"><span class="empty">No moves yet</span></div>
      </footer>`;
    grid.appendChild(this.el);
    this.cube = new Cube3D($('.cubehost', this.el), geo);
    this.q = {
      time: $('.time', this.el), mv: $('.mv', this.el), state: $('.state', this.el), verdict: $('.verdict', this.el),
      cur: $('.curmove', this.el), meta: $('.curmeta', this.el), hist: $('.hist', this.el), medal: $('.medal', this.el),
      distance: $('.distance-progress', this.el), distNumber: $('.dist-number', this.el), distTrend: $('.dist-trend', this.el),
    };
    this.pending = 0;
    this.chain = Promise.resolve();
    this.reset(geo.solved);
  }
  reset(state) {
    this.running = false; this.anchor = 0; this.frozen = 0; this.moves = 0; this.done = false;
    this.el.classList.remove('winner', 'solved');
    this.q.medal.className = 'medal'; this.q.medal.textContent = '';
    this.q.verdict.innerHTML = ''; this.q.cur.textContent = '–'; this.q.meta.innerHTML = '&nbsp;';
    this.q.hist.innerHTML = '<span class="empty">No moves yet</span>';
    this.q.mv.textContent = '0'; this.q.time.textContent = fmtClock(0);
    this.q.distance.hidden = true;
    this.q.distance.className = 'distance-progress';
    this.q.distNumber.textContent = '3'; this.q.distTrend.textContent = 'Starting state';
    this.setStatus('waiting…', false);
    this.pending = 0; this.chain = Promise.resolve();
    this.cube.setState(state);
  }
  begin() { this.running = true; this.anchor = clock.now(); this.setStatus(this.thinkingWord(), true); }
  thinkingWord() { return this.spec.category === 'llm' ? 'thinking…' : 'deciding…'; }
  setStatus(t, live) { this.q.state.textContent = t; this.q.state.classList.toggle('live', !!live); }
  tick() {
    if (this.running) this.q.time.textContent = fmtClock(clock.now() - this.anchor);
  }
  queueAnimation(move, state) {
    // Keep the cube in step with the data; if events pile up, skip the animation.
    const ms = Math.max(70, Math.min(260, 260 / Math.max(1, clock.speed)));
    if (this.pending > 2) { this.chain = this.chain.then(() => this.cube.setState(state)); return; }
    this.pending++;
    this.chain = this.chain.then(() => this.cube.animateMove(move, state, ms)).catch(() => this.cube.setState(state)).then(() => { this.pending--; });
  }
  markHistory() {
    this.q.hist.querySelectorAll('.chip.last').forEach(c => c.classList.remove('last'));
  }
  addChip(text, cls) {
    if (this.q.hist.querySelector('.empty')) this.q.hist.innerHTML = '';
    this.markHistory();
    const c = h('span', 'chip ' + (cls || ''), esc(text));
    c.classList.add('last');
    this.q.hist.appendChild(c);
    this.q.hist.scrollTop = this.q.hist.scrollHeight;
  }
  onMove(ev) {
    this.anchor = clock.now() - ev.elapsed_s;
    this.moves = ev.moves_used;
    this.q.mv.textContent = String(ev.moves_used);
    this.q.cur.textContent = ev.move;
    let meta = `${Math.round(ev.latency_ms)} ms`;
    if (ev.probability != null) meta += ` · p=${ev.probability.toFixed(2)}`;
    if (ev.revisited_state) meta += ' · visited before';
    if (ev.move_source === 'solver_only_fallback') meta += ' · SOLVER ONLY (model failed)';
    else if (ev.guide_overrode) meta += ` · SOLVER OVERRIDE (model: ${ev.model_proposed_move})`;
    else if (ev.move_source === 'model') meta += ' · guided choice';
    this.q.meta.textContent = meta;
    if (ev.distance_change) {
      this.q.distance.hidden = false;
      this.q.distance.className = 'distance-progress ' + ev.distance_change;
      this.q.distNumber.textContent = ev.distance_after_label ||
        (ev.distance_after == null ? '>7' : String(ev.distance_after));
      const marks = { closer: '↓ Closer to solved', farther: '↑ Farther from solved',
        same: '→ No distance change', unknown: '? Beyond exact search range' };
      this.q.distTrend.textContent = marks[ev.distance_change] || 'Unknown';
    }
    this.addChip(ev.move, ev.revisited_state ? 'progress-farther' :
      (ev.distance_change ? 'progress-' + ev.distance_change : ''));
    if (ev.distance_change) {
      const chip = this.q.hist.querySelector('.chip.last');
      if (chip) chip.title = `Shortest distance: ${ev.distance_before == null ? '>7' : ev.distance_before} → ${ev.distance_after_label} (${ev.distance_change}); exact only through 7 turns` +
        (ev.revisited_state ? '; revisits an earlier cube state' : '');
    }
    this.queueAnimation(ev.move, ev.state);
    if (!ev.solved) this.setStatus(this.thinkingWord(), true);
  }
  onFail(ev) {
    this.anchor = clock.now() - ev.elapsed_s;
    this.q.cur.textContent = '✗';
    this.q.meta.textContent = (ev.error || 'failed').slice(0, 145);
    this.q.meta.title = ev.error || 'failed';
    this.addChip('✗', 'fail');
    this.setStatus(this.thinkingWord(), true);
  }
  finish(r) {
    this.running = false; this.done = true;
    this.q.time.textContent = fmtClock(r.total_time_s);
    this.q.mv.textContent = String(r.moves_used);
    this.setStatus('', false);
    const tags = [];
    if (r.solved) { tags.push(`<div class="tag ok">${r.assisted_mode ? 'SOLVED (SOLVER-ASSISTED) ✓' : 'SOLVED ✓'}</div>`); this.el.classList.add('solved'); }
    else {
      tags.push(`<div class="tag stop">${STATUS_TEXT[r.status] || r.status}</div>`);
      tags.push('<div class="tag ns">NOT SOLVED</div>');
    }
    this.q.verdict.innerHTML = tags.join('');
    // Final cube position (after any queued animation finishes).
    this.chain = this.chain.then(() => this.cube.setState(r.final_state || this.cube.state));
  }
  setRank(rank, solved) {
    if (!solved) {
      this.q.medal.className = 'medal';
      this.q.medal.textContent = '';
      return;
    }
    const sfx = ['th', 'st', 'nd', 'rd', 'th'][Math.min(rank, 4)] || 'th';
    this.q.medal.className = 'medal r' + rank;
    this.q.medal.textContent = rank + sfx;
    if (rank === 1 && solved) this.el.classList.add('winner');
  }
}

/* ------------------------------------------------------------------ app state */
const App = {
  config: null, geo: null, cards: {}, run: null, session: 0, queue: [], draining: false,
  mode: 'idle', runInfo: null, totalPuzzles: 0, doneRuns: [], lastRun: null, es: null,
};

function showError(msg) {
  const b = $('#errbanner');
  if (!msg) { b.hidden = true; return; }
  b.textContent = msg; b.hidden = false;
}

/* ------------------------------------------------------------- identity bar */
function renderIdentity() {
  const box = $('#idbox');
  const cfg = App.config;
  let name = cfg.student_name, roll = cfg.student_roll_no;
  try { name = name || localStorage.getItem('stu_name') || ''; roll = roll || localStorage.getItem('stu_roll') || ''; } catch (e) { /* storage may be blocked */ }
  if (name && roll) {
    box.innerHTML = `<span><span class="lbl">Student</span>${esc(name)}</span><span><span class="lbl">Roll No</span>${esc(roll)}</span>`;
    return;
  }
  box.innerHTML = `<span class="id-warn">Set STUDENT_NAME / STUDENT_ROLL_NO in .env (or type them here):</span>
    <input id="in-name" type="text" placeholder="Your name" value="${esc(name)}">
    <input id="in-roll" type="text" placeholder="Roll no." value="${esc(roll)}">`;
  const save = () => {
    const n = $('#in-name').value.trim(), r = $('#in-roll').value.trim();
    try { localStorage.setItem('stu_name', n); localStorage.setItem('stu_roll', r); } catch (e) { /* ignore */ }
    if (n && r) renderIdentity();
  };
  $('#in-name').addEventListener('change', save); $('#in-roll').addEventListener('change', save);
}

/* -------------------------------------------------------------------- setup */
function assertCurrentMarkup() {
  // A descriptive error is preferable to a null-property exception if the
  // browser somehow mixes frontend versions or an HTML element was renamed.
  const ids = [
    'idbox', 'provider', 'mockbanner', 'localbanner', 'budgetbar', 'errbanner',
    'modellist', 'modelcount', 'grid', 'keynote', 'run', 'stop', 'replay',
    'tab-race', 'tab-stats', 'speedpill', 'view-race', 'view-stats',
    'suite', 'npz', 'seed', 'parallel', 'ollama-guided', 'guidance-wrap', 'autostats', 'puzzleinfo', 'puzzlebar',
  ];
  const missing = ids.filter(id => !document.getElementById(id));
  if (missing.length) throw new Error(
    'Frontend files are out of sync (missing: ' + missing.map(id => '#' + id).join(', ') +
    '). Restart the server and hard-refresh with Ctrl+Shift+R.'
  );
}

async function init() {
  assertCurrentMarkup();
  const [cfg, geo] = await Promise.all([fetch('/api/config').then(r => r.json()), fetch('/api/geometry').then(r => r.json())]);
  App.config = cfg; App.geo = geo;
  renderIdentity();
  $('#provider').value = cfg.provider || 'mock';
  updateProvider();
  $('#provider').addEventListener('change', updateProvider);
  await refreshUsage();
  $('#run').addEventListener('click', startLive);
  $('#stop').addEventListener('click', stopAll);
  $('#replay').addEventListener('click', startReplay);
  $('#tab-race').addEventListener('click', () => showView('race'));
  $('#tab-stats').addEventListener('click', () => { showView('stats'); });
  $('#speedpill').addEventListener('click', cycleSpeed);
  requestAnimationFrame(function loop() { Object.values(App.cards).forEach(c => c.tick()); requestAnimationFrame(loop); });
  renderStats(null);
}

function updateProvider() {
  const provider = $('#provider').value;
  $('#mockbanner').hidden = provider !== 'mock';
  $('#localbanner').hidden = provider !== 'ollama';
  $('#guidance-wrap').hidden = provider !== 'ollama';
  if (provider !== 'ollama') $('#ollama-guided').checked = false;
  if (provider === 'ollama') $('#parallel').checked = false; // local models may compete for RAM/VRAM
  $('#parallel').disabled = provider === 'ollama'; // server also forces serial requests
  const models = provider === 'ollama' ? App.config.local_models : App.config.models;
  const ml = $('#modellist'); ml.innerHTML = '';
  models.forEach(m => {
    const l = h('label', '', `<input type="checkbox" value="${m.key}" checked> ${esc(m.name)} <small>${esc(m.model_id)}</small>`);
    ml.appendChild(l);
  });
  ml.onchange = updateModelCount;
  buildCards(models);
  updateModelCount();
  $('#keynote').textContent = `Exactly 3 moves away · maximum 20 moves/model (Claude 5) · zero retries · ${provider.toUpperCase()}`;
}
async function refreshUsage() {
  const bar = $('#budgetbar');
  try {
    const usage = await fetch('/api/usage').then(r => r.json());
    const x = usage.by_model;
    bar.textContent = `PERSISTENT OPENROUTER BUDGET: ${usage.total_used} / ${usage.total_limit} calls · ` +
      `Claude ${x.opus.used}/5 · Jev ${x.jev.used}/20 · Luna ${x.luna.used}/20 · Clef ${x.clef.used}/20 · ` +
      `${usage.cache_entries} cached responses · reported cost $${usage.known_cost_usd.toFixed(5)}`;
  } catch { bar.textContent = 'Cannot read persistent quota database; live run will be blocked.'; }
}
function updateModelCount() {
  const n = document.querySelectorAll('#modellist input:checked').length;
  const all = document.querySelectorAll('#modellist input').length;
  $('#modelcount').textContent = `(${n}/${all})`;
}
function selectedModels() { return [...document.querySelectorAll('#modellist input:checked')].map(i => i.value); }

function buildCards(models) {
  const grid = $('#grid');
  grid.innerHTML = ''; App.cards = {};
  models.forEach(m => { App.cards[m.key] = new Card(m, App.geo, grid); });
}

function showView(v) {
  $('#view-race').hidden = v !== 'race'; $('#view-stats').hidden = v !== 'stats';
  $('#tab-race').classList.toggle('active', v === 'race'); $('#tab-stats').classList.toggle('active', v === 'stats');
}

const SPEEDS = [1, 2.5, 5, 10, 25];
function setSpeed(s) {
  clock.setSpeed(s);
  $('#speedpill').textContent = App.mode === 'replay' ? `▶▶ ${s}x` : (App.mode === 'live' ? 'LIVE' : `▶▶ ${s}x`);
  App.replaySpeed = s;
}
function cycleSpeed() {
  if (App.mode === 'live') return;
  const i = SPEEDS.indexOf(App.replaySpeed || 2.5);
  setSpeed(SPEEDS[(i + 1) % SPEEDS.length]);
}

function setRunning(on) {
  $('#run').hidden = on; $('#stop').hidden = !on; $('#replay').disabled = on;
  ['suite', 'npz', 'seed', 'provider', 'parallel', 'ollama-guided'].forEach(id => { $('#' + id).disabled = on; });
}

/* --------------------------------------------------------------- live run */
async function startLive() {
  showError('');
  const body = {
    suite: $('#suite').value, n_puzzles: +$('#npz').value || 1, models: selectedModels(),
    parallel: $('#parallel').checked, provider: $('#provider').value,
    ollama_guided: $('#provider').value === 'ollama' && $('#ollama-guided').checked,
  };
  if (!body.models.length) { showError('Select at least one model.'); return; }
  if (body.ollama_guided && !confirm('ASSISTED DEMO ONLY: the exact cube solver will reveal distance-reducing moves and can override model choices. Solves will NOT count as independent model successes. Continue?')) return;
  if (body.provider === 'openrouter' && !confirm('This spends your teacher-provided API allowance. The project enforces 65 total calls and 5 Claude calls. Have you tested MOCK and OLLAMA first?')) return;
  const seed = $('#seed').value; if (seed !== '') body.seed = +seed;
  let res;
  try {
    res = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  } catch (e) { showError('Could not reach the backend: ' + e.message); return; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { showError(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)); return; }
  resetSession();
  App.mode = 'live'; setSpeed(1); setRunning(true); showView('race');
  App.runId = data.run_id;
  const my = App.session;
  const es = new EventSource(`/api/run/${data.run_id}/events`);
  App.es = es;
  es.onmessage = m => { if (my !== App.session) return; const ev = JSON.parse(m.data); push(ev, my); if (['run_done', 'run_stopped', 'run_error'].includes(ev.type)) es.close(); };
  es.onerror = () => { /* EventSource reconnects with Last-Event-ID; nothing to do */ };
}

function resetSession() {
  App.session++; App.queue = []; App.draining = false;
  if (App.es) { App.es.close(); App.es = null; }
  App.doneRuns = []; App.runInfo = null; App.finalRun = null;
}

async function stopAll() {
  if (App.mode === 'live' && App.runId) {
    await fetch(`/api/run/${App.runId}/stop`, { method: 'POST' }).catch(() => { });
  } else { App.session++; App.queue = []; endRun(); }
}

/* --------------------------------------------------------------- pipeline */
function push(ev, session) {
  App.queue.push(ev);
  if (!App.draining) drain(session);
}
async function drain(session) {
  App.draining = true;
  while (App.queue.length && session === App.session) {
    const ev = App.queue.shift();
    try { await process(ev, session); } catch (e) { console.error('event error', e, ev); }
  }
  if (session === App.session) App.draining = false;
}

async function process(ev, session) {
  const cards = App.cards;
  switch (ev.type) {
    case 'run_started': {
      App.runInfo = ev; App.totalPuzzles = ev.puzzles.length;
      buildCards(ev.models);
      $('#mockbanner').hidden = !ev.mock;
      $('#localbanner').hidden = ev.request?.provider !== 'ollama';
      if (ev.request?.ollama_guided) $('#localbanner').textContent = 'SOLVER-ASSISTED LOCAL DEMO: reference engine may override model moves. NOT a valid independent model solve benchmark.';
      else $('#localbanner').textContent = 'OLLAMA LOCAL MODE — independent model attempts; no OpenRouter calls.';
      renderPuzzleBar(ev.puzzles, 0, []);
      break;
    }
    case 'puzzle_started': {
      const p = ev.data;
      clock.rebase(0);
      Object.values(cards).forEach(c => {
        c.reset(p.state); c.begin();
        if (App.runInfo?.request?.provider === 'ollama') c.q.distance.hidden = false;
      });
      renderPuzzleInfo(p, ev.total);
      renderPuzzleBar(App.runInfo.puzzles, p.index, App.doneRuns);
      break;
    }
    case 'model_thinking': { cards[ev.model]?.setStatus(cards[ev.model].thinkingWord(), true); break; }
    case 'move': cards[ev.model]?.onMove(ev); break;
    case 'turn_failed': cards[ev.model]?.onFail(ev); break;
    case 'model_done': cards[ev.model]?.finish(ev.result); break;
    case 'puzzle_done': {
      let solvedRank = 0;
      ev.ranking.forEach(k => {
        const r = ev.results.find(x => x.model_key === k);
        if (r?.solved) cards[k]?.setRank(++solvedRank, true);
        else cards[k]?.setRank(0, false);
      });
      App.doneRuns.push(ev.puzzle);
      renderPuzzleBar(App.runInfo.puzzles, 0, App.doneRuns);
      if (session !== App.session) return;
      await sleep(ev.puzzle < App.totalPuzzles ? HOLD_MS : FINAL_HOLD_MS);
      break;
    }
    case 'run_done': await finishRun(ev, session); break;
    case 'run_stopped': endRun('Run stopped.'); if (ev.summary) loadFinalStats(); break;
    case 'run_error': endRun(); showError('Run aborted: ' + ev.message); if (ev.summary) loadFinalStats(); break;
  }
}

function endRun() { App.mode = 'idle'; setRunning(false); setSpeed(App.replaySpeed || 2.5); $('#speedpill').textContent = 'DONE'; }

async function finishRun(ev, session) {
  const wasLive = App.mode === 'live';
  endRun();
  if (wasLive) {
    const run = await fetch(`/api/run/${App.runId}`).then(r => r.json()).catch(() => null);
    if (run) { App.lastRun = run; renderStats(run); }
    await refreshUsage();
  } else if (App.lastRun) { renderStats(App.lastRun); }
  if ($('#autostats').checked && session === App.session) showView('stats');
}
async function loadFinalStats() {
  const run = await fetch(`/api/run/${App.runId}`).then(r => r.json()).catch(() => null);
  if (run && run.results.length) { App.lastRun = run; renderStats(run); }
}

/* ----------------------------------------------------------- puzzle widgets */
function renderPuzzleInfo(p, total) {
  const exact = p.optimal_exact;
  const optimal = exact ? `<b>${p.optimal}</b> moves (exact, breadth-first search)` : `&le; <b>${p.reference_len}</b> moves (scramble length; exact search not run)`;
  $('#puzzleinfo').innerHTML = `Puzzle <b>${p.index} / ${total}</b> &middot; scramble (${p.scramble_len}): <code>${esc(p.scramble.join(' '))}</code> &middot; shortest known solution: ${optimal}`;
}
function renderPuzzleBar(puzzles, active, done) {
  const bar = $('#puzzlebar'); bar.innerHTML = '';
  puzzles.forEach(p => {
    const cls = p.index === active ? 'active' : (done.includes(p.index) ? 'done' : '');
    bar.appendChild(h('span', 'pp ' + cls, `${done.includes(p.index) ? '✓ ' : ''}#${p.index}`));
  });
}

/* ------------------------------------------------------------------ replay */
function rankTrials(trials) {
  const key = t => t.solved ? [0, t.moves_used, t.total_time_s, 0] : [1, -(t.final_correct_facelets || 0), t.total_time_s, t.moves_used];
  return [...trials].sort((a, b) => { const x = key(a), y = key(b); for (let i = 0; i < 4; i++) if (x[i] !== y[i]) return x[i] - y[i]; return 0; }).map(t => t.model_key);
}

async function startReplay() {
  showError('');
  let run = App.lastRun;
  if (!run) run = await fetch('/api/runs/latest').then(r => r.ok ? r.json() : null).catch(() => null);
  if (!run || !run.results || !run.results.length) { showError('No finished run to replay yet - run the benchmark first.'); return; }
  App.lastRun = run;
  resetSession();
  const my = App.session;
  App.mode = 'replay'; setRunning(true); setSpeed(App.replaySpeed || 2.5); showView('race');
  $('#stop').hidden = false;
  $('#mockbanner').hidden = !run.mock;
  $('#localbanner').hidden = run.request?.provider !== 'ollama';
  $('#localbanner').textContent = run.request?.ollama_guided ? 'SOLVER-ASSISTED DEMO — NOT independent model solutions.' : 'OLLAMA LOCAL MODE — independent model attempts.';
  const info = { type: 'run_started', models: run.models, puzzles: run.puzzles, mock: run.mock };
  await process(info, my);
  for (const p of run.puzzles) {
    if (my !== App.session) return;
    await process({ type: 'puzzle_started', data: p, total: run.puzzles.length, puzzle: p.index }, my);
    const results = run.results.filter(r => r.puzzle_index === p.index);
    const sched = [];
    for (const r of results) {
      let prev = 0, used = 0;
      for (const t of r.turn_log) {
        sched.push({ t: prev, ev: { type: 'model_thinking', model: r.model_key, turn: t.turn } });
        if (t.ok) {
          used++;
          sched.push({ t: t.elapsed_s, ev: { type: 'move', model: r.model_key, ...t, state: t.state_after, moves_used: used, solved: r.solved && used === r.moves_used } });
        } else sched.push({ t: t.elapsed_s, ev: { type: 'turn_failed', model: r.model_key, ...t } });
        prev = t.elapsed_s;
      }
      sched.push({ t: r.total_time_s, ev: { type: 'model_done', model: r.model_key, result: r } });
    }
    sched.sort((a, b) => a.t - b.t);
    for (const s of sched) {
      while (clock.now() < s.t) {
        if (my !== App.session) return;
        await sleep(Math.min(60, Math.max(4, (s.t - clock.now()) / clock.speed * 1000)));
      }
      if (my !== App.session) return;
      await process(s.ev, my);
    }
    await process({ type: 'puzzle_done', puzzle: p.index, ranking: rankTrials(results), results }, my);
  }
  if (my === App.session) await process({ type: 'run_done' }, my);
}

/* -------------------------------------------------------------- statistics */
const fmtMs = ms => ms == null ? '—' : (ms < 1000 ? `${ms.toFixed(0)} ms` : `${(ms / 1000).toFixed(2)} s`);
function fmtSecs(s) {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60); return `${m}m ${(s - m * 60).toFixed(0).padStart(2, '0')}s`;
}
const fmtGap = g => g == null ? '—' : (g > 0 ? `+${g.toFixed(2)}` : g.toFixed(2));

function barChart(title, rows, unit, fmt, maxOverride) {
  const max = maxOverride || Math.max(...rows.map(r => r.v ?? 0), 0.0001);
  return `<div class="chart"><h4>${esc(title)}</h4>${rows.map(r => `
    <div class="bar"><span>${esc(r.name)}</span>
      <div class="track"><div class="fill" style="width:${r.v == null ? 0 : Math.max(1.5, 100 * r.v / max)}%;background:${r.color}"></div></div>
      <span class="val">${r.v == null ? '—' : fmt(r.v)}</span></div>`).join('')}</div>`;
}

function renderStats(run) {
  const box = $('#view-stats');
  if (!run || !run.summary || !run.summary.models.length) {
    box.innerHTML = `<div class="slide"><div class="empty-slide"><h2>Benchmark statistics</h2><p>Run the benchmark (or replay a finished run) to see per-model latency, solve time, move counts, success rate and optimality gap.</p></div></div>`;
    return;
  }
  const colors = Object.fromEntries(run.models.map(m => [m.key, m.color]));
  const S = run.summary.models;
  const best = (f, dir) => { const vals = S.map(f).filter(v => v != null); return vals.length ? (dir === 'min' ? Math.min(...vals) : Math.max(...vals)) : null; };
  const bLat = best(s => s.avg_move_latency_ms, 'min'), bTime = best(s => s.total_time_s, 'min'), bMoves = best(s => s.total_moves, 'min');
  const bSucc = best(s => s.success_rate, 'max'), bGap = best(s => s.avg_gap, 'min');
  const cls = (v, b) => v != null && v === b ? 'best' : '';
  const req = run.request || {};
  const nP = run.puzzles.length;
  const gapNote = S.some(s => s.gap_samples > s.gap_exact_samples)
    ? 'Gap = model moves − exact shortest (BFS); where no exact optimum was computed, scramble length is used as an upper bound.'
    : 'Gap = model moves − exact shortest solution (breadth-first search), averaged over the puzzles each model solved.';

  const rows = S.map(s => `<tr>
    <td class="name"><span class="swatch" style="background:${colors[s.key]}"></span>${esc(s.name)}<small>${esc(s.category === 'llm' ? 'Frontier LLM' : 'Decision model')}</small></td>
    <td class="num ${cls(s.avg_move_latency_ms, bLat)}">${fmtMs(s.avg_move_latency_ms)}<small>includes cached turns</small></td>
    <td class="num">${fmtMs(s.avg_live_request_ms)}<small>live HTTP/local only</small></td>
    <td class="num">${s.api_calls || 0} live / ${s.cache_hits || 0} cached<small>${s.local_requests || 0} local Ollama calls</small></td>
    <td class="num ${cls(s.total_time_s, bTime)}">${fmtSecs(s.total_time_s)}<small>avg ${fmtSecs(s.avg_trial_time_s)} / puzzle</small></td>
    <td class="num ${cls(s.total_moves, bMoves)}">${s.total_moves}<small>avg ${s.avg_moves} / puzzle</small></td>
    <td class="num ${cls(s.success_rate, bSucc)}">${s.success_rate == null ? '—' : s.success_rate.toFixed(0) + '%'}<small>${s.solved} / ${s.trials} unassisted; ${s.assisted_solved || 0}/${s.assisted_trials || 0} assisted</small></td>
    <td class="num ${cls(s.avg_gap, bGap)}">${fmtGap(s.avg_gap)}<small>${s.gap_samples ? `${s.optimal_solves} optimal of ${s.solved} solved` : 'no solved puzzles'}</small></td>
    <td class="num">${s.invalid_outputs}<small>${s.retries} retries &middot; ${s.failed_turns} failed turns</small></td>
  </tr>`).join('');

  const A = run.summary.analysis || {};
  const qa = ['q1', 'q2', 'q3', 'q4', 'q5'].filter(k => A[k]).map((k, i) => `
    <div class="q"><b>${i + 1}. ${esc(A[k].question)}</b><p>${esc(A[k].answer)}</p>
    ${A[k].evidence && A[k].evidence.length ? `<ul>${A[k].evidence.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    ${A[k].note ? `<div class="note">${esc(A[k].note)}</div>` : ''}</div>`).join('');

  const modelKeys = run.models.map(m => m.key);
  const trialRows = run.puzzles.map(p => {
    const cells = modelKeys.map(k => {
      const r = run.results.find(x => x.model_key === k && x.puzzle_index === p.index);
      if (!r) return '<td>—</td>';
      const c = r.solved ? 'st-ok' : 'st-bad';
      const pc = r.progress_counts;
      const progressLine = pc ? `<br><span class="distance-summary">↓${pc.closer} closer · ↑${pc.farther} farther · →${pc.same} same · ?${pc.unknown} unknown</span>` : '';
      return `<td><span class="${c}">${r.solved ? (r.assisted_mode ? 'SOLVED · ASSISTED' : 'SOLVED') : (STATUS_TEXT[r.status] || r.status)}</span><br>${r.moves_used} moves${r.gap != null ? ` (gap ${r.gap > 0 ? '+' : ''}${r.gap})` : ''} &middot; ${fmtSecs(r.total_time_s)}${r.invalid_outputs ? `<br><span class="st-warn">${r.invalid_outputs} invalid</span>` : ''}${progressLine}</td>`;
    }).join('');
    return `<tr><td>#${p.index}</td><td><code>${esc(p.scramble.join(' '))}</code></td><td>${p.optimal_exact ? p.optimal : '≤' + p.reference_len}</td>${cells}</tr>`;
  }).join('');

  const rid = run.id;
  const usageHtml = run.mock ? 'Simulated: no real API use.' :
    `Real remote calls: ${run.results.reduce((v, r) => v + (r.api_calls || 0), 0)} · ` +
    `cache hits: ${run.results.reduce((v, r) => v + (r.cache_hits || 0), 0)} · ` +
    `local requests: ${run.results.reduce((v, r) => v + (r.local_requests || 0), 0)} · ` +
    `known cost: $${run.results.reduce((v, r) => v + (r.cost_usd || 0), 0).toFixed(5)} ` +
    `(unreported usage may have additional cost)`;
  box.innerHTML = `<div class="slide">
    <h2>Statistical benchmark</h2>
    <div class="sub">${usageHtml} · Live network and cache timings are stored separately in the CSV files. Cached timings must not be compared as live model speed.</div>
    ${req.provider === 'ollama' ? '<div class="sub">Ollama move diagnostics: green means the exact shortest distance decreased, red increased, grey was unchanged. Distance is verified by bounded BFS through 7 turns; >7 means exact distance is unknown. The distance oracle is never shown to the AI models.</div>' : ''}
    <div class="sub">${nP} puzzles &middot; ${esc(req.suite || '')} suite &middot; seed ${esc(req.seed)} &middot; move limit ${run.limits.max_moves} &middot; time limit ${run.limits.time_limit_s}s${run.mock ? ' &middot; <b class="st-bad">MOCK DATA - not real results</b>' : ''}</div>
    <table class="stats">
      <thead><tr><th>Model</th><th>Observed avg / move</th><th>Live request latency</th><th>Real calls / cache</th><th>Total solve time</th><th>Total moves</th><th>Success rate</th><th>Optimal gap</th><th>Invalid outputs</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="sub" style="margin-top:8px">${gapNote} Green = best in column. Total time / moves are summed over all ${nP} puzzles (unsolved runs count their full time and moves).</div>
    <h3>At a glance</h3>
    <div class="charts">
      ${barChart('Live inference latency (cache hits excluded)', S.map(s => ({ name: s.name, v: s.avg_live_request_ms, color: colors[s.key] })), 'ms', fmtMs)}
      ${barChart('Success rate (higher is better)', S.map(s => ({ name: s.name, v: s.success_rate, color: colors[s.key] })), '%', v => v.toFixed(0) + '%', 100)}
      ${barChart('Optimal gap, moves above shortest (lower is better)', S.map(s => ({ name: s.name, v: s.avg_gap, color: colors[s.key] })), '', v => fmtGap(v))}
    </div>
    <h3>The five questions</h3>
    <div class="qa">${qa}</div>
    <details class="trials"><summary>Per-puzzle results (${run.results.length} trials)</summary>
      <table class="trial"><thead><tr><th>#</th><th>Scramble</th><th>Optimal</th>${run.models.map(m => `<th>${esc(m.name)}</th>`).join('')}</tr></thead><tbody>${trialRows}</tbody></table></details>
    <div class="exports"><a href="/api/run/${rid}/trials.csv" download="trials-${rid}.csv">&#8681; Trials CSV</a><a href="/api/run/${rid}/moves.csv" download="moves-${rid}.csv">&#8681; Per-move log CSV</a><span class="sub" style="margin:8px 0 0">Full JSON saved in <code>results/</code></span></div>
  </div>`;
}

init().catch(e => showError('Failed to initialise UI: ' + e.message));
