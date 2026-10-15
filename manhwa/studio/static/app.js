'use strict';
// Manhwa Studio : bibliothèque (séries → épisodes) et écran Découpe.

const STRIP_W = 380; // largeur d'affichage du strip, comme #strip dans app.css
const STEP_NAMES = ['Pages', 'Découpe', 'Texte', 'Voix', 'Vidéo'];
const JOB_STEPS = [
  ['frames', 'Frames 9:16'],
  ['ocr', 'Lecture du texte'],
  ['tts', 'Voix'],
  ['render', 'Rendu vidéo'],
];
const TALL_DOUBT = 2.5; // une case de plus de 2,5 écrans cache sans doute une coupe

const ICONS = {
  sparkles: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z',
  play: 'M7 4l12 8-12 8z',
  reset: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  check: 'M20 6 9 17l-5-5',
  alert: 'M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  down: 'M12 5v14M19 12l-7 7-7-7',
  scissors: 'M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z',
};

/* ---------- Outils ---------- */

const $ = (sel, root = document) => root.querySelector(sel);
const enc = encodeURIComponent;
const fmt = (n) => n.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'class') node.className = value;
    else if (key === 'style') node.style.cssText = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...children.flat().filter((c) => c != null && c !== false));
  return node;
}

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name]);
  svg.append(path);
  return svg;
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).detail || message;
    } catch {}
    throw new Error(message);
  }
  return res.json();
}

let toastTimer;
function toast(message, action) {
  const box = $('#toast');
  box.replaceChildren(el('span', { text: message }), action && el('button', { type: 'button', text: action.label, onclick: () => { box.hidden = true; action.run(); } }));
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (box.hidden = true), 4500);
}

/* ---------- État ---------- */

const state = {
  library: null,
  current: null, // id du chapitre ouvert
  chapter: null, // détail renvoyé par /api/chapter
  cuts: [],
  panels: [],
  reviewed: false,
  undo: [],
  drag: null,
  doubt: -1,
};

const isRunning = (job) => job && (job.status === 'queued' || job.status === 'running');
const scale = () => STRIP_W / state.chapter.width;

/* ---------- Bibliothèque ---------- */

function renderLibrary() {
  const lib = state.library;
  const nav = $('#library');
  if (!lib) return;
  const episodes = lib.series.reduce((n, s) => n + s.chapters.length, 0);
  $('#brand-sub').textContent = episodes ? `${plural(lib.series.length, 'série', 'séries')} · ${plural(episodes, 'épisode', 'épisodes')}` : 'Inbox vide';
  nav.replaceChildren(
    ...lib.series.map((s) =>
      el(
        'section',
        { class: 'series' },
        el(
          'div',
          { class: 'series-head' },
          el('div', { class: 'line' }, el('span', { text: s.name }), el('span', { class: 'count', text: `${Math.round((100 * s.done) / s.total)} %` })),
          el('div', { class: 'bar' }, el('span', { style: `width:${(100 * s.done) / s.total}%` })),
        ),
        s.chapters.map(episodeRow),
      ),
    ),
  );
}

function jobProgressIndex(job) {
  // étape du travail en cours → case de la barre (frames = découpe, ocr = texte…)
  return JOB_STEPS.findIndex(([step]) => step === job.step) + 1;
}

function episodeRow(c) {
  const p = c.progress;
  const running = isRunning(c.job);
  const runningAt = running ? Math.max(1, jobProgressIndex(c.job)) : -1;
  let status;
  if (running) status = el('span', { class: 'spinner' });
  else if (c.job && c.job.status === 'error') status = el('span', { class: 'state', text: 'Erreur' });
  else if (p.done === p.total) status = el('span', { class: 'state' }, icon('check'));
  else status = el('span', { class: 'state', text: STEP_NAMES[p.done] });
  return el(
    'button',
    { type: 'button', class: `episode${c.id === state.current ? ' on' : ''}`, onclick: () => openChapter(c.id) },
    el('div', { class: 'line' }, el('span', { class: 'name', text: c.name.replace('chapter-', 'Épisode ') }), status),
    el('div', { class: 'steps' }, STEP_NAMES.map((_, i) => el('i', { class: i === runningAt ? 'running' : i < p.done ? 'on' : '' }))),
  );
}

function findEpisode(id) {
  for (const s of state.library?.series || []) for (const c of s.chapters) if (c.id === id) return c;
  return null;
}

/* ---------- Accueil ---------- */

function renderHome() {
  const empty = !state.library || !state.library.series.length;
  $('#view').replaceChildren(
    el(
      'div',
      { class: 'empty-state' },
      el('span', { class: 'logo' }, icon(empty ? 'inbox' : 'sparkles')),
      el('h2', { text: empty ? 'Ton inbox est vide' : 'Choisis un épisode' }),
      empty
        ? el('p', {}, 'Télécharge un chapitre avec ', el('code', { text: 'python -m manhwa download <url>' }), el('br'), 'ou dépose des images dans ', el('code', { text: 'inbox/<série>/<chapitre>/' }), '.')
        : el('p', { text: 'La découpe est déjà proposée : tu n’as qu’à vérifier.' }),
    ),
  );
}

/* ---------- Chapitre : écran Découpe ---------- */

async function openChapter(id) {
  state.current = id;
  history.replaceState(null, '', `#${enc(id)}`);
  renderLibrary();
  $('#view').replaceChildren(el('div', { class: 'skeleton' }), el('p', { class: 'loading-label', text: 'Analyse du chapitre… les cases se découpent.' }));
  try {
    const ch = await api(`/api/chapter?id=${enc(id)}`);
    if (state.current !== id) return;
    loadChapter(ch);
    renderChapter(true);
    $('main').scrollTop = 0;
  } catch (e) {
    $('#view').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Impossible d’ouvrir ce chapitre : ${e.message}` })));
  }
}

function loadChapter(ch) {
  state.chapter = ch;
  state.cuts = ch.cuts.map((c) => ({ ...c }));
  state.panels = ch.panels;
  state.reviewed = !!ch.reviewed;
  state.undo = [];
  state.doubt = -1;
}

function doubts() {
  const list = state.cuts.filter((c) => !c.sure).map((c) => ({ y: c.y, kind: 'cut' }));
  if (!state.reviewed) {
    for (const p of state.panels) if (p.screens > TALL_DOUBT) list.push({ y: Math.round((p.y0 + p.y1) / 2), kind: 'tall' });
  }
  return list.sort((a, b) => a.y - b.y);
}

function renderChapter(intro = false) {
  const ch = state.chapter;
  const H = ch.height * scale();
  const strip = el('div', { id: 'strip', class: intro ? 'intro' : '', style: `height:${H}px`, onclick: onStripClick, onpointerdown: onPointerDown });
  const rows = ch.tiles.rows;
  for (let i = 0; i < ch.tiles.count; i++) {
    const h = Math.min(rows, ch.height - i * rows) * scale();
    strip.append(el('img', { src: `/api/tile?id=${enc(ch.id)}&i=${i}`, loading: 'lazy', decoding: 'async', alt: '', style: `top:${i * rows * scale()}px;height:${h}px` }));
  }
  const notice = ch.manual_frames
    ? el('div', { class: 'notice' }, icon('alert'), el('p', { text: `Ce chapitre a ${ch.manual_frames} frames faites à la main. « Créer la vidéo » les remplacera par cette découpe.` }))
    : null;
  $('#view').replaceChildren(
    ...[el('div', { class: 'head', id: 'head' }), notice, el('div', { class: 'workspace' }, el('div', {}, strip), el('div', { class: 'side', id: 'side' }))].filter(Boolean),
  );
  renderHead();
  renderOverlays();
  renderSide();
  if (intro) setTimeout(() => $('#strip')?.classList.remove('intro'), 2500);
}

function renderHead() {
  const ch = state.chapter;
  const n = doubts().length;
  const job = findEpisode(ch.id)?.job || ch.job;
  const running = isRunning(job);
  $('#head').replaceChildren(
    el(
      'div',
      { class: 'titles' },
      el('h2', { text: `${ch.series} · ${ch.name.replace('chapter-', 'Épisode ')}` }),
      el('p', { text: `${plural(state.panels.length, 'case', 'cases')} · ${plural(state.cuts.length, 'coupe', 'coupes')} · ${state.undo.length || ch.edited ? 'découpe retouchée' : 'découpe automatique'}` }),
    ),
    el(
      'div',
      { class: 'actions' },
      n ? el('button', { type: 'button', class: 'pill warn', onclick: nextDoubt }, icon('down'), `${n} à vérifier`) : null,
      el('button', { type: 'button', class: 'pill', title: 'Revenir à la découpe automatique', onclick: resetCuts }, icon('reset'), 'Auto'),
      el('button', { type: 'button', class: 'pill accent', disabled: running, onclick: makeVideo }, running ? el('span', { class: 'spinner light' }) : icon('play'), running ? 'En cours…' : 'Créer la vidéo'),
    ),
  );
}

function renderOverlays() {
  const strip = $('#strip');
  if (!strip) return;
  strip.querySelectorAll('.panel, .cut').forEach((n) => n.remove());
  const s = scale();
  state.panels.forEach((p, i) => {
    const tall = p.screens > 1.25;
    strip.append(
      el(
        'div',
        { class: 'panel', style: `top:${p.y0 * s}px;height:${(p.y1 - p.y0) * s}px`, onmouseenter: () => showPreview(i) },
        el('span', { class: `badge${p.screens > TALL_DOUBT && !state.reviewed ? ' tall' : ''}`, text: tall ? `${i + 1} · ${fmt(p.screens)} écrans` : `${i + 1}` }),
      ),
    );
  });
  state.cuts.forEach((c, i) => strip.append(el('div', { class: `cut${c.sure ? '' : ' doubt'}`, style: `top:${c.y * s}px;--i:${i}`, 'data-i': i })));
}

function renderSide() {
  const side = $('#side');
  if (!side) return;
  const ch = state.chapter;
  const ep = findEpisode(ch.id);
  const job = ep?.job || ch.job;
  const progress = ep?.progress || ch.progress;
  const n = doubts().length;
  const cards = [];

  if (job && (isRunning(job) || job.status === 'error')) cards.push(jobCard(job));

  cards.push(
    el(
      'div',
      { class: 'card' },
      el('h3', { text: 'Aperçu' }),
      el('div', { class: 'frame', id: 'preview' }, el('div', { class: 'empty', text: 'Survole une case pour voir sa frame 9:16.' })),
      el('p', { class: 'caption', id: 'preview-caption', text: ' ' }),
    ),
  );

  if (n) {
    cards.push(
      el(
        'div',
        { class: 'card' },
        el('h3', { text: `${plural(n, 'endroit', 'endroits')} à vérifier` }),
        el('p', { class: 'muted', text: 'Lignes en pointillés : coupe incertaine. Badge orange : case très haute, il manque peut-être une coupe.' }),
        el('div', { class: 'actions', style: 'margin-top:10px' }, el('button', { type: 'button', class: 'pill', onclick: nextDoubt }, icon('down'), 'Suivant'), el('button', { type: 'button', class: 'pill', onclick: acceptAll }, icon('check'), 'Tout est bon')),
      ),
    );
  }

  if (!isRunning(job) && progress.done === progress.total) {
    cards.push(
      el('div', { class: 'card' }, el('h3', { text: 'Vidéo prête' }), el('div', { class: 'frame' }, el('video', { src: `/api/video?id=${enc(ch.id)}&v=${Date.now()}`, controls: true, preload: 'metadata' }))),
    );
  }

  cards.push(
    el(
      'div',
      { class: 'card' },
      el('h3', { text: 'Gestes' }),
      el(
        'ul',
        { class: 'gestures' },
        el('li', {}, el('b', { text: 'Clic sur une ligne' }), el('span', { class: 'muted', text: 'la supprimer' })),
        el('li', {}, el('b', { text: 'Clic sur une case' }), el('span', { class: 'muted', text: 'couper ici (aimanté sur la marge la plus proche)' })),
        el('li', {}, el('b', { text: 'Glisser une ligne' }), el('span', { class: 'muted', text: 'l’ajuster' })),
        el('li', {}, el('b', { text: 'Ctrl+Z' }), el('span', { class: 'muted', text: 'annuler' })),
      ),
    ),
  );
  side.replaceChildren(...cards);
}

function jobCard(job) {
  const at = JOB_STEPS.findIndex(([step]) => step === job.step);
  return el(
    'div',
    { class: 'card' },
    el('div', { class: 'job' }, job.status === 'error' ? icon('alert') : el('span', { class: 'spinner' }), job.status === 'error' ? 'Erreur' : job.status === 'queued' ? 'En attente…' : `${job.label}…`),
    job.error ? el('p', { class: 'muted', style: 'margin-top:6px', text: job.error }) : null,
    el(
      'div',
      { class: 'job-steps' },
      JOB_STEPS.map(([, label], i) => {
        const done = at > i;
        const on = at === i && job.status === 'running';
        return el('div', { class: done ? 'done' : on ? 'on' : '' }, done ? icon('check') : on ? el('span', { class: 'spinner' }) : el('span', { class: 'dot' }), label);
      }),
    ),
  );
}

/* ---------- Aperçu ---------- */

let previewTimer;
function showPreview(i) {
  clearTimeout(previewTimer);
  document.querySelectorAll('.panel.on').forEach((n) => n.classList.remove('on'));
  document.querySelectorAll('.panel')[i]?.classList.add('on');
  previewTimer = setTimeout(() => {
    const p = state.panels[i];
    if (!p) return;
    const img = el('img', { src: `/api/preview?id=${enc(state.chapter.id)}&y0=${p.y0}&y1=${p.y1}`, alt: '' });
    $('#preview')?.replaceChildren(img);
    const caption = $('#preview-caption');
    if (caption) caption.textContent = `Case ${i + 1} · ${fmt(p.screens)} écran${p.screens >= 2 ? 's' : ''}${p.screens > 1.25 ? ' · coupée en plusieurs frames' : ''}`;
  }, 90);
}

/* ---------- Gestes sur les coupes ---------- */

function stripY(event) {
  const rect = $('#strip').getBoundingClientRect();
  return Math.round((event.clientY - rect.top) / scale());
}

function snapY(y) {
  const radius = state.chapter.width * 0.08;
  let best = y;
  let bestDist = radius + 1;
  for (const g of state.chapter.gutters) {
    const dist = y >= g.y0 && y < g.y1 ? 0 : Math.min(Math.abs(y - g.y0), Math.abs(y - g.y1));
    if (dist < bestDist) {
      best = Math.round((g.y0 + g.y1) / 2);
      bestDist = dist;
    }
  }
  return best;
}

function onPointerDown(event) {
  const line = event.target.closest('.cut');
  if (!line) return;
  event.preventDefault();
  const i = Number(line.dataset.i);
  state.drag = { i, line, startClient: event.clientY, startY: state.cuts[i].y, y: state.cuts[i].y, moved: false };
  line.classList.add('dragging');
  line.setPointerCapture(event.pointerId);
  line.addEventListener('pointermove', onPointerMove);
  line.addEventListener('pointerup', onPointerUp, { once: true });
}

function onPointerMove(event) {
  const d = state.drag;
  if (!d) return;
  if (Math.abs(event.clientY - d.startClient) > 3) d.moved = true;
  d.y = Math.min(state.chapter.height - 1, Math.max(1, Math.round(d.startY + (event.clientY - d.startClient) / scale())));
  d.line.style.top = `${d.y * scale()}px`;
}

function onPointerUp() {
  const d = state.drag;
  state.drag = null;
  if (!d) return;
  d.line.removeEventListener('pointermove', onPointerMove);
  d.line.classList.remove('dragging');
  d.justDragged = true;
  if (!d.moved) {
    commit(state.cuts.filter((_, j) => j !== d.i), 'Coupe supprimée');
  } else {
    commit(state.cuts.map((c, j) => (j === d.i ? { y: snapY(d.y), sure: true } : c)), 'Coupe déplacée');
  }
  // le clic qui suit le relâchement ne doit pas ajouter de coupe
  state.ignoreClickUntil = Date.now() + 250;
}

function onStripClick(event) {
  if (event.target.closest('.cut') || Date.now() < (state.ignoreClickUntil || 0)) return;
  const y = snapY(stripY(event));
  if (state.cuts.some((c) => Math.abs(c.y - y) < 4)) return;
  commit([...state.cuts, { y, sure: true }], 'Coupe ajoutée');
}

function commit(cuts, message) {
  state.undo.push({ cuts: state.cuts, reviewed: state.reviewed });
  state.cuts = cuts.sort((a, b) => a.y - b.y);
  state.panels = localPanels();
  renderOverlays();
  renderHead();
  renderSide();
  scheduleSave();
  if (message) toast(message, { label: 'Annuler', run: undo });
}

function localPanels() {
  // affichage immédiat entre les coupes ; le serveur renvoie ensuite les cases sans leurs marges
  const ys = [0, ...state.cuts.map((c) => c.y), state.chapter.height];
  const screen = state.chapter.screen;
  return ys.slice(0, -1).map((y0, i) => ({ y0, y1: ys[i + 1], screens: Math.round(((ys[i + 1] - y0) / screen) * 100) / 100 }));
}

function undo() {
  const previous = state.undo.pop();
  if (!previous) return;
  state.cuts = previous.cuts;
  state.reviewed = previous.reviewed;
  state.panels = localPanels();
  renderOverlays();
  renderHead();
  renderSide();
  scheduleSave();
}

let saveTimer;
let saving = Promise.resolve();
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 300);
}

function saveNow() {
  clearTimeout(saveTimer);
  const id = state.chapter.id;
  const body = JSON.stringify({ cuts: state.cuts, reviewed: state.reviewed });
  saving = saving
    .then(() => api(`/api/cuts?id=${enc(id)}`, { method: 'PUT', body }))
    .then((res) => {
      if (state.chapter?.id !== id) return;
      state.panels = res.panels;
      state.chapter.edited = true;
      renderOverlays();
      renderHead();
    })
    .catch((e) => toast(`Sauvegarde impossible : ${e.message}`));
  return saving;
}

function nextDoubt() {
  const list = doubts();
  if (!list.length) return;
  state.doubt = (state.doubt + 1) % list.length;
  const target = list[state.doubt];
  const strip = $('#strip');
  const main = $('main');
  const top = strip.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop + target.y * scale();
  main.scrollTo({ top: top - main.clientHeight / 2, behavior: 'smooth' });
  if (target.kind === 'cut') {
    const i = state.cuts.findIndex((c) => c.y === target.y);
    const line = strip.querySelector(`.cut[data-i="${i}"]`);
    line?.classList.remove('focus');
    void line?.offsetWidth;
    line?.classList.add('focus');
  }
}

function acceptAll() {
  const cuts = state.cuts.map((c) => ({ ...c, sure: true }));
  state.undo.push({ cuts: state.cuts, reviewed: state.reviewed });
  state.cuts = cuts;
  state.reviewed = true;
  renderOverlays();
  renderHead();
  renderSide();
  scheduleSave();
  toast('Découpe validée', { label: 'Annuler', run: undo });
}

async function resetCuts() {
  const before = { cuts: state.cuts, reviewed: state.reviewed };
  await saveNow();
  try {
    const ch = await api(`/api/cuts/reset?id=${enc(state.chapter.id)}`, { method: 'POST' });
    loadChapter(ch);
    state.undo = [before];
    renderChapter(true);
    toast('Découpe automatique restaurée', { label: 'Annuler', run: undo });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function makeVideo() {
  const ch = state.chapter;
  if (ch.manual_frames && !confirm(`Remplacer les ${ch.manual_frames} frames faites à la main par cette découpe ?`)) return;
  await saveNow();
  try {
    const job = await api(`/api/make?id=${enc(ch.id)}`, { method: 'POST' });
    ch.job = job;
    ch.manual_frames = 0;
    const ep = findEpisode(ch.id);
    if (ep) ep.job = job;
    renderHead();
    renderSide();
    renderLibrary();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible de lancer la vidéo : ${e.message}`);
  }
}

/* ---------- Mise à jour en direct ---------- */

let pollTimer;
function schedulePoll(delay) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, delay);
}

async function poll() {
  try {
    const before = findEpisode(state.current)?.job;
    state.library = await api('/api/library');
    renderLibrary();
    const after = findEpisode(state.current)?.job;
    if (state.chapter && JSON.stringify(before) !== JSON.stringify(after)) {
      renderHead();
      renderSide();
    }
  } catch {}
  const busy = state.library?.series.some((s) => s.chapters.some((c) => isRunning(c.job)));
  schedulePoll(busy ? 1500 : 10000);
}

document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && state.chapter) {
    event.preventDefault();
    undo();
  }
});

window.addEventListener('hashchange', () => {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && id !== state.current && findEpisode(id)) openChapter(id);
});

for (const slot of document.querySelectorAll('[data-icon]')) slot.replaceChildren(icon(slot.dataset.icon));

(async function start() {
  try {
    state.library = await api('/api/library');
  } catch (e) {
    $('#view').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Serveur injoignable : ${e.message}` })));
    return;
  }
  renderLibrary();
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && findEpisode(id)) openChapter(id);
  else renderHome();
  schedulePoll(10000);
})();
