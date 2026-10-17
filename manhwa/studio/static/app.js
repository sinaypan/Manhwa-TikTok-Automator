'use strict';
// Manhwa Studio : bibliothèque (séries → épisodes), écrans Découpe et Personnages.

const STRIP_W = 380; // largeur d'affichage du strip, comme #strip dans app.css
const STEP_NAMES = ['Pages', 'Découpe', 'Texte', 'Voix', 'Vidéo'];
const JOB_STEPS = [
  ['frames', 'Frames 9:16'],
  ['ocr', 'Lecture du texte'],
  ['textfix', 'Correction du texte'],
  ['tts', 'Voix'],
  ['render', 'Rendu vidéo'],
  ['listen', 'Réécoute de la voix'],
];
// étape d'un travail → case de la barre d'avancement (Pages, Découpe, Texte, Voix, Vidéo)
const STEP_BAR = { frames: 1, ocr: 2, textfix: 2, faces: 2, scene: 2, describe: 2, places: 2, wiki: 2, review: 2, voices: 2, sounds: 2, pilot: 2, tts: 3, render: 4, listen: 4, parts: 4 };
const KIND_STEPS = {
  faces: [['faces', 'Recherche des visages']],
  wiki: [['wiki', 'Lecture du wiki']],
  wiki_images: [
    ['wiki_images', 'Images du wiki'],
    ['wiki_faces', 'Visages du wiki'],
  ],
};
KIND_STEPS.review = [['review', 'Relecture GPT']];
KIND_STEPS.voices = [['voices', 'Choix des voix']];
KIND_STEPS.sounds = [['sounds', 'Choix des sons (GPT)']];
KIND_STEPS.understand = [
  ['scene', 'Ce que montrent les cases'],
  ['describe', 'Ce qui se passe dans les cases'],
  ['sounds', 'Choix des sons (GPT)'],
  ['places', 'Lieux et ambiances'],
];
KIND_STEPS.scene = [['scene', 'Ce que montrent les cases']];
const AUTO_STEPS = [
  ['frames', 'Frames 9:16'],
  ['ocr', 'Lecture du texte'],
  ['textfix', 'Correction du texte'],
  ['faces', 'Visages'],
  ['scene', 'Ce que montrent les cases'],
  ['describe', 'Ce qui se passe dans les cases'],
  ['wiki', 'Wiki'],
  ['review', 'Relecture GPT'],
  ['voices', 'Choix des voix'],
  ['sounds', 'Sons'],
  ['places', 'Lieux et ambiances'],
  ['pilot', 'Pilote automatique'],
  ['tts', 'Voix'],
  ['render', 'Rendu vidéo'],
  ['listen', 'Réécoute de la voix'],
  ['parts', 'Parties pour TikTok'],
];
KIND_STEPS.listen = [['listen', 'Réécoute de la voix']];
KIND_STEPS.parts = [['parts', 'Découpe en parties']];
const KIND_TITLES = { auto: 'Tout faire', faces: 'Recherche des personnages', wiki: 'Lecture du wiki', wiki_images: 'Images du wiki', review: 'Relecture par GPT', voices: 'Choix des voix par GPT', sounds: 'Sons proposés par GPT', scene: 'Ce que montrent les cases', understand: 'Comprendre les cases' };
const SCREENS = [
  ['cut', 'Découpe'],
  ['cast', 'Personnages'],
  ['review', 'Relecture'],
  ['sounds', 'Sons'],
  ['video', 'Vidéo'],
];
const SCREEN_HASH = { cast: 'personnages', review: 'relecture', sounds: 'sons', video: 'video' };
const TALL_DOUBT = 2; // une case de plus de 2 écrans cache sans doute une coupe

const ICONS = {
  sparkles: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z',
  play: 'M7 4l12 8-12 8z',
  reset: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  check: 'M20 6 9 17l-5-5',
  alert: 'M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  down: 'M12 5v14M19 12l-7 7-7-7',
  scissors: 'M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  plus: 'M12 5v14M5 12h14',
  x: 'M18 6 6 18M6 6l12 12',
  edit: 'M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
};

/* ---------- Outils ---------- */

const $ = (sel, root = document) => root.querySelector(sel);
// replaceChildren écrit « null » pour un enfant vide : on les retire d'abord
const fill = (node, ...children) => node.replaceChildren(...children.flat(Infinity).filter((c) => c != null && c !== false));
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
  node.append(...children.flat(Infinity).filter((c) => c != null && c !== false));
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

/* ---------- À faire, puis déjà fait : ce qu'on vient de décider reste quelques secondes (on peut changer
   d'avis), puis se range tout en bas ; la suivante prend sa place, sans avoir à défiler ---------- */

const settleTimers = new Map(); // clé → { stop }
const SETTLE = 2; // secondes avant qu'une ligne décidée se range
const pointer = { x: -1, y: -1 };
let lastPress = null; // le bouton qu'on vient de cliquer : la suivante le mettra sous la souris

document.addEventListener('pointermove', (e) => Object.assign(pointer, { x: e.clientX, y: e.clientY }), { passive: true });
document.addEventListener('pointerdown', (e) => {
  Object.assign(pointer, { x: e.clientX, y: e.clientY });
  const hit = e.target.closest?.('button, textarea, select');
  const row = hit?.closest('[data-key]');
  if (!row) return (lastPress = null);
  const r = hit.getBoundingClientRect();
  lastPress = { key: row.dataset.key, tag: hit.tagName, label: hit.tagName === 'BUTTON' ? hit.textContent.trim() : hit.className, dy: e.clientY - r.top };
}, true);

function sameControl(row, press) {
  return [...row.querySelectorAll(press.tag)].find((b) => (press.tag === 'BUTTON' ? b.textContent.trim() : b.className) === press.label);
}

function alignUnderPointer(key, press) {
  // la ligne suivante : son bouton « C'est bon » (ou le même nom, le même champ) vient sous la souris
  const row = document.querySelector(`.queue > [data-key="${CSS.escape(key)}"]`);
  const same = row && sameControl(row, press);
  if (!same) return;
  const r = same.getBoundingClientRect();
  $('main')?.scrollBy(0, r.top + Math.min(press.dy, r.height - 2) - pointer.y);
}

function settle(key, seconds, done, { collapse = true } = {}) {
  unsettle(key);
  const find = () => document.querySelector(`.queue > [data-key="${CSS.escape(key)}"]`);
  const row = find();
  if (!row) return;
  row.style.setProperty('--settle', `${seconds}s`);
  row.classList.remove('settling', 'held');
  void row.offsetWidth;
  row.classList.add('settling');
  const press = lastPress?.key === key ? lastPress : null;
  // la souris qui bouge sur la ligne la retient (on relit, on corrige) ; immobile sur le bouton, elle part
  const origin = { ...pointer };
  const ac = new AbortController();
  let left = seconds * 1000;
  let start = 0;
  let timer = null;
  const run = () => {
    row.classList.remove('held');
    start = performance.now();
    timer = setTimeout(finish, left);
  };
  const hold = () => {
    if (timer == null) return;
    clearTimeout(timer);
    timer = null;
    left = Math.max(1000, left - (performance.now() - start));
    row.classList.add('held');
  };
  const finish = () => {
    unsettle(key);
    const live = find();
    if (!live || !collapse) return done();
    const next = live.nextElementSibling?.dataset.key || live.previousElementSibling?.dataset.key;
    const queue = live.closest('.queue');
    const aim = press && next && queue?.contains(document.elementFromPoint(pointer.x, pointer.y)) ? press : null;
    live.style.height = `${live.offsetHeight}px`;
    void live.offsetWidth;
    live.classList.add('leaving');
    setTimeout(() => {
      done();
      if (aim) alignUnderPointer(next, aim);
    }, 300);
  };
  row.addEventListener('pointermove', (e) => {
    if (Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > 12) hold();
  }, { signal: ac.signal });
  row.addEventListener('pointerleave', () => timer == null && run(), { signal: ac.signal });
  row.addEventListener('focusin', (e) => e.target.matches('textarea, select') && hold(), { signal: ac.signal });
  settleTimers.set(key, { stop: () => (clearTimeout(timer), ac.abort()) });
  run();
}

function unsettle(key) {
  settleTimers.get(key)?.stop();
  settleTimers.delete(key);
}

function doneList(id, title, rows) {
  return el(
    'details',
    { class: 'done-list', id, open: state.openDone.has(id), hidden: !rows.length, ontoggle: (e) => (e.currentTarget.open ? state.openDone.add(id) : state.openDone.delete(id)) },
    el('summary', {}, icon('check'), title, el('span', { class: 'muted', text: ' · cliquer pour voir ou changer d’avis' })),
    el('div', { class: 'lines' }, rows),
  );
}

function afterSettle(key, fresh) {
  // la ligne quitte la file ; compteurs et liste du bas sont refaits (pas la file : rien ne saute)
  const old = document.getElementById(fresh.id);
  if (!old) return;
  old.querySelector(`.queue > [data-key="${CSS.escape(key)}"]`)?.remove();
  for (const sel of ['.block-head', '.bar', '.done-list']) {
    const a = old.querySelector(sel);
    const b = fresh.querySelector(sel);
    if (a && b) a.replaceWith(b);
  }
  const queue = old.querySelector('.queue');
  if (queue && !queue.children.length) queue.replaceWith(fresh.querySelector('.queue-empty') || el('div'));
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
  screen: 'cut', // 'cut' (Découpe) ou 'cast' (Personnages)
  cast: null, // détail renvoyé par /api/cast
  sel: new Set(), // visages sélectionnés (à ranger)
  pendingKeys: new Set(), // répliques encore à valider (une validée y reste 2 s, puis se range en bas)
  soundKeys: new Set(), // sons encore à choisir (même principe)
  soundFocus: null, // la case affichée en grand dans Sons (sinon la première à choisir)
  soundLib: false, // « Tous les sons… » ouvert
  openDone: new Set(), // listes « déjà faits » et blocs repliables ouverts
  openFaces: new Set(), // personnages dont on voit tous les visages
  autoScene: new Set(), // chapitres dont on a déjà lancé « ce que montrent les cases » tout seul
  editing: null, // relecture : la proposition que l'on corrige soi-même
  reviewRecent: [], // relecture : les dernières décisions (en tête de « Déjà décidées »)
  reviewInflight: 0,
  reviewMode: 'proposals', // relecture : 'proposals' (ce que GPT ou la correction locale propose) ou 'all' (toutes les bulles)
  bubbles: null, // toutes les bulles du chapitre (mode 'all')
  bubbleKeys: new Set(), // bulles encore à vérifier
  autoAnalyzed: new Set(), // chapitres dont on a déjà lancé la recherche de visages tout seul
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
    ...[el('button', { type: 'button', class: 'add-btn', onclick: openImport }, icon('plus'), 'Ajouter des chapitres'), importCard()].filter(Boolean),
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
  if (KIND_STEPS[job.kind]) return -1; // personnages et wiki ne font pas partie des 5 étapes
  return STEP_BAR[job.step] ?? 0;
}

function episodeRow(c) {
  const p = c.progress;
  const running = isRunning(c.job);
  const at = running ? jobProgressIndex(c.job) : -1;
  const runningAt = at < 0 ? -1 : Math.max(1, at);
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

function setHash() {
  const suffix = SCREEN_HASH[state.screen];
  history.replaceState(null, '', `#${enc(state.current)}${suffix ? `/${suffix}` : ''}`);
}

function parseHash() {
  // « #Série%2Fchapter-001 », « …/personnages » ou « …/relecture »
  const [raw, suffix] = location.hash.slice(1).split('/');
  const screen = Object.keys(SCREEN_HASH).find((k) => SCREEN_HASH[k] === suffix) || 'cut';
  return { id: decodeURIComponent(raw || ''), screen };
}

async function openChapter(id, screen = 'cut') {
  state.current = id;
  state.screen = screen;
  setHash();
  renderLibrary();
  $('#view').replaceChildren(el('div', { class: 'skeleton' }), el('p', { class: 'loading-label', text: 'Analyse du chapitre… les cases se découpent.' }));
  try {
    const ch = await api(`/api/chapter?id=${enc(id)}`);
    if (state.current !== id) return;
    loadChapter(ch);
    if (state.screen === 'cast') openCast();
    else if (state.screen === 'review') openReview();
    else if (state.screen === 'sounds') openSounds();
    else if (state.screen === 'video') openVideo();
    else renderChapter(true);
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
  state.checked = ch.checked || []; // cases hautes déjà vérifiées (début de la case)
  state.confirmed = true; // state.panels vient du serveur (marges retirées)
  state.undo = [];
  state.doubt = -1;
}

const isChecked = (p) => state.checked.some((y) => Math.abs(y - p.y0) < 40);

function doubts() {
  const list = state.cuts.filter((c) => !c.sure).map((c) => ({ y: c.y, kind: 'cut' }));
  // les cases très hautes ne comptent que sur les vraies cases renvoyées par le serveur : la découpe
  // provisoire (affichée juste après un clic) garde les marges blanches et grossit les cases
  if (!state.reviewed && state.confirmed) {
    for (const p of state.panels) {
      if (p.screens > TALL_DOUBT && !isChecked(p)) list.push({ y: Math.round((p.y0 + p.y1) / 2), kind: 'tall', panel: p });
    }
  }
  return list.sort((a, b) => a.y - b.y);
}

const snapshot = () => ({ cuts: state.cuts, reviewed: state.reviewed, checked: state.checked });

function renderChapter(intro = false) {
  const ch = state.chapter;
  const H = ch.height * scale();
  const strip = el('div', {
    id: 'strip',
    class: intro ? 'intro' : '',
    style: `height:${H}px`,
    onclick: onStripClick,
    onpointerdown: onPointerDown,
    onpointermove: onStripHover,
    onpointerleave: () => ($('#hint').hidden = true),
  });
  const rows = ch.tiles.rows;
  for (let i = 0; i < ch.tiles.count; i++) {
    const h = Math.min(rows, ch.height - i * rows) * scale();
    strip.append(el('img', { src: `/api/tile?id=${enc(ch.id)}&i=${i}`, loading: 'lazy', decoding: 'async', alt: '', style: `top:${i * rows * scale()}px;height:${h}px` }));
  }
  let notice = null;
  if (ch.manual_frames) {
    notice = el('div', { class: 'notice' }, icon('alert'), el('p', { text: `Ce chapitre a ${ch.manual_frames} frames faites à la main. « Créer la vidéo » les remplacera par cette découpe.` }));
  } else if (ch.stale_frames) {
    notice = el('div', { class: 'notice' }, icon('alert'), el('p', { text: 'La découpe a changé depuis la dernière vidéo. « Créer la vidéo » la mettra à jour.' }));
  }
  $('#view').replaceChildren(
    ...[el('div', { class: 'head', id: 'head' }), notice, el('div', { class: 'workspace' }, el('div', {}, strip), el('div', { class: 'side', id: 'side' }))].filter(Boolean),
  );
  renderHead();
  renderOverlays();
  renderSide();
  if (intro) setTimeout(() => $('#strip')?.classList.remove('intro'), 2500);
}

function screenTabs() {
  return el(
    'div',
    { class: 'tabs', role: 'tablist' },
    SCREENS.map(([key, label]) => el('button', { type: 'button', role: 'tab', 'aria-selected': String(state.screen === key), class: state.screen === key ? 'on' : '', onclick: () => switchScreen(key) }, label)),
  );
}

function switchScreen(screen) {
  if (screen === state.screen || !state.chapter) return;
  state.screen = screen;
  setHash();
  $('#hint').hidden = true;
  hidePeek();
  if (screen === 'cast') openCast();
  else if (screen === 'review') openReview();
  else if (screen === 'sounds') openSounds();
  else if (screen === 'video') openVideo();
  else {
    renderChapter(false);
    focusFrameRow();
  }
  $('main').scrollTop = 0;
}

// Le bouton vidéo dit si tes derniers changements (voix, sons, textes) y sont déjà
function videoButton(running) {
  const p = findEpisode(state.chapter.id)?.progress || state.chapter.progress;
  const upToDate = p && p.done === p.total;
  const stale = p?.video && !upToDate;
  if (running) {
    const job = findEpisode(state.chapter.id)?.job || state.chapter.job;
    const pct = job?.progress != null && job.status === 'running' ? ` ${Math.round(job.progress * 100)} %` : '';
    return el('button', { type: 'button', class: 'pill accent', disabled: true, title: 'L’avancement détaillé est dans le bandeau en bas à droite' }, el('span', { class: 'spinner light' }), `En cours…${pct}`);
  }
  if (upToDate) return el('button', { type: 'button', class: 'pill', title: 'La vidéo contient tous tes changements', onclick: () => switchScreen('video') }, icon('check'), 'Vidéo à jour');
  return el(
    'button',
    { type: 'button', class: `pill accent${stale ? ' pulse' : ''}`, title: stale ? 'Tu as changé des voix, des sons ou des textes depuis la dernière vidéo : elle ne les contient pas encore' : '', onclick: makeVideo },
    icon(stale ? 'reset' : 'play'),
    stale ? 'Mettre à jour la vidéo' : 'Créer la vidéo',
  );
}

function renderHead() {
  const ch = state.chapter;
  const head = $('#head');
  renderDock();
  if (!head) return;
  const job = findEpisode(ch.id)?.job || ch.job;
  const running = isRunning(job);
  const title = el('h2', { text: `${ch.series} · ${ch.name.replace('chapter-', 'Épisode ')}` });
  if (state.screen === 'video') {
    const v = state.videoInfo;
    const todo = v ? v.flags.filter((f) => !f.done).length : 0;
    head.replaceChildren(
      el('div', { class: 'titles' }, title, el('p', { text: v ? `${plural(v.timeline.length, 'case', 'cases')} · ${todo} passage${todo > 1 ? 's' : ''} à corriger` : 'Vidéo' })),
      screenTabs(),
      el('div', { class: 'actions' }, videoButton(running)),
    );
    return;
  }
  if (state.screen === 'sounds') {
    const s = state.sounds;
    const set = s ? [...s.spots, ...s.actions].filter((x) => x.sound !== s.none).length : 0;
    head.replaceChildren(
      el('div', { class: 'titles' }, title, el('p', { text: s ? `${state.soundKeys.size} à choisir · ${set} avec un son dans la vidéo` : 'Sons' })),
      screenTabs(),
      el('div', { class: 'actions' }, videoButton(running)),
    );
    return;
  }
  if (state.screen === 'review') {
    const r = state.review;
    const pending = r ? r.items.filter((x) => x.state === 'pending').length : 0;
    head.replaceChildren(
      el('div', { class: 'titles' }, title, el('p', { text: r ? (r.done ? `${plural(r.items.length, 'proposition', 'propositions')} de GPT · ${pending} à décider` : 'Pas encore relu par GPT') : 'Relecture' })),
      screenTabs(),
      el(
        'div',
        { class: 'actions' },
        r?.done ? el('button', { type: 'button', class: 'pill', disabled: running, title: 'Relire tout le chapitre (tes décisions sont gardées)', onclick: runReview }, running ? el('span', { class: 'spinner' }) : icon('reset'), 'Relire à nouveau') : null,
        videoButton(running),
      ),
    );
    return;
  }
  if (state.screen === 'cast') {
    const c = state.cast;
    const named = c ? c.characters.filter((x) => x.faces.length).length : 0;
    const done = c ? c.lines.filter((l) => l.speaker).length : 0;
    head.replaceChildren(
      el('div', { class: 'titles' }, title, el('p', { text: c ? `${plural(named, 'personnage', 'personnages')} · ${done} / ${plural(c.lines.length, 'réplique validée', 'répliques validées')}` : 'Personnages' })),
      screenTabs(),
      el(
        'div',
        { class: 'actions' },
        el('button', { type: 'button', class: 'pill', title: 'Chercher à nouveau les visages (garde ce que tu as rangé)', disabled: running || !c?.frames, onclick: () => analyzeFaces(true) }, running ? el('span', { class: 'spinner' }) : icon('reset'), 'Revoir les visages'),
        videoButton(running),
      ),
    );
    return;
  }
  const n = doubts().length;
  head.replaceChildren(
    el(
      'div',
      { class: 'titles' },
      title,
      el('p', { text: `${plural(state.panels.length, 'case', 'cases')} · ${plural(state.cuts.length, 'coupe', 'coupes')} · ${state.undo.length || ch.edited ? 'découpe retouchée' : 'découpe automatique'}` }),
    ),
    screenTabs(),
    el(
      'div',
      { class: 'actions' },
      n ? el('button', { type: 'button', class: 'pill warn', onclick: nextDoubt }, icon('down'), `${n} à vérifier`) : null,
      el('button', { type: 'button', class: 'pill', title: 'Revenir à la découpe automatique', onclick: resetCuts }, icon('reset'), 'Auto'),
      el('button', { type: 'button', class: 'pill', title: 'Comment ça marche', 'aria-label': 'Comment ça marche', onclick: () => { state.introOpen = true; renderSide(); $('#side').scrollTop = 0; } }, '?'),
      el('button', { type: 'button', class: 'pill', disabled: running, title: 'Tout d’un coup : visages, relecture GPT, voix, sons, puis la vidéo', onclick: runAuto }, icon('sparkles'), 'Tout faire'),
      videoButton(running),
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
        el('span', { class: `badge${p.screens > TALL_DOUBT && !state.reviewed && !isChecked(p) ? ' tall' : ''}`, text: tall ? `${i + 1} · ${fmt(p.screens)} écrans` : `${i + 1}` }),
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
  const cards = [];

  if (job && (isRunning(job) || job.status === 'error')) cards.push(jobCard(job));
  // la vidéo finie passe en premier : c'est ce qu'on vient chercher après « Créer la vidéo »
  else if (progress.done === progress.total) {
    cards.push(
      el(
        'div',
        { class: 'card' },
        el('h3', { text: 'Vidéo prête' }),
        el('div', { class: 'frame video' }, el('video', { src: `/api/video?id=${enc(ch.id)}&v=${Date.now()}`, controls: true, preload: 'metadata' })),
      ),
    );
  }

  cards.push(
    el(
      'div',
      { class: 'card' },
      el('h3', { text: 'Aperçu' }),
      el('div', { class: 'frame', id: 'preview' }, el('div', { class: 'empty', text: 'Survole une case pour voir sa frame 9:16.' })),
      el('p', { class: 'caption', id: 'preview-caption', text: ' ' }),
      el('div', { class: 'reading', id: 'reading' }),
    ),
  );

  const doubtsBox = doubtsCard();
  if (doubtsBox) cards.push(doubtsBox);

  if (showIntro()) cards.unshift(introCard());
  side.replaceChildren(...cards);
}

function doubtsCard() {
  const list = doubts();
  const n = list.length;
  if (!n) return null;
  const current = state.doubt >= 0 ? list[Math.min(state.doubt, n - 1)] : null;
  const what = !current
    ? 'Lignes en pointillés : coupe incertaine. Badge orange : case très haute, il manque peut-être une coupe.'
    : current.kind === 'cut'
      ? `Endroit ${Math.min(state.doubt, n - 1) + 1}/${n} : coupe incertaine. Garde-la, ou clique dessus pour la supprimer.`
      : `Endroit ${Math.min(state.doubt, n - 1) + 1}/${n} : case très haute (${fmt(current.panel.screens)} écrans). Ajoute une coupe si ce sont plusieurs cases.`;
  return el(
    'div',
    { class: 'card', id: 'doubts-card' },
    el('h3', { text: `${plural(n, 'endroit', 'endroits')} à vérifier` }),
    el('p', { class: 'muted', text: what }),
    el(
      'div',
      { class: 'actions', style: 'margin-top:10px;flex-wrap:wrap' },
      current
        ? el('button', { type: 'button', class: 'pill accent', onclick: keepDoubt }, icon('check'), 'C’est bon')
        : el('button', { type: 'button', class: 'pill accent', onclick: nextDoubt }, icon('down'), 'Voir le premier'),
      current ? el('button', { type: 'button', class: 'pill', onclick: nextDoubt }, icon('down'), 'Suivant') : null,
      el('button', { type: 'button', class: 'pill', onclick: acceptAll }, 'Tout est bon'),
    ),
  );
}

function refreshDoubts() {
  // met à jour la carte « à vérifier » sans toucher à l'aperçu ; toujours d'accord avec le compteur du haut
  const old = $('#doubts-card');
  const fresh = doubtsCard();
  if (old && fresh) old.replaceWith(fresh);
  else if (old) old.remove();
  else if (fresh) $('#side')?.append(fresh);
}

/* ---------- Mode d'emploi : affiché en haut à la première visite, rouvrable avec « ? » ---------- */

function showIntro() {
  try {
    return state.introOpen ?? localStorage.getItem('studio.intro.seen') !== '1';
  } catch {
    return state.introOpen ?? true;
  }
}

function closeIntro() {
  state.introOpen = false;
  try {
    localStorage.setItem('studio.intro.seen', '1');
  } catch {}
  renderSide();
}

function introCard() {
  return el(
    'div',
    { class: 'card intro-card' },
    el('h3', { text: 'Comment ça marche' }),
    el(
      'ol',
      {},
      el('li', {}, 'Les ', el('b', { text: 'lignes' }), ' sur le chapitre sont les coupes proposées : chaque morceau devient une case de la vidéo.'),
      el('li', {}, el('b', { text: 'Clic sur une ligne' }), ' : la supprimer. ', el('b', { text: 'Clic dans une case' }), ' : couper ici. ', el('b', { text: 'Glisser' }), ' : ajuster.'),
      el('li', {}, 'Pointillés et badges orange = ', el('b', { text: 'à vérifier' }), '. Le reste est sûr.'),
      el('li', {}, 'Survole une case pour voir sa frame ici. Puis ', el('b', { text: 'Créer la vidéo' }), '.'),
    ),
    el('button', { type: 'button', class: 'pill accent', onclick: closeIntro }, icon('check'), 'Compris'),
  );
}

/* ---------- Bulle d'aide qui suit le curseur ---------- */

function onStripHover(event) {
  const hint = $('#hint');
  if (!hint) return;
  if (state.drag) {
    hint.hidden = true;
    return;
  }
  hint.textContent = event.target.closest('.cut') ? 'Clic : supprimer · Glisser : ajuster' : 'Clic : couper ici';
  hint.style.left = `${event.clientX}px`;
  hint.style.top = `${event.clientY}px`;
  hint.hidden = false;
}

function remaining(job) {
  // estimation d'après la vitesse de l'étape en cours
  if (job.progress == null || job.progress <= 0.02 || !job.step_started) return '';
  const elapsed = Date.now() / 1000 - job.step_started;
  const left = (elapsed / job.progress) * (1 - job.progress);
  if (left < 60) return ' · moins d’une minute';
  return ` · ≈ ${Math.round(left / 60)} min restantes`;
}

function counted(job) {
  // « 6 210 / 12 960 images » : ce qui est fait sur le total de l'étape
  if (job.total == null) return '';
  return ` · ${job.done.toLocaleString('fr-FR')} / ${job.total.toLocaleString('fr-FR')} ${job.unit}`;
}

function jobCard(job) {
  const steps = job.kind === 'auto' ? AUTO_STEPS : KIND_STEPS[job.kind] || JOB_STEPS;
  const at = steps.findIndex(([step]) => step === job.step);
  const title = job.status === 'error' ? 'Erreur' : job.status === 'queued' ? 'En attente…' : KIND_TITLES[job.kind] || 'Création de la vidéo';
  const detail =
    job.status === 'running' && at >= 0
      ? `Étape ${at + 1}/${steps.length} · ${job.label}${counted(job)}${job.progress != null ? ` · ${Math.round(job.progress * 100)} %` : ''}${remaining(job)}`
      : '';
  return el(
    'div',
    { class: 'card', id: 'job-card' },
    el('div', { class: 'job' }, job.status === 'error' ? icon('alert') : el('span', { class: 'spinner' }), title),
    detail ? el('p', { class: 'job-progress', text: detail }) : null,
    job.progress != null && job.status === 'running' ? el('div', { class: 'bar' }, el('span', { style: `width:${job.progress * 100}%` })) : null,
    job.error ? el('p', { class: 'muted', style: 'margin-top:6px', text: job.error }) : null,
    (job.warnings || []).length ? el('p', { class: 'muted', style: 'margin-top:6px', text: `Sauté : ${job.warnings.join(' · ')}` }) : null,
    job.step === 'wiki_images' && job.status === 'running'
      ? el('p', { class: 'notice-inline' }, icon('alert'), 'Une fenêtre de navigateur s’est ouverte : si Cloudflare demande une vérification, passe-la dedans. La suite se fait toute seule.')
      : null,
    el(
      'div',
      { class: 'job-steps' },
      steps.map(([, label], i) => {
        const done = at > i;
        const on = at === i && job.status === 'running';
        return el('div', { class: done ? 'done' : on ? 'on' : '' }, done ? icon('check') : on ? el('span', { class: 'spinner' }) : el('span', { class: 'dot' }), label);
      }),
    ),
  );
}

/* ---------- Bandeau d'avancement : visible sur tous les onglets ---------- */

const dock = { open: false, done: null, doneTimer: null }; // done : le travail qui vient de finir (« Vidéo prête »)

function dockJob() {
  // le travail du chapitre ouvert d'abord, sinon celui d'un autre chapitre qui tourne
  const here = state.current && findEpisode(state.current)?.job;
  if (here && (isRunning(here) || here.status === 'error')) return { job: here, id: state.current };
  for (const s of state.library?.series || []) for (const c of s.chapters) if (isRunning(c.job)) return { job: c.job, id: c.id };
  return null;
}

function renderDock() {
  let box = $('#job-dock');
  if (!box) {
    box = el('div', { id: 'job-dock', hidden: true });
    document.body.append(box);
  }
  const found = dockJob();
  const cardOnScreen = document.getElementById('job-card'); // la même carte est déjà à l'écran (Découpe…)
  if (dock.done && !found) {
    const { id, title } = dock.done;
    box.hidden = false;
    box.className = 'done';
    fill(box,
      el('div', { class: 'dock-line' }, icon('check'), el('b', { text: title }),
        el('button', { type: 'button', class: 'pill accent', onclick: () => { dock.done = null; renderDock(); id === state.current ? switchScreen('video') : (location.hash = `#${enc(id)}/video`); } }, 'Voir'),
        el('button', { type: 'button', class: 'link quiet', 'aria-label': 'Fermer', onclick: () => { dock.done = null; renderDock(); } }, icon('x'))));
    return;
  }
  if (!found || (cardOnScreen && found.id === state.current)) {
    box.hidden = true;
    return;
  }
  const { job, id } = found;
  const steps = job.kind === 'auto' ? AUTO_STEPS : KIND_STEPS[job.kind] || JOB_STEPS;
  const at = steps.findIndex(([step]) => step === job.step);
  const name = id === state.current ? '' : `${id.split('/')[0]} · ${(id.split('/')[1] || '').replace('chapter-', 'Ép. ')} — `;
  const pct = job.progress != null ? ` · ${Math.round(job.progress * 100)} %` : '';
  box.hidden = false;
  box.className = job.status === 'error' ? 'error' : '';
  fill(box,
    el('button', { type: 'button', class: 'dock-line', title: dock.open ? 'Replier' : 'Voir toutes les étapes', onclick: () => { dock.open = !dock.open; renderDock(); } },
      job.status === 'error' ? icon('alert') : el('span', { class: 'spinner' }),
      el('span', { class: 'grow' },
        el('b', { text: `${name}${job.status === 'error' ? 'Erreur' : job.status === 'queued' ? 'En attente…' : KIND_TITLES[job.kind] || 'Création de la vidéo'}` }),
        el('span', { class: 'muted', text: job.status === 'running' && at >= 0 ? ` · ${at + 1}/${steps.length} ${steps[at][1]}${pct}${remaining(job)}` : '' })),
      icon(dock.open ? 'down' : 'plus')),
    job.progress != null && job.status === 'running' ? el('div', { class: 'bar' }, el('span', { style: `width:${job.progress * 100}%` })) : null,
    dock.open ? jobCard(job) : null);
  if (dock.open) box.querySelector('#job-card')?.removeAttribute('id'); // une seule « vraie » carte à mettre à jour
}

function dockFinished(before, after, id) {
  // un travail qui vient de finir : « Vidéo prête » (ou « Erreur ») reste affiché
  if (!isRunning(before) || isRunning(after)) return;
  if (after?.status === 'done' && ['make', 'auto'].includes(after.kind)) {
    const ep = (id.split('/')[1] || '').replace('chapter-', 'épisode ');
    dock.done = { id, title: `Vidéo prête · ${ep}` };
    clearTimeout(dock.doneTimer);
    dock.doneTimer = setTimeout(() => { dock.done = null; renderDock(); }, 60000);
  }
}

/* ---------- Aperçu ---------- */

let previewTimer;
function showPreview(i) {
  clearTimeout(previewTimer);
  document.querySelectorAll('.panel.on').forEach((n) => n.classList.remove('on'));
  document.querySelectorAll('.panel')[i]?.classList.add('on');
  previewTimer = setTimeout(async () => {
    const p = state.panels[i];
    if (!p) return;
    const id = state.chapter.id;
    // on demande au serveur les frames exactes que la vidéo fera pour cette case
    let frames;
    try {
      frames = await api(`/api/panel?id=${enc(id)}&y0=${p.y0}&y1=${p.y1}`);
    } catch {
      return;
    }
    if (state.chapter?.id !== id || state.panels[i] !== p) return;
    const src = ([a, b]) => `/api/preview?id=${enc(id)}&y0=${a}&y1=${b}&x0=${frames.x0}&x1=${frames.x1}`;
    const n = frames.parts.length;
    const box = $('#preview');
    if (!box) return;
    box.classList.toggle('multi', n > 1);
    box.style.setProperty('--n', n);
    box.replaceChildren(...frames.parts.map((part) => el('img', { src: src(part), alt: '' })));
    const caption = $('#preview-caption');
    if (caption) {
      const size = `${fmt(p.screens)} écran${p.screens >= 2 ? 's' : ''}`;
      caption.textContent = n > 1 ? `Case ${i + 1} · ${size} · la vidéo la montre en ${n} frames` : `Case ${i + 1} · ${size} · telle quelle dans la vidéo`;
    }
    renderReading(frames);
  }, 90);
}

// ce que la voix lira pour la case survolée, et les SFX repérés (servent aux bruitages)
const KIND_LABELS = { sfx: 'SFX', noise: 'bruit', number: 'chiffre seul', watermark: 'filigrane', credit: 'crédits', title: 'titre' };

function renderReading(frames) {
  const box = $('#reading');
  if (!box) return;
  if (!frames.ocr_done) {
    box.replaceChildren(el('p', { class: 'muted', text: 'Le texte sera lu à la création de la vidéo.' }));
    return;
  }
  const spoken = frames.bubbles.filter((b) => b.kind === 'dialogue');
  const other = frames.bubbles.filter((b) => KIND_LABELS[b.kind]);
  const parts = [
    spoken.length
      ? el('div', { class: 'spoken' }, ...spoken.map((b) => el('p', { text: `« ${b.text} »` })))
      : el('p', { class: 'muted', text: 'Rien à lire dans cette case.' }),
  ];
  if (other.length) {
    parts.push(
      el('div', { class: 'chips' }, ...other.map((b) => el('span', { class: `chip ${b.kind}`, title: `${KIND_LABELS[b.kind]} (pas lu) : ${b.text}`, text: `${KIND_LABELS[b.kind]} · ${b.text.slice(0, 18)}` }))),
      el('p', { class: 'muted', text: 'Pastilles : repéré mais pas lu par la voix. Les SFX serviront aux bruitages.' }),
    );
  }
  box.replaceChildren(...parts);
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
  state.undo.push(snapshot());
  state.cuts = cuts.sort((a, b) => a.y - b.y);
  state.panels = localPanels();
  state.confirmed = false;
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
  state.checked = previous.checked || [];
  state.panels = localPanels();
  state.confirmed = false;
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
  const body = JSON.stringify({ cuts: state.cuts, reviewed: state.reviewed, checked: state.checked });
  saving = saving
    .then(() => api(`/api/cuts?id=${enc(id)}`, { method: 'PUT', body }))
    .then((res) => {
      if (state.chapter?.id !== id) return;
      state.panels = res.panels;
      state.confirmed = true;
      state.chapter.edited = true;
      renderOverlays();
      renderHead();
      refreshDoubts();
    })
    .catch((e) => toast(`Sauvegarde impossible : ${e.message}`));
  return saving;
}

function nextDoubt() {
  const list = doubts();
  if (!list.length) {
    refreshDoubts();
    renderHead();
    toast('Plus rien à vérifier');
    return;
  }
  state.doubt = (state.doubt + 1) % list.length;
  focusDoubt(list[state.doubt]);
  refreshDoubts();
}

function keepDoubt() {
  // « C'est bon » : l'endroit en cours est vérifié, on passe au suivant
  const list = doubts();
  const target = list[Math.min(state.doubt, list.length - 1)];
  if (!target) return;
  state.undo.push(snapshot());
  if (target.kind === 'cut') state.cuts = state.cuts.map((c) => (c.y === target.y ? { ...c, sure: true } : c));
  else state.checked = [...state.checked, target.panel.y0];
  const rest = doubts();
  state.doubt = rest.length ? Math.min(state.doubt, rest.length - 1) : -1;
  renderOverlays();
  renderHead();
  renderSide();
  scheduleSave();
  if (rest.length) focusDoubt(rest[state.doubt]);
  else toast('Tout est vérifié', { label: 'Annuler', run: undo });
}

function focusDoubt(target) {
  // saut direct (le défilement animé ne démarre pas toujours sur un strip aussi long),
  // puis l'endroit visé clignote pour qu'on le repère tout de suite
  const strip = $('#strip');
  const main = $('main');
  const top = strip.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop + target.y * scale();
  main.scrollTo({ top: Math.max(0, top - main.clientHeight / 2) });
  let node = null;
  if (target.kind === 'cut') {
    node = strip.querySelector(`.cut[data-i="${state.cuts.findIndex((c) => c.y === target.y)}"]`);
  } else {
    node = strip.querySelectorAll('.panel')[state.panels.indexOf(target.panel)];
  }
  if (!node) return;
  node.classList.remove('focus');
  void node.offsetWidth; // relance l'animation
  node.classList.add('focus');
}

function acceptAll() {
  const cuts = state.cuts.map((c) => ({ ...c, sure: true }));
  state.undo.push(snapshot());
  state.cuts = cuts;
  state.reviewed = true;
  renderOverlays();
  renderHead();
  renderSide();
  scheduleSave();
  toast('Découpe validée', { label: 'Annuler', run: undo });
}

async function resetCuts() {
  const before = snapshot();
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

/* ---------- Chapitre : écran Personnages ---------- */

const castJob = () => findEpisode(state.current)?.job || state.cast?.job || state.chapter?.job;
const faceSrc = (f) => `/api/face?id=${enc(state.chapter.id)}&f=${enc(f)}`;

function charLabel(cid) {
  if (cid === state.cast?.narrator) return 'Narrateur';
  if (state.cast?.extras?.[cid]) return state.cast.extras[cid].label;
  const list = state.cast?.characters || [];
  const i = list.findIndex((c) => c.id === cid);
  if (i < 0) return '?';
  return list[i].name || `Perso ${i + 1}`;
}

function avatar(cid, size = '') {
  if (cid === state.cast.narrator) return el('span', { class: `avatar narrator ${size}` }, icon('sparkles'));
  if (state.cast.extras?.[cid]) return el('span', { class: `avatar extra ${size}` }, icon('users'));
  const c = state.cast.characters.find((x) => x.id === cid);
  return c?.cover ? el('img', { class: `avatar ${size}`, src: faceSrc(c.cover), alt: '' }) : el('span', { class: `avatar ${size}` }, icon('users'));
}

async function openCast() {
  const id = state.chapter.id;
  state.sel = new Set();
  state.cast = null;
  $('#view').replaceChildren(el('div', { class: 'head', id: 'head' }), el('div', { id: 'cast' }, el('div', { class: 'skeleton short' })), el('div', { id: 'tray', class: 'tray', hidden: true }));
  renderHead();
  try {
    const c = await api(`/api/cast?id=${enc(id)}`);
    if (state.chapter?.id !== id || state.screen !== 'cast') return;
    setCast(c, true);
    focusFrameRow();
  } catch (e) {
    $('#cast').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Impossible d’ouvrir les personnages : ${e.message}` })));
  }
}

function setCast(c, fresh = false) {
  state.cast = c;
  if (fresh) state.pendingKeys = new Set(c.lines.filter((l) => !l.speaker).map((l) => l.key));
  // première visite : la recherche des visages se lance toute seule (aucun clic à faire)
  const id = state.chapter.id;
  if (c.status !== 'ready' && c.frames && !isRunning(castJob()) && !state.autoAnalyzed.has(id)) {
    state.autoAnalyzed.add(id);
    analyzeFaces();
    return;
  }
  renderCast();
}

async function analyzeFaces(force = false) {
  // force : chercher à nouveau même si la découpe n'a pas changé (ce qui est rangé sert de modèle)
  const id = state.chapter.id;
  try {
    const job = await api(`/api/cast/analyze?id=${enc(id)}${force ? '&force=1' : ''}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    state.chapter.job = job;
    if (state.cast) state.cast.job = job;
    renderLibrary();
    renderCast();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function renderCast() {
  const box = $('#cast');
  if (!box || !state.cast) return;
  const c = state.cast;
  const job = castJob();
  renderHead();
  const parts = [];
  if (KIND_STEPS[job?.kind] && (isRunning(job) || job.status === 'error')) parts.push(jobCard(job));
  else if (isRunning(job)) parts.push(el('div', { class: 'notice' }, el('span', { class: 'spinner' }), el('p', { text: 'La vidéo est en cours de création : les personnages se mettront à jour après.' })));
  if (!c.frames) {
    parts.push(el('div', { class: 'notice' }, icon('alert'), el('p', { text: 'Crée d’abord la vidéo depuis l’onglet Découpe : les visages se cherchent dans ses frames.' })));
  } else if (c.status === 'stale' && !isRunning(job)) {
    parts.push(el('div', { class: 'notice' }, icon('alert'), el('p', {}, 'La découpe a changé depuis. ', el('button', { type: 'button', class: 'link', onclick: () => analyzeFaces() }, 'Chercher les visages à nouveau'), ' (ce que tu as rangé est gardé).')));
  }
  if (c.status !== 'missing') parts.push(charsSection(), linesSection());
  box.replaceChildren(...parts);
  renderTray();
}

/* Personnages : un groupe de visages par personnage, nommé une fois pour toute la série */

function charsSection() {
  const c = state.cast;
  const all = c.characters.map((ch, i) => ({ ...ch, i })).filter((ch) => ch.faces.length).sort((a, b) => b.faces.length - a.faces.length);
  const here = all.filter((ch) => !ch.silent);
  const silent = all.filter((ch) => ch.silent);
  const elsewhere = c.characters.filter((ch) => !ch.faces.length);
  const cards = here.map(charCard);
  if (c.unsorted.length) cards.push(looseCard(c.unsorted));
  return el(
    'section',
    { class: 'cast-block' },
    el(
      'div',
      { class: 'block-head row' },
      el('div', { class: 'grow' }, el('h3', { text: 'Personnages' }), el('p', { class: 'muted', text: 'Donne un nom à chaque groupe (ou clique sur un nom du wiki). Un visage mal rangé ? Clique dessus, puis sur le bon personnage dans la barre du bas.' })),
      el('div', { class: 'head-actions' }, voicesHead(), wikiStatus()),
    ),
    el('div', { class: 'cast-grid voices' }, narratorCard(), extrasCard()),
    el('div', { class: 'cast-grid packed' }, cards),
    silent.length
      ? el(
          'details',
          { class: 'silent-block', open: state.openDone.has('silent'), ontoggle: (e) => (e.currentTarget.open ? state.openDone.add('silent') : state.openDone.delete('silent')) },
          el('summary', {}, el('b', { text: `Ne parlent pas · ${silent.length}` }), el('span', { class: 'muted', text: ' · jamais proposés pour une réplique (« Parle » pour en remettre un)' })),
          el('div', { class: 'cast-grid packed' }, silent.map(charCard)),
        )
      : null,
    elsewhere.length ? el('p', { class: 'muted elsewhere', text: `Déjà vus dans la série : ${elsewhere.map((ch) => charLabel(ch.id)).join(', ')}.` }) : null,
    c.rejected.length
      ? el('details', { class: 'rejected' }, el('summary', { text: `${plural(c.rejected.length, 'forme écartée', 'formes écartées')} (pas des visages)` }), el('div', { class: 'faces' }, c.rejected.map(faceThumb)))
      : null,
  );
}

const person = (wid) => state.cast.people.find((w) => w.id === wid);
const FACES_SHOWN = 4; // une rangée ; au-delà, la carte se replie (« +12 ») : les cartes gardent la même taille

function facesList(ch) {
  const many = ch.faces.length > FACES_SHOWN + 1;
  const open = !many || state.openFaces.has(ch.id);
  const toggle = () => {
    if (state.openFaces.has(ch.id)) state.openFaces.delete(ch.id);
    else state.openFaces.add(ch.id);
    document.querySelector(`.who[data-char="${CSS.escape(ch.id)}"] .faces`)?.replaceWith(facesList(ch));
  };
  return el(
    'div',
    { class: 'faces' },
    (open ? ch.faces : ch.faces.slice(0, FACES_SHOWN)).map(faceThumb),
    many ? el('button', { type: 'button', class: 'more-faces', title: open ? 'Replier' : 'Voir tous ses visages', onclick: toggle }, open ? 'Replier' : `+${ch.faces.length - FACES_SHOWN}`) : null,
  );
}


function charCard(ch) {
  return el(
    'div',
    { class: `card who${ch.silent ? ' silent' : ''}`, 'data-char': ch.id },
    el(
      'div',
      { class: 'who-head' },
      avatar(ch.id, 'big'),
      el('input', {
        class: 'name',
        value: ch.name,
        placeholder: `Perso ${ch.i + 1} · qui est-ce ?`,
        'aria-label': 'Nom du personnage',
        maxlength: 40,
        autocomplete: 'off',
        onfocus: (e) => openPicker(ch, e.target),
        onblur: () => setTimeout(closePicker, 150),
        onchange: (e) => {
          // un nom choisi dans la liste du wiki lie aussi sa fiche
          const page = state.cast.people.find((w) => w.title === e.target.value.trim());
          updateChar(ch.id, page ? { name: page.title, wiki: page.id } : { name: e.target.value });
        },
        onkeydown: (e) => {
          if (e.key === 'Enter') e.target.blur();
          if (e.key === 'Escape') closePicker();
        },
      }),
      el('button', { type: 'button', class: 'count', title: 'Sélectionner tous ses visages', onclick: () => selectFaces(ch.faces) }, String(ch.faces.length)),
    ),
    wikiLine(ch),
    ch.silent ? null : voiceRow(ch),
    facesList(ch),
    el(
      'div',
      { class: 'who-foot' },
      el('button', { type: 'button', class: 'link quiet', title: ch.silent ? 'Il peut être proposé pour les répliques' : 'Il ne sera plus proposé pour les répliques', onclick: () => updateChar(ch.id, { silent: !ch.silent }) }, ch.silent ? 'Parle' : 'Ne parle pas'),
    ),
  );
}

/* Liste des noms du wiki sous le champ : les têtes, les propositions d'abord */

function closePicker() {
  $('#picker')?.remove();
}

function pickerThumb(w) {
  if (!w.thumb) return el('span', { class: 'pick-thumb' }, w.title.split(/\s+/).map((p) => p[0]).join('').slice(0, 2));
  return el('img', { class: 'pick-thumb', src: `/api/wiki_thumb?id=${enc(state.chapter.id)}&w=${enc(w.id)}`, alt: '' });
}

function openPicker(ch, input) {
  closePicker();
  const c = state.cast;
  if (!c.people.length) return;
  const box = el('div', { class: 'picker', id: 'picker' });
  input.closest('.who-head').append(box);
  const pick = (w) => {
    closePicker();
    input.value = w.title;
    updateChar(ch.id, { name: w.title, wiki: w.id });
  };
  const row = (w, proposed) => {
    const owner = c.characters.find((x) => x.wiki === w.id && x.id !== ch.id);
    const facts = [w.debut ? `dès le ch. ${w.debut}` : null, w.gender, w.hair && `cheveux : ${w.hair.split(/[,(]/)[0].trim()}`].filter(Boolean).join(' · ');
    return el(
      'button',
      // mousedown : avant que le champ perde le focus (et ferme la liste)
      { type: 'button', class: `pick-row${proposed ? ' proposed' : ''}${owner ? ' taken' : ''}`, onmousedown: (e) => { e.preventDefault(); pick(w); } },
      pickerThumb(w),
      el('span', { class: 'pick-text' }, el('b', { text: w.title }), el('span', { class: 'muted', text: facts })),
      owner ? el('span', { class: 'pick-tag', text: `déjà : ${charLabel(owner.id)}` }) : proposed ? el('span', { class: 'pick-tag accent', text: 'proposé' }) : null,
    );
  };
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const match = (w) => !q || w.title.toLowerCase().includes(q) || (w.name || '').toLowerCase().includes(q);
    // jamais les personnages qui n'apparaissent que plus tard (spoiler)
    const people = c.people.filter((w) => !w.later && match(w));
    const proposed = ch.suggest.map(person).filter((w) => w && match(w));
    // ceux déjà donnés à un autre groupe passent à la fin
    const taken = new Set(c.characters.filter((x) => x.wiki && x.id !== ch.id).map((x) => x.wiki));
    const rest = people.filter((w) => !ch.suggest.includes(w.id)).sort((a, b) => taken.has(a.id) - taken.has(b.id));
    const groups = [
      ['Proposés', proposed, true],
      ['Déjà apparus', rest.filter((w) => w.debut), false],
      ['Apparition inconnue', rest.filter((w) => !w.debut), false],
    ].filter(([, list]) => list.length);
    box.replaceChildren(
      ...(groups.length
        ? groups.map(([title, list, isProposed]) => el('div', { class: 'pick-group' }, el('p', { class: 'pick-title', text: title }), list.map((w) => row(w, isProposed))))
        : [el('p', { class: 'muted pick-empty', text: 'Aucun personnage du wiki à ce nom : Entrée pour garder le nom tapé.' })]),
    );
  };
  input.addEventListener('input', render);
  render();
}

function wikiLine(ch) {
  // fiche liée : genre, cheveux, apparition, caractère ; sinon : les noms proposés
  const page = ch.wiki && person(ch.wiki);
  if (page) {
    const facts = [page.gender, page.hair && `cheveux : ${page.hair.split(',')[0]}`, page.debut && `dès le ch. ${page.debut}`].filter(Boolean).join(' · ');
    return el(
      'div',
      { class: 'wiki-card' },
      page.image ? el('img', { class: 'wiki-portrait', src: `/api/wiki_image?id=${enc(state.chapter.id)}&f=${enc(page.image)}`, alt: '' }) : null,
      el(
        'div',
        { class: 'wiki-text' },
        el('p', {}, el('b', { text: page.title }), page.name !== page.title ? el('span', { class: 'muted', text: ` (${page.name})` }) : null),
        facts ? el('p', { class: 'muted', text: facts }) : null,
        page.personality ? el('details', {}, el('summary', { text: 'Caractère (wiki)' }), el('p', { text: page.personality })) : null,
        el('p', {}, el('a', { href: page.url, target: '_blank', rel: 'noopener noreferrer', class: 'link' }, 'Voir sur le wiki'), ' · ', el('button', { type: 'button', class: 'link quiet', onclick: () => updateChar(ch.id, { wiki: null }) }, 'Pas lui')),
      ),
    );
  }
  if (!ch.suggest.length) return null;
  return el(
    'div',
    { class: 'who-chips wiki-suggest' },
    el('span', { class: 'muted', text: 'Wiki :' }),
    ch.suggest.map((wid, k) => {
      const w = person(wid);
      return w ? el('button', { type: 'button', class: `chip-btn plain${k === 0 ? ' proposed' : ''}`, title: k === 0 ? 'Le plus probable (cheveux, apparition, visage)' : 'Autre possibilité', onclick: () => updateChar(ch.id, { name: w.title, wiki: w.id }) }, w.title) : null;
    }),
  );
}

function wikiStatus() {
  const c = state.cast;
  const busy = isRunning(castJob());
  if (!c.wiki) {
    return el('div', { class: 'actions' }, el('button', { type: 'button', class: 'pill', disabled: busy, onclick: () => readWiki(false) }, icon('users'), 'Noms depuis le wiki'));
  }
  const missing = c.wiki.listed && !c.wiki.images; // images pas encore téléchargées (une image introuvable ne compte pas)
  return el(
    'div',
    { class: 'actions wiki-status' },
    el('span', { class: 'muted', text: `${c.wiki.sitename} · ${plural(c.people.length, 'personnage', 'personnages')} · lu le ${c.wiki.fetched}` }),
    missing
      ? el('button', { type: 'button', class: 'pill', disabled: busy, title: 'Ouvre une fenêtre de navigateur : la vérification Cloudflare se passe à la main, une fois', onclick: () => readWiki(true) }, 'Images du wiki')
      : null,
    el('button', { type: 'button', class: 'pill', disabled: busy, title: 'Relire le wiki', onclick: () => readWiki(false) }, icon('reset')),
  );
}

async function readWiki(images) {
  const id = state.chapter.id;
  try {
    const job = await api(`/api/cast/wiki?id=${enc(id)}${images ? '&images=1' : ''}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    state.chapter.job = job;
    state.cast.job = job;
    renderCast();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function looseCard(faces) {
  return el(
    'div',
    { class: 'card who loose' },
    el(
      'div',
      { class: 'who-head' },
      el('span', { class: 'avatar big' }, icon('users')),
      el('div', { class: 'name static' }, el('b', { text: 'Autres visages' }), el('span', { class: 'muted', text: 'Pas encore rangés' })),
      el('button', { type: 'button', class: 'count', title: 'Tout sélectionner', onclick: () => selectFaces(faces) }, String(faces.length)),
    ),
    el('div', { class: 'faces' }, faces.map(faceThumb)),
  );
}

function faceThumb(fid) {
  return el(
    'button',
    { type: 'button', class: `face${state.sel.has(fid) ? ' sel' : ''}`, 'data-face': fid, onclick: () => toggleFace(fid), onmouseenter: (e) => peekFace(fid, e.currentTarget), onmouseleave: hidePeek },
    el('img', { src: faceSrc(fid), alt: '', loading: 'lazy' }),
  );
}

/* Aperçu agrandi au survol : la case d'où vient un visage, ou une réplique en grand */

let peekTimer;
const CONTEXT = 1.8; // hauteur montrée autour de la case, en largeurs de chapitre

function showContext(anchor, crop, boxes) {
  // boxes : [[classe, [x, y, w, h] dans le repère de la case], ...]
  clearTimeout(peekTimer);
  peekTimer = setTimeout(() => {
    const W = state.chapter.width;
    const H = state.chapter.height;
    const [cx, cy, cw, ch] = crop;
    // la case entière et un peu de ce qui l'entoure ; une case très haute : centrée sur la bulle ou le visage
    const span = Math.min(H, Math.max(CONTEXT * W, Math.min(ch + 0.8 * W, 2.6 * W)));
    const focus = ch + 0.8 * W <= span ? cy + ch / 2 : cy + boxes[0][1][1] + boxes[0][1][3] / 2;
    const y0 = Math.round(Math.max(0, Math.min(H - span, focus - span / 2)));
    const view = [0, y0, W, Math.round(span)];
    const toStrip = ([x, y, w, h]) => [cx + x, cy + y, w, h];
    let box = $('#peek');
    if (!box) document.body.append((box = el('div', { id: 'peek' })));
    box.replaceChildren(
      el(
        'div',
        { class: 'shot', style: `aspect-ratio:${W}/${view[3]}` },
        el('img', { src: `/api/strip?id=${enc(state.chapter.id)}&y=${view[1]}&h=${view[3]}&w=600`, alt: '' }),
        el('span', { class: 'frame-box', style: boxStyle([cx, cy, cw, ch], view) }),
        boxes.map(([cls, b]) => el('span', { class: cls, style: boxStyle(toStrip(b), view) })),
      ),
      el('p', { class: 'peek-caption', text: 'Cadre : la case de la vidéo · autour : le chapitre' }),
    );
    // à côté de l'élément survolé, aussi grand que l'écran le permet
    const r = anchor.getBoundingClientRect();
    const h = window.innerHeight - 70;
    const w = Math.min(560, (h * W) / view[3]);
    const imgH = (w * view[3]) / W;
    box.style.width = `${w + 12}px`;
    const left = r.right + 12 + w < window.innerWidth ? r.right + 12 : Math.max(12, r.left - 24 - w);
    box.style.left = `${left}px`;
    box.style.top = `${Math.max(12, Math.min(window.innerHeight - imgH - 50, r.top + r.height / 2 - imgH / 2))}px`;
    box.hidden = false;
  }, 180);
}

function hidePeek() {
  clearTimeout(peekTimer);
  const box = $('#peek');
  if (box) box.hidden = true;
}

function peekFace(fid, anchor) {
  const v = state.cast?.face_views?.[fid];
  if (v) showContext(anchor, v.crop, [['face-box on', v.box]]);
}

function paintSelection() {
  document.querySelectorAll('.face').forEach((n) => n.classList.toggle('sel', state.sel.has(n.dataset.face)));
  renderTray();
}

function toggleFace(fid) {
  if (state.sel.has(fid)) state.sel.delete(fid);
  else state.sel.add(fid);
  paintSelection();
}

function selectFaces(faces) {
  const all = faces.every((f) => state.sel.has(f));
  for (const f of faces) {
    if (all) state.sel.delete(f);
    else state.sel.add(f);
  }
  paintSelection();
}

function renderTray() {
  const tray = $('#tray');
  if (!tray) return;
  const n = state.sel.size;
  tray.hidden = !n;
  if (!n) return;
  const c = state.cast;
  tray.replaceChildren(
    el('b', { text: `${plural(n, 'visage', 'visages')} → ranger dans` }),
    el(
      'div',
      { class: 'tray-targets' },
      c.characters.map((ch) => el('button', { type: 'button', class: 'chip-btn', onclick: () => moveFaces(ch.id) }, avatar(ch.id, 'small'), charLabel(ch.id))),
      el('button', { type: 'button', class: 'chip-btn', onclick: () => moveFaces('new') }, icon('plus'), 'Nouveau personnage'),
      c.unsorted.length || n ? el('button', { type: 'button', class: 'chip-btn', onclick: () => moveFaces('none') }, 'Autres visages') : null,
      el('button', { type: 'button', class: 'chip-btn quiet', onclick: () => moveFaces('not_face') }, 'Pas un visage'),
    ),
    el('button', { type: 'button', class: 'pill', title: 'Annuler la sélection', 'aria-label': 'Annuler la sélection', onclick: () => { state.sel.clear(); paintSelection(); } }, icon('x')),
  );
}

function faceOwner(fid) {
  const c = state.cast;
  if (c.rejected.includes(fid)) return 'not_face';
  return c.characters.find((ch) => ch.faces.includes(fid))?.id || 'none';
}

async function moveFaces(to, quiet = false) {
  const faces = [...state.sel];
  const before = {};
  for (const f of faces) (before[faceOwner(f)] ||= []).push(f);
  const id = state.chapter.id;
  try {
    const res = await api(`/api/cast/move?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ faces, to }) });
    if (state.chapter?.id !== id) return;
    state.sel.clear();
    setCast(res);
    if (quiet) return;
    const where = to === 'not_face' ? '« pas un visage »' : to === 'none' ? '« autres visages »' : charLabel(res.moved_to);
    toast(`${plural(faces.length, 'visage rangé', 'visages rangés')} dans ${where}`, { label: 'Annuler', run: () => undoMove(before) });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function undoMove(before) {
  for (const [to, faces] of Object.entries(before)) {
    state.sel = new Set(faces);
    // un personnage sans nom vidé par le déplacement a été retiré : on le recrée
    const gone = !['none', 'not_face'].includes(to) && !state.cast.characters.some((c) => c.id === to);
    await moveFaces(gone ? 'new' : to, true);
  }
}

async function updateChar(cid, changes) {
  try {
    state.cast = await api(`/api/cast/character?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ char: cid, ...changes }) });
    if ('voice' in changes || ('voice_ok' in changes && Object.keys(changes).length === 1)) {
      // la voix change : seule cette carte est redessinée (pas les 150 répliques), et on l'écoute tout de suite
      const i = state.cast.characters.findIndex((c) => c.id === cid);
      const card = document.querySelector(`.who[data-char="${CSS.escape(cid)}"]`);
      if (card && i >= 0) card.replaceWith(charCard({ ...state.cast.characters[i], i }));
      renderHead();
      if ('voice' in changes) {
        const play = document.querySelector(`.who[data-char="${CSS.escape(cid)}"] .play`);
        if (play) playSample(play, { char: cid });
      }
      return;
    }
    if ('name' in changes && Object.keys(changes).length === 1) {
      // nom tapé à la main : les champs restent tels quels (on écrit peut-être déjà le suivant)
      $('#speak')?.replaceWith(linesSection());
      renderTray();
      renderHead();
    } else {
      const top = $('main').scrollTop;
      renderCast();
      $('main').scrollTop = top;
    }
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

/* Qui parle : chaque réplique, avec le personnage proposé (visage le plus proche de la bulle) */

function linesSection() {
  const c = state.cast;
  const total = c.lines.length;
  const done = c.lines.filter((l) => l.speaker).length;
  const queue = c.lines.filter((l) => state.pendingKeys.has(l.key));
  const rest = c.lines.filter((l) => !state.pendingKeys.has(l.key));
  const proposals = queue.filter((l) => !l.speaker && l.suggestion).length;
  let body;
  if (!c.ocr_done) body = [el('p', { class: 'muted', text: 'Le texte n’a pas encore été lu : crée d’abord la vidéo.' })];
  else if (!total) body = [el('p', { class: 'muted', text: 'Aucune réplique dans ce chapitre.' })];
  else
    body = [
      queue.length
        ? el('div', { class: 'lines queue', id: 'speak-queue' }, queue.map(lineRow))
        : el('div', { class: 'notice queue-empty' }, icon('check'), el('p', { text: 'Toutes les répliques ont leur personnage. Pour changer d’avis : « Déjà validées », juste dessous.' })),
      doneList('speak-done', `Déjà validées · ${rest.length}`, rest.map(lineRow)),
    ];
  return el(
    'section',
    { class: 'cast-block', id: 'speak' },
    el(
      'div',
      { class: 'block-head row' },
      el('div', { class: 'grow' }, el('h3', { text: `Qui parle · ${queue.length} à valider` }), el('p', { class: 'muted', text: 'Clique sur la bonne tête, sur l’image ou dessous (en pointillés : la proposition). La réplique se range en bas au bout de 2 secondes (tant que ta souris bouge dessus, elle attend) et la suivante prend sa place : tu peux changer d’avis avant, ou plus tard dans « Déjà validées ».' })),
      el('div', { class: 'actions' }, proposals ? el('button', { type: 'button', class: 'pill accent', onclick: acceptProposals }, icon('check'), `Valider les ${proposals} propositions`) : null),
    ),
    el('div', { class: 'bar' }, el('span', { style: `width:${total ? (100 * done) / total : 0}%` })),
    ...body,
  );
}

function boxStyle(box, view) {
  const [, vy, vw, vh] = view;
  return `left:${(100 * box[0]) / vw}%;top:${(100 * (box[1] - vy)) / vh}%;width:${(100 * box[2]) / vw}%;height:${(100 * box[3]) / vh}%`;
}

function lineRow(l) {
  const c = state.cast;
  const [, vy, vw, vh] = l.view;
  const options = [...l.candidates];
  if (l.speaker && l.speaker !== c.narrator && !options.includes(l.speaker)) options.unshift(l.speaker);
  const state_ = (cid) => (l.speaker === cid ? ' on' : !l.speaker && l.suggestion === cid ? ' proposed' : '');
  const chip = (cid) => el('button', { type: 'button', class: `chip-btn${state_(cid)}`, onclick: () => setSpeaker(l, cid) }, avatar(cid, 'small'), charLabel(cid));
  const others = c.characters.filter((ch) => !options.includes(ch.id));
  return el(
    'div',
    { class: `line-row${l.speaker ? ' done' : ''}`, 'data-key': l.key },
    el(
      'div',
      {
        class: 'shot',
        style: `aspect-ratio:${vw}/${vh}`,
        // survol : la même image en grand (les cadres des visages restent cliquables)
        onmouseenter: (e) => showContext(e.currentTarget, l.crop, [['bubble-box', l.box], ...l.faces.map((f) => ['face-box', f.box])]),
        onmouseleave: hidePeek,
      },
      el('img', { src: `/api/crop?id=${enc(state.chapter.id)}&frame=${enc(l.frame)}&y=${vy}&h=${vh}`, alt: '', loading: 'lazy' }),
      el('span', { class: 'bubble-box', style: boxStyle(l.box, l.view) }),
      l.faces.map((f) =>
        el('button', { type: 'button', class: `face-box${state_(f.char)}`, style: boxStyle(f.box, l.view), title: `C’est ${charLabel(f.char)} qui parle`, onclick: () => setSpeaker(l, f.char) }, el('span', { text: charLabel(f.char) })),
      ),
    ),
    el(
      'div',
      { class: 'line-body' },
      el('p', { class: 'quote', text: `« ${l.text} »` }),
      el('div', { class: 'line-meta' }, emotionSelect(l), l.kind !== 'dialogue' ? el('span', { class: 'chip', text: { thought: 'pensée', narration: 'narration' }[l.kind] || l.kind }) : null, l.auto ? el('span', { class: 'chip', title: 'Validé par le pilote automatique ([auto] speakers)', text: 'validé d’office' }) : null),
      el(
        'div',
        { class: 'who-chips' },
        options.map(chip),
        chip(c.narrator),
        el(
          'select',
          { class: 'chip-btn', 'aria-label': 'Un autre personnage', onchange: (e) => pickOther(l, e.target) },
          el('option', { value: '', text: 'Autre…' }),
          others.length ? el('optgroup', { label: 'Personnages' }, others.map((ch) => el('option', { value: ch.id, text: charLabel(ch.id) }))) : null,
          el('optgroup', { label: 'Personnage secondaire' },
            Object.entries(c.extras || {}).map(([k, x]) => el('option', { value: k, text: x.label })),
            el('option', { value: '__new', text: '+ Nouveau personnage…' })),
        ),
      ),
    ),
  );
}

async function sendSpeakers(choices) {
  const id = state.chapter.id;
  const res = await api(`/api/cast/speakers?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ choices }) });
  if (state.chapter?.id === id) state.cast = res;
  return res;
}

async function setSpeaker(l, cid) {
  const before = l.speaker;
  try {
    await sendSpeakers([{ key: l.key, char: cid }]);
    // seule la ligne et le compteur changent : pas de saut dans la liste
    const fresh = state.cast.lines.find((x) => x.key === l.key);
    if (fresh) document.querySelector(`.line-row[data-key="${CSS.escape(l.key)}"]`)?.replaceWith(lineRow(fresh));
    refreshSpeakHead();
    renderHead();
    if (state.pendingKeys.has(l.key)) {
      if (fresh?.speaker)
        settle(l.key, SETTLE, () => {
          state.pendingKeys.delete(l.key);
          afterSettle(l.key, linesSection());
        });
      else unsettle(l.key);
    }
    const face = nearestFace(fresh || l);
    if (face && cid && face.char !== cid && state.cast.characters.some((c) => c.id === cid)) {
      // le visage le plus proche de la bulle porte un autre nom : c'est peut-être lui qui est mal rangé
      toast(`Le visage encadré (« ${charLabel(face.char)} »), c’est ${charLabel(cid)} ?`, { label: 'Oui, corriger', run: () => fixFace(face.id, cid) });
    } else if (before !== cid && fresh) toast(`« ${l.text.slice(0, 32)}${l.text.length > 32 ? '…' : ''} » → ${cid ? charLabel(cid) : 'personne'}`, { label: 'Annuler', run: () => setSpeaker(fresh, before) });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function nearestFace(l) {
  if (!l?.faces?.length) return null;
  const [bx, by] = [l.box[0] + l.box[2] / 2, l.box[1] + l.box[3] / 2];
  const d = (f) => Math.hypot(f.box[0] + f.box[2] / 2 - bx, f.box[1] + f.box[3] / 2 - by);
  return [...l.faces].sort((a, b) => d(a) - d(b))[0];
}

async function fixFace(faceId, cid) {
  // range ce visage dans le bon personnage : toutes les répliques et les groupes se mettent à jour
  state.sel = new Set([faceId]);
  const top = $('main').scrollTop;
  await moveFaces(cid);
  $('main').scrollTop = top;
}

async function pickOther(l, select) {
  const value = select.value;
  select.value = '';
  if (!value) return;
  if (value !== '__new') return setSpeaker(l, value);
  const name = prompt('Nom du personnage (il gardera son nom pour toute la série) :');
  if (!name || !name.trim()) return;
  try {
    const res = await api(`/api/cast/new?id=${enc(state.chapter.id)}`, { method: 'POST', body: JSON.stringify({ name, key: l.key }) });
    state.cast = res;
    const top = $('main').scrollTop;
    renderCast();
    $('main').scrollTop = top;
    toast(`${name.trim()} ajouté : il dit cette réplique (sa voix est choisie à la création de la vidéo, modifiable dans sa carte)`);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function refreshSpeakHead() {
  // compteur, barre et bouton « Valider les propositions » sans redessiner les répliques
  const old = $('#speak');
  if (!old) return;
  const fresh = linesSection();
  old.querySelector('.block-head').replaceWith(fresh.querySelector('.block-head'));
  old.querySelector('.bar')?.replaceWith(fresh.querySelector('.bar'));
}

async function acceptProposals() {
  const todo = state.cast.lines.filter((l) => !l.speaker && l.suggestion);
  try {
    await sendSpeakers(todo.map((l) => ({ key: l.key, char: l.suggestion })));
    for (const l of todo) state.pendingKeys.delete(l.key);
    $('#speak').replaceWith(linesSection());
    renderHead();
    toast(plural(todo.length, 'réplique validée', 'répliques validées'), {
      label: 'Annuler',
      run: async () => {
        await sendSpeakers(todo.map((l) => ({ key: l.key, char: null })));
        for (const l of todo) state.pendingKeys.add(l.key);
        $('#speak')?.replaceWith(linesSection());
        renderHead();
      },
    });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function onCastJob(before, after) {
  // la recherche des visages avance, ou vient de finir
  if (isRunning(after)) {
    const card = $('#job-card');
    if (card && KIND_STEPS[after.kind]) card.replaceWith(jobCard(after));
    else renderCast();
    return;
  }
  if (isRunning(before)) {
    try {
      const c = await api(`/api/cast?id=${enc(state.chapter.id)}`);
      if (state.screen === 'cast') setCast(c, true);
    } catch {}
  }
}

/* ---------- Voix des personnages ---------- */

const player = new Audio();
let playing = null; // bouton ▶ en cours

function voiceOf(char) {
  const c = state.cast;
  if (!c) return null;
  if (char === c.narrator) return c.narrator_voice;
  if (c.extras?.[char]) return c.extras[char].voice;
  return c.characters.find((x) => x.id === char)?.voice || null;
}

function playSample(button, params) {
  // un deuxième clic sur le même bouton arrête l'extrait
  if (playing === button && !player.paused) {
    player.pause();
    button.classList.remove('on');
    playing = null;
    return;
  }
  playing?.classList.remove('on');
  playing = button;
  button.classList.add('on', 'loading');
  const v = voiceOf(params.char);
  const q = new URLSearchParams({ id: state.chapter.id, ...(v ? { name: v.name, pitch: v.pitch || '+0Hz', rate: v.rate || '+0%', expressive: v.expressive ? '1' : '' } : {}), ...params });
  player.src = `/api/voice_sample?${q}`;
  player.play().catch(() => toast('Extrait impossible (connexion à la voix ?)')).finally(() => button.classList.remove('loading'));
  player.onended = () => {
    button.classList.remove('on');
    playing = null;
  };
}

function voiceSelect(current, onpick) {
  const c = state.cast;
  const groups = { Male: 'Voix d’homme', Female: 'Voix de femme' };
  return el(
    'select',
    { class: 'chip-btn voice-select', 'aria-label': 'Voix', onchange: (e) => onpick(e.target.value) },
    Object.entries(groups).map(([g, label]) =>
      el('optgroup', { label }, c.voices.filter((v) => v.gender === g).map((v) => el('option', { value: v.name, selected: v.name === current, text: `${v.label}${v.traits ? ` · ${v.traits}` : ''}` }))),
    ),
  );
}

function voiceRow(ch) {
  const v = ch.voice;
  if (!v) return el('div', { class: 'voice-row' }, el('span', { class: 'muted', text: 'Voix : donnée à la création de la vidéo (ou « Proposer les voix »).' }));
  const shift = (d) => updateChar(ch.id, { voice: { ...v, pitch: `${(parseInt(v.pitch, 10) || 0) + d}Hz` } });
  const pitch = parseInt(v.pitch, 10) || 0;
  return el(
    'div',
    { class: `voice-row${ch.voice_ok ? ' ok' : ''}` },
    el('button', { type: 'button', class: 'play', title: 'Écouter une de ses répliques', 'aria-label': 'Écouter', onclick: (e) => playSample(e.currentTarget, { char: ch.id }) }, icon('play')),
    state.cast.qwen ? null : voiceSelect(v.name, (name) => updateChar(ch.id, { voice: { ...v, name } })),
    state.cast.qwen ? null : el('span', { class: 'pitch' },
      el('button', { type: 'button', class: 'link quiet', title: 'Plus grave', onclick: () => shift(-6) }, '−'),
      el('span', { class: 'muted', text: pitch ? `${pitch > 0 ? '+' : ''}${pitch} Hz` : 'hauteur' }),
      el('button', { type: 'button', class: 'link quiet', title: 'Plus aigu', onclick: () => shift(6) }, '+')),
    state.cast.qwen ? null : state.cast.expressive
      ? el('button', { type: 'button', class: `chip-btn plain${v.expressive ? ' on' : ''}`, title: 'Voix plus vivante (Chatterbox, local) : le ton change avec l’émotion de chaque réplique', onclick: () => updateChar(ch.id, { voice: { ...v, expressive: !v.expressive } }) }, icon('sparkles'), 'Expressive')
      : null,
    ch.voice_ok
      ? el('span', { class: 'voice-ok' }, icon('check'), 'validée')
      : el('button', { type: 'button', class: 'chip-btn plain proposed', title: v.reason || '', onclick: () => updateChar(ch.id, { voice_ok: true }) }, icon('check'), 'Valider'),
    !ch.voice_ok && v.reason && !state.cast.qwen ? el('p', { class: 'muted voice-reason', text: `${v.by === 'gpt' ? 'GPT' : 'Auto'} : ${v.reason}` }) : null,
    designRow(ch.id),
  );
}

function designRow(char) {
  // Qwen3-TTS : la voix est une description (GPT) ; « Autre voix » en redemande une, « Modifier » pour l'écrire
  const c = state.cast;
  if (!c.qwen) return null;
  const text = c.designs?.[char];
  const editing = state.editDesign === char;
  if (editing) {
    const box = el('textarea', { class: 'field design-text', rows: 2, text: text || '', 'aria-label': 'Description de la voix (en anglais)' });
    setTimeout(() => box.focus(), 0);
    return el('div', { class: 'design-row' }, box,
      el('div', { class: 'who-chips' },
        el('button', { type: 'button', class: 'chip-btn plain', onclick: () => { state.editDesign = null; renderCast(); } }, 'Annuler'),
        el('button', { type: 'button', class: 'chip-btn plain on', onclick: () => setDesign(char, box.value) }, icon('check'), 'Enregistrer')));
  }
  return el('div', { class: 'design-row' },
    el('p', { class: 'muted voice-reason', title: 'La voix que Qwen joue, avec l’émotion de chaque réplique', text: text ? `Voix : ${text}` : 'Voix : décrite par GPT à la création de la vidéo (▶ pour l’entendre).' }),
    el('div', { class: 'who-chips' },
      el('button', { type: 'button', class: 'chip-btn plain', title: 'GPT propose une autre voix pour ce personnage', onclick: () => setDesign(char, '') }, icon('sparkles'), 'Autre voix'),
      el('button', { type: 'button', class: 'chip-btn plain', onclick: () => { state.editDesign = char; renderCast(); } }, icon('edit'), 'Modifier')));
}

async function setDesign(char, design) {
  try {
    toast(design ? 'Voix enregistrée' : 'GPT cherche une autre voix…');
    state.cast = await api(`/api/cast/design?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ char, design }) });
    state.editDesign = null;
    renderCast();
    toast('Voix changée : ▶ pour l’entendre (la première fois, ≈ 20 s)');
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function narratorCard() {
  const c = state.cast;
  const v = c.narrator_voice;
  return el(
    'div',
    { class: 'card who narrator-card' },
    el('div', { class: 'who-head' }, el('span', { class: 'avatar big narrator' }, icon('sparkles')), el('div', { class: 'name static' }, el('b', { text: 'Narrateur' }), el('span', { class: 'muted', text: 'Encadrés de narration, et les répliques sans personnage' }))),
    el(
      'div',
      { class: 'voice-row ok' },
      el('button', { type: 'button', class: 'play', 'aria-label': 'Écouter', onclick: (e) => playSample(e.currentTarget, { char: c.narrator }) }, icon('play')),
      c.qwen ? null : voiceSelect(v.name, (name) => setNarrator({ ...v, name })),
    ),
    designRow(c.narrator),
  );
}

function extrasCard() {
  const c = state.cast;
  if (!c.extras) return null;
  return el(
    'div',
    { class: 'card who narrator-card' },
    el('div', { class: 'who-head' }, el('span', { class: 'avatar big extra' }, icon('users')), el('div', { class: 'name static' }, el('b', { text: 'Figurants' }), el('span', { class: 'muted', text: 'Les personnages secondaires sans groupe (« Autre… » sur une réplique)' }))),
    Object.entries(c.extras).map(([k, x]) =>
      el(
        'div',
        { class: 'voice-row ok' },
        el('button', { type: 'button', class: 'play', 'aria-label': `Écouter ${x.label}`, onclick: (e) => playSample(e.currentTarget, { char: k }) }, icon('play')),
        el('span', { class: 'muted', text: x.label.replace('Figurant ', '') }),
        c.qwen ? null : voiceSelect(x.voice.name, (name) => setExtra(k, { ...x.voice, name })),
      ),
    ),
    Object.keys(c.extras).map((k) => designRow(k)),
  );
}

async function setExtra(extra, voice) {
  try {
    state.cast = await api(`/api/cast/extra?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ extra, voice }) });
    const card = [...document.querySelectorAll('.narrator-card')].find((n) => n.textContent.includes('Figurants'));
    card?.replaceWith(extrasCard());
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

async function setNarrator(voice) {
  try {
    state.cast = await api(`/api/cast/narrator?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ voice }) });
    renderCast();
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

async function proposeVoices() {
  if (!state.cast.gpt.configured) return openSettings();
  const id = state.chapter.id;
  try {
    const job = await api(`/api/cast/voices?id=${enc(id)}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    state.cast.job = job;
    renderCast();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function validateVoices() {
  const todo = state.cast.characters.filter((c) => c.voice && !c.voice_ok && !c.silent && c.faces.length);
  for (const c of todo) {
    try {
      state.cast = await api(`/api/cast/character?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ char: c.id, voice_ok: true }) });
    } catch {}
  }
  renderCast();
  toast(`${plural(todo.length, 'voix validée', 'voix validées')}`);
}

function voicesHead() {
  const c = state.cast;
  const pending = c.characters.filter((x) => x.voice && !x.voice_ok && !x.silent && x.faces.length).length;
  const busy = isRunning(castJob());
  return el(
    'div',
    { class: 'actions' },
    el('button', { type: 'button', class: 'pill', disabled: busy, title: c.gpt.configured ? 'GPT choisit une voix d’après le genre et le caractère (wiki) et ses répliques' : 'Colle d’abord la clé GPT', onclick: proposeVoices }, icon('sparkles'), 'Proposer les voix'),
    pending ? el('button', { type: 'button', class: 'pill accent', onclick: validateVoices }, icon('check'), `Valider les ${pending} voix`) : null,
  );
}

/* ---------- Émotion d'une réplique ---------- */

function emotionSelect(l) {
  const c = state.cast;
  return el(
    'select',
    { class: `chip-btn emotion${l.emotion && l.emotion !== 'neutral' ? ' set' : ''}`, title: 'Le ton de la réplique (vitesse, hauteur, volume de la voix)', 'aria-label': 'Émotion', onchange: (e) => setEmotion(l, e.target.value) },
    Object.entries(c.emotions).map(([k, label]) => el('option', { value: k, selected: k === (l.emotion || 'neutral'), text: `Ton : ${label}` })),
  );
}

async function setEmotion(l, emotion) {
  try {
    state.cast = await api(`/api/review/emotion?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify({ key: l.key, emotion }) });
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

/* ---------- Écran Relecture (propositions de GPT) ---------- */

const FIELD_TITLES = {
  text: ['Texte corrigé', 'Erreur de lecture corrigée (par GPT, ou en local : mots collés, lettre perdue). La version acceptée est celle que la voix lira.'],
  kind: ['Type de bulle', 'Réplique, pensée, narration, bruitage… La narration est lue par le narrateur ; un bruitage n’est pas lu.'],
  speaker: ['Qui parle', 'Le personnage que GPT pense entendre, d’après la scène et les visages autour.'],
};

async function openReview() {
  const id = state.chapter.id;
  $('#view').replaceChildren(el('div', { class: 'head', id: 'head' }), el('div', { id: 'review' }, el('div', { class: 'skeleton short' })));
  state.review = null;
  state.bubbles = null;
  renderHead();
  try {
    const r = await api(`/api/review?id=${enc(id)}`);
    if (state.chapter?.id !== id || state.screen !== 'review') return;
    state.review = r;
    renderReview();
    if (state.reviewMode === 'all') await openBubbles();
    focusFrameRow();
  } catch (e) {
    $('#review').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Impossible d’ouvrir la relecture : ${e.message}` })));
  }
}

const reviewJob = () => findEpisode(state.current)?.job || state.review?.job;

async function runReview() {
  if (!state.review.gpt.configured) return openSettings();
  const id = state.chapter.id;
  try {
    const job = await api(`/api/review/run?id=${enc(id)}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    state.review.job = job;
    renderReview();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function reviewModes() {
  const r = state.review;
  const pending = r.items.filter((x) => x.state === 'pending').length;
  const todo = state.bubbles ? state.bubbles.filter((b) => !b.checked).length : null;
  const set = (mode) => {
    state.reviewMode = mode;
    if (mode === 'all' && !state.bubbles) return openBubbles();
    renderReview();
  };
  return el(
    'div',
    { class: 'tabs small review-modes' },
    [
      ['proposals', `Propositions · ${pending} à décider`],
      ['all', todo == null ? 'Toutes les bulles' : `Toutes les bulles · ${todo} à vérifier`],
    ].map(([key, label]) => el('button', { type: 'button', class: state.reviewMode === key ? 'on' : '', onclick: () => set(key) }, label)),
  );
}

async function openBubbles() {
  const id = state.chapter.id;
  try {
    const res = await api(`/api/bubbles?id=${enc(id)}`);
    if (state.chapter?.id !== id) return;
    state.bubbles = res.bubbles;
    // filigranes, crédits, titres, numéros : repérés tout seuls et jamais lus, pas besoin de les vérifier
    state.bubbleKeys = new Set(res.bubbles.filter((b) => !b.checked && !AUTO_KINDS[b.kind]).map((b) => b.key));
    renderReview();
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function bubblesSection() {
  // chaque bulle du chapitre, une à une : son vrai texte, son vrai type, « c'est bon »
  const all = state.bubbles;
  const queue = all.filter((b) => state.bubbleKeys.has(b.key));
  const rest = all.filter((b) => !state.bubbleKeys.has(b.key));
  return el(
    'section',
    { class: 'cast-block', id: 'bubble-block' },
    el('div', { class: 'block-head' },
      el('h3', { text: `Toutes les bulles · ${queue.length} à vérifier` }),
      el('p', { class: 'muted', text: 'Corrige le texte si la lecture s’est trompée, choisis le type (une pensée, un encadré de narration, un bruitage…), puis « C’est bon » (ou Entrée). La bulle se range en bas au bout de 2 secondes (tant que ta souris bouge dessus, elle attend) et la suivante arrive, son « C’est bon » sous ta souris. Ce que tu vérifies ici sert aussi de référence pour mesurer la machine.' })),
    el('div', { class: 'bar' }, el('span', { style: `width:${all.length ? (100 * rest.length) / all.length : 0}%` })),
    queue.length
      ? el('div', { class: 'lines queue', id: 'bubble-queue' }, queue.map(bubbleRow))
      : el('div', { class: 'notice queue-empty' }, icon('check'), el('p', { text: 'Toutes les bulles sont vérifiées. Pour changer d’avis : la liste juste dessous.' })),
    doneList('bubble-done', `Déjà vérifiées · ${rest.length}`, rest.map(bubbleRow)),
  );
}

const AUTO_KINDS = { watermark: 'filigrane du site', credit: 'crédits', title: 'titre du chapitre', number: 'numéro', silent: 'ponctuation seule' };

function bubbleRow(b) {
  const r = state.review;
  const view = reviewView(b, 0.5);
  const done = !state.bubbleKeys.has(b.key);
  const text = el('textarea', { class: 'field bubble-text', rows: 2, spellcheck: 'false', text: b.text, 'aria-label': 'Texte de la bulle' });
  text.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      checkBubble(b, { text: text.value, checked: true });
    }
  });
  const kinds = el('div', { class: 'who-chips' },
    Object.entries(r.kinds).map(([k, label]) =>
      el('button', { type: 'button', class: `chip-btn plain${b.kind === k ? ' on' : ''}`, onclick: () => checkBubble(b, { kind: k, text: text.value }) }, label)),
    r.kinds[b.kind] ? null : el('span', { class: 'chip', title: 'Repéré tout seul, jamais lu par la voix', text: AUTO_KINDS[b.kind] || b.kind }));
  return el(
    'div',
    { class: `line-row bubble-row${done ? ' done' : ''}`, 'data-key': b.key },
    reviewShot(b, view, 360),
    el('div', { class: 'line-body' },
      b.orig !== b.text ? el('p', { class: 'muted small', text: `Lu sur l’image : ${b.orig}` }) : null,
      text,
      kinds,
      el('div', { class: 'who-chips' },
        done
          ? [el('span', { class: 'state-badge accepted' }, icon('check'), b.checked ? 'Vérifiée' : 'Repérée toute seule'),
             el('button', { type: 'button', class: 'link quiet', onclick: () => checkBubble(b, { checked: false }) }, 'Remettre à vérifier')]
          : el('button', { type: 'button', class: 'pill accent', onclick: () => checkBubble(b, { text: text.value, checked: true }) }, icon('check'), 'C’est bon'))),
  );
}

async function checkBubble(b, changes) {
  const id = state.chapter.id;
  const body = { key: b.key, ...changes };
  if (body.text != null && body.text.trim() === b.text) delete body.text; // rien de changé dans le texte
  try {
    const res = await api(`/api/bubbles/check?id=${enc(id)}`, { method: 'POST', body: JSON.stringify(body) });
    if (state.chapter?.id !== id) return;
    state.bubbles = res.bubbles;
    if (changes.checked === false) {
      state.bubbleKeys.add(b.key);
      return renderReview();
    }
    const fresh = res.bubbles.find((x) => x.key === b.key);
    document.querySelector(`#bubble-block .line-row[data-key="${CSS.escape(b.key)}"]`)?.replaceWith(bubbleRow(fresh));
    if (changes.checked && state.bubbleKeys.has(b.key))
      settle(b.key, SETTLE, () => {
        state.bubbleKeys.delete(b.key);
        afterSettle(b.key, bubblesSection());
        const tabs = $('.review-modes');
        tabs?.replaceWith(reviewModes());
        // la suivante est prête à corriger au clavier
        $('#bubble-queue .bubble-text')?.focus({ preventScroll: true });
      });
    if (body.text != null || body.kind) state.review = await api(`/api/review?id=${enc(id)}`);
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

function renderReview() {
  const box = $('#review');
  const r = state.review;
  if (!box || !r) return;
  renderHead();
  if (state.reviewMode === 'all' && state.bubbles) {
    box.replaceChildren(reviewModes(), bubblesSection());
    return;
  }
  const job = reviewJob();
  const parts = [reviewModes()];
  if (job?.kind === 'review' && (isRunning(job) || job.status === 'error')) parts.push(jobCard(job));
  if (!r.gpt.configured) {
    parts.push(el('div', { class: 'notice' }, icon('alert'), el('p', {}, 'Pas de clé GPT. ', el('button', { type: 'button', class: 'link', onclick: openSettings }, 'Colle-la ici'), ' (elle reste sur ton ordinateur, dans .env).')));
  } else if (!r.ocr_done) {
    parts.push(el('div', { class: 'notice' }, icon('alert'), el('p', { text: 'Crée d’abord la vidéo depuis l’onglet Découpe : GPT relit le texte lu.' })));
  } else if (!r.done && !isRunning(job)) {
    parts.push(
      el('div', { class: 'card intro-card' },
        el('h3', { text: 'Relecture par GPT' }),
        el('p', { text: 'GPT relit tout le chapitre : il corrige les erreurs de lecture, dit si une bulle est une réplique, une pensée, de la narration ou un bruitage, propose qui parle et note le ton de chaque réplique. Rien ne change sans ton accord, sauf le ton (modifiable dans Personnages). Environ 3 minutes.' }),
        el('button', { type: 'button', class: 'pill accent', onclick: runReview }, icon('sparkles'), 'Relire le chapitre')),
    );
  }
  if (r.items.length) {
    const pending = r.items.filter((x) => x.state === 'pending');
    const rank = (x) => {
      const i = state.reviewRecent.indexOf(`${x.key}:${x.field}`);
      return i < 0 ? 1e9 : i;
    };
    const decided = r.items.filter((x) => x.state !== 'pending').sort((a, b) => rank(a) - rank(b));
    const yes = decided.filter((x) => x.state === 'accepted').length;
    parts.push(
      pending.length
        ? reviewFocus(pending[0], pending.length)
        : el('div', { class: 'notice' }, icon('check'), el('p', { text: `Tout est décidé : ${yes} acceptées, ${decided.length - yes} refusées. Pour changer d’avis : la liste juste dessous.` })),
      doneList('review-done', `Déjà décidées · ${yes} acceptées, ${decided.length - yes} refusées`, decided.map(reviewRow)),
    );
  }
  if (r.done && !r.items.length) parts.push(el('div', { class: 'notice' }, icon('check'), el('p', { text: 'GPT n’a rien trouvé à corriger.' })));
  box.replaceChildren(...parts);
}

function reviewView(item, ratio) {
  const [, , w] = item.crop;
  const cy = item.box[1] + item.box[3] / 2;
  const h = Math.min(item.crop[3], Math.round(ratio * w));
  return [0, Math.max(0, Math.min(item.crop[3] - h, Math.round(cy - h / 2))), w, h];
}

function reviewShot(item, view, width) {
  return el(
    'div',
    { class: 'shot', style: `aspect-ratio:${view[2]}/${view[3]}`, onmouseenter: (e) => showContext(e.currentTarget, item.crop, [['bubble-box', item.box]]), onmouseleave: hidePeek },
    el('img', { src: `/api/crop?id=${enc(state.chapter.id)}&frame=${enc(item.frame)}&y=${view[1]}&h=${view[3]}&w=${width}`, alt: '', loading: 'lazy' }),
    el('span', { class: 'bubble-box', style: boxStyle(item.box, view) }),
  );
}

const reviewLabel = (item, v) => (item.field === 'kind' ? state.review.kinds[v] || v : v ?? '—');

function reviewChange(item) {
  if (item.field === 'text') return el('div', { class: 'diff' }, el('p', { class: 'old', text: item.old }), el('p', { class: 'new' }, ...diffWords(item.old, item.new)));
  return [el('p', { class: 'quote' }, `« ${item.text} »`), el('p', { class: 'change' }, el('span', { class: 'muted', text: reviewLabel(item, item.old) }), ' → ', el('b', { text: reviewLabel(item, item.new) }))];
}

function reviewFocus(item, left) {
  // la proposition à décider, seule et en grand : Accepter / Refuser, et la suivante arrive à sa place
  const r = state.review;
  const [title, help] = FIELD_TITLES[item.field];
  const id = `${item.key}:${item.field}`;
  const editing = state.editing === id;
  const pending = r.items.filter((x) => x.state === 'pending');
  let body;
  if (editing) {
    body = [
      el('p', { class: 'muted', text: 'Lu sur l’image :' }),
      el('p', { class: 'old-plain', text: item.old }),
      el('textarea', { class: 'field edit-text', id: 'edit-text', rows: 3, spellcheck: 'false', text: item.new }),
    ];
  } else body = [reviewChange(item)];
  const kinds = item.field === 'kind' && !editing
    ? el('div', { class: 'who-chips' }, el('span', { class: 'muted', text: 'Ou plutôt :' }),
        Object.entries(r.kinds).filter(([k]) => k !== item.new && k !== item.old).map(([k, label]) => el('button', { type: 'button', class: 'chip-btn plain', onclick: () => decideOne(item, 'accepted', k) }, label)))
    : null;
  const key = (k) => el('kbd', { text: k });
  return el(
    'div',
    { class: 'card review-focus', 'data-key': id },
    el('div', { class: 'focus-head' },
      el('span', { class: 'chip', text: title }),
      el('span', { class: `chip source ${item.by}`, text: { local: 'Correction locale', gpt: 'GPT', mine: 'Ta version' }[item.by] || 'GPT' }),
      el('span', { class: 'muted grow', text: `${plural(left, 'proposition', 'propositions')} à décider` }),
      el('button', { type: 'button', class: 'link quiet', onclick: () => decide(pending, 'accepted') }, `Tout accepter (${pending.length})`)),
    el('div', { class: 'focus-body' },
      reviewShot(item, reviewView(item, 0.75), 720),
      el('div', { class: 'line-body' }, body, kinds, el('p', { class: 'muted small', text: help }))),
    el('div', { class: 'focus-actions' },
      editing
        ? [
            el('button', { type: 'button', class: 'pill big', onclick: () => { state.editing = null; renderReview(); } }, 'Annuler'),
            el('button', { type: 'button', class: 'pill accent big', onclick: saveEdit }, icon('check'), 'Valider ma version', key('Entrée')),
          ]
        : [
            el('button', { type: 'button', class: 'pill big', title: 'Ce n’est pas du texte (bruit, lettres du dessin) : la bulle n’est pas lue', onclick: () => notText(item) }, 'Pas du texte', key('N')),
            el('button', { type: 'button', class: 'pill big', onclick: () => decideOne(item, 'rejected') }, icon('x'), 'Refuser', key('R')),
            item.field === 'text' ? el('button', { type: 'button', class: 'pill big', onclick: () => editItem(item) }, icon('edit'), 'Corriger moi-même', key('E')) : null,
            el('button', { type: 'button', class: 'pill accent big', onclick: () => decideOne(item, 'accepted') }, icon('check'), 'Accepter', key('A')),
          ]),
  );
}

async function notText(item) {
  // la bulle n'est pas du texte : elle n'est plus lue, et ses autres propositions tombent
  const id = state.chapter.id;
  try {
    await api(`/api/bubbles/check?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ key: item.key, kind: 'noise', checked: true }) });
    state.review = await api(`/api/review?id=${enc(id)}`);
    state.bubbles = null;
    renderReview();
    toast(`« ${item.text.slice(0, 30)} » : pas du texte, plus lu`, { label: 'Annuler', run: async () => {
      await api(`/api/bubbles/check?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ key: item.key, kind: item.field === 'kind' ? item.old : 'dialogue', checked: false }) });
      state.review = await api(`/api/review?id=${enc(id)}`);
      renderReview();
    } });
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

function editItem(item) {
  state.editing = `${item.key}:${item.field}`;
  renderReview();
  const box = $('#edit-text');
  box?.focus();
  box?.setSelectionRange(box.value.length, box.value.length);
}

function saveEdit() {
  const item = currentReviewItem();
  const value = $('#edit-text')?.value.trim();
  if (!item || !value) return;
  decideOne(item, 'accepted', value);
}

function currentReviewItem() {
  return state.review?.items.find((x) => x.state === 'pending') || null;
}

function reviewRow(item) {
  // une proposition déjà décidée : son état en clair, et de quoi changer d'avis
  const view = reviewView(item, 0.55);
  const accepted = item.state === 'accepted';
  return el(
    'div',
    { class: `line-row review ${item.state}`, 'data-key': `${item.key}:${item.field}` },
    reviewShot(item, view, 360),
    el('div', { class: 'line-body' },
      reviewChange(item),
      el('div', { class: 'who-chips' },
        item.state === 'pending'
          ? [el('button', { type: 'button', class: 'chip-btn plain', onclick: () => decideOne(item, 'accepted') }, icon('check'), 'Accepter'),
             el('button', { type: 'button', class: 'chip-btn plain', onclick: () => decideOne(item, 'rejected') }, icon('x'), 'Refuser')]
          : [el('span', { class: `state-badge ${item.state}` }, icon(accepted ? 'check' : 'x'), accepted ? (item.auto ? 'Acceptée d’office' : 'Acceptée') : 'Refusée (on garde l’original)'),
             el('button', { type: 'button', class: 'link quiet', onclick: () => decideOne(item, accepted ? 'rejected' : 'accepted') }, accepted ? 'Refuser plutôt' : 'Accepter plutôt'),
             el('button', { type: 'button', class: 'link quiet', onclick: () => decideOne(item, 'pending') }, 'Remettre à décider')])),
  );
}

async function decideOne(item, stateName, value) {
  // tout de suite à l'écran (la suivante arrive), enregistré derrière
  const id = state.chapter.id;
  const before = { state: item.state, new: item.new };
  const tag = `${item.key}:${item.field}`;
  item.state = stateName;
  if (value != null) item.new = value;
  state.editing = null;
  state.reviewRecent = [tag, ...state.reviewRecent.filter((k) => k !== tag)];
  const top = $('main').scrollTop;
  renderReview();
  $('main').scrollTop = top;
  if (stateName !== 'pending') toast(`${stateName === 'accepted' ? 'Acceptée' : 'Refusée'} : « ${item.text.slice(0, 30)}${item.text.length > 30 ? '…' : ''} »`, { label: 'Annuler', run: () => decideOne(item, 'pending') });
  state.reviewInflight += 1;
  try {
    const res = await api(`/api/review/decide?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ decisions: [{ key: item.key, field: item.field, state: stateName, ...(value != null ? { value } : {}) }] }) });
    state.reviewInflight -= 1;
    if (state.chapter?.id !== id || state.reviewInflight) return; // d'autres clics suivent : on attend le dernier
    state.review = res;
    renderHead();
  } catch (e) {
    state.reviewInflight -= 1;
    item.state = before.state;
    item.new = before.new;
    if (state.screen === 'review') renderReview();
    toast(`Non enregistré : ${e.message}`);
  }
}

document.addEventListener('keydown', (e) => {
  // relecture au clavier : A accepter, R refuser, E corriger soi-même
  if (state.screen !== 'review' || state.reviewMode !== 'proposals' || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.id === 'edit-text') {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      saveEdit();
    } else if (e.key === 'Escape') {
      state.editing = null;
      renderReview();
    }
    return;
  }
  if (e.target.closest('input, textarea, select')) return;
  const item = currentReviewItem();
  if (!item || state.editing) return;
  const k = e.key.toLowerCase();
  if (k === 'a' || k === 'enter') decideOne(item, 'accepted');
  else if (k === 'r') decideOne(item, 'rejected');
  else if (k === 'n') notText(item);
  else if (k === 'e' && item.field === 'text') editItem(item);
  else return;
  e.preventDefault();
});

function diffWords(a, b) {
  // les mots nouveaux en couleur : on voit tout de suite ce que GPT a changé
  const before = new Set(String(a || '').split(/\s+/));
  return String(b || '').split(/(\s+)/).map((w) => (w.trim() && !before.has(w) ? el('mark', { text: w }) : w));
}

async function decide(items, stateName) {
  const id = state.chapter.id;
  try {
    const res = await api(`/api/review/decide?id=${enc(id)}`, { method: 'POST', body: JSON.stringify({ decisions: items.map((x) => ({ key: x.key, field: x.field, state: stateName })) }) });
    if (state.chapter?.id !== id) return;
    state.review = res;
    const top = $('main').scrollTop;
    renderReview();
    $('main').scrollTop = top;
    if (items.length > 1) toast(`${items.length} ${stateName === 'accepted' ? 'acceptées' : 'refusées'}`, { label: 'Annuler', run: () => decide(items, 'pending') });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function onReviewJob(before, after) {
  if (isRunning(after)) {
    const card = $('#job-card');
    if (card && after.kind === 'review') card.replaceWith(jobCard(after));
    else renderReview();
    return;
  }
  if (isRunning(before)) {
    try {
      const r = await api(`/api/review?id=${enc(state.chapter.id)}`);
      if (state.screen === 'review') {
        state.review = r;
        renderReview();
      }
    } catch {}
  }
}

/* ---------- Réglages : la clé GPT (change chaque jour) ---------- */

async function openSettings() {
  let s;
  try {
    s = (await api('/api/settings')).gpt;
  } catch (e) {
    return toast(`Réglages indisponibles : ${e.message}`);
  }
  $('#settings')?.remove();
  const status = el('p', { class: 'muted', text: s.configured ? `Clé enregistrée : ${s.key_hint}` : 'Aucune clé enregistrée.' });
  const base = el('input', { class: 'field', value: s.base, placeholder: 'https://…/v1', spellcheck: 'false' });
  const model = el('input', { class: 'field', value: s.model, placeholder: 'gpt-4.1', spellcheck: 'false' });
  const key = el('input', { class: 'field', type: 'password', placeholder: s.gpt_configured ? 'Nouvelle clé (laisser vide pour garder l’actuelle)' : 'Colle ta clé ici', autocomplete: 'off', spellcheck: 'false' });
  const claude = el('input', { class: 'field', type: 'password', placeholder: s.claude?.configured ? `Enregistrée : ${s.claude.key_hint} (laisser vide pour la garder)` : 'Clé Anthropic (sk-ant-…), facultative', autocomplete: 'off', spellcheck: 'false' });
  const close = () => $('#settings')?.remove();
  const save = async () => {
    try {
      const res = await api('/api/settings/gpt', { method: 'PUT', body: JSON.stringify({ base: base.value, model: model.value, key: key.value, claude_key: claude.value }) });
      key.value = '';
      claude.value = '';
      status.textContent = `Enregistré : ${res.gpt.key_hint}. Test…`;
      await api('/api/settings/gpt/test', { method: 'POST' });
      status.textContent = `Clé enregistrée et testée : ${res.gpt.key_hint} ✓`;
      if (state.cast) state.cast.gpt = res.gpt;
      if (state.review) state.review.gpt = res.gpt;
    } catch (e) {
      status.textContent = e.message;
    }
  };
  document.body.append(
    el('div', { id: 'settings', class: 'modal', onclick: (e) => e.target.id === 'settings' && close() },
      el('div', { class: 'card modal-card' },
        el('h3', { text: 'Réglages · GPT' }),
        el('p', { class: 'muted', text: 'Tout reste sur ton ordinateur, dans le fichier .env (jamais envoyé sur GitHub). La clé change chaque jour : colle la nouvelle ici.' }),
        el('label', {}, 'Adresse du proxy', base),
        el('label', {}, 'Modèle', model),
        el('label', {}, 'Clé', key),
        el('p', { class: 'muted', text: `Sans clé GPT (ou si elle a expiré), Claude prend le relais (${s.claude?.model || 'claude-haiku-5-5'}). Sa clé se crée sur console.anthropic.com.` }),
        el('label', {}, 'Clé Claude (secours)', claude),
        status,
        el('div', { class: 'actions', style: 'justify-content:flex-end' },
          el('button', { type: 'button', class: 'pill', onclick: close }, 'Fermer'),
          el('button', { type: 'button', class: 'pill accent', onclick: save }, icon('check'), 'Enregistrer et tester')))),
  );
  (s.configured ? key : base.value ? key : base).focus();
}

/* ---------- Écran Sons : un son pour chaque bruitage, et la musique ---------- */

async function openSounds() {
  const id = state.chapter.id;
  $('#view').replaceChildren(el('div', { class: 'head', id: 'head' }), el('div', { id: 'sounds' }, el('div', { class: 'skeleton short' })));
  state.sounds = null;
  renderHead();
  try {
    const s = await api(`/api/sounds?id=${enc(id)}`);
    if (state.chapter?.id !== id || state.screen !== 'sounds') return;
    if (state.focusFrame) {
      // venu d'ailleurs (« Corriger » depuis la vidéo) : la case visée, en grand
      const hit = [...s.spots, ...s.actions].find((x) => x.frame === state.focusFrame);
      state.soundFocus = hit?.key || null;
      state.focusFrame = null;
    }
    setSounds(s, true);
  } catch (e) {
    $('#sounds').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Impossible d’ouvrir les sons : ${e.message}` })));
  }
}

function soundItems() {
  const s = state.sounds;
  const order = (x) => `${x.frame}:${x.key.startsWith('frame:') ? 1 : 0}`;
  return [...s.spots, ...s.actions].sort((a, b) => order(a).localeCompare(order(b)));
}

function setSounds(s, fresh = false) {
  state.sounds = s;
  if (fresh) state.soundKeys = new Set([...s.spots, ...s.actions].filter((x) => !x.chosen).map((x) => x.key));
  // première visite : on regarde ce que montrent les cases (en local, ≈ 15 s), sans clic à faire
  const id = state.chapter.id;
  const job = findEpisode(id)?.job || s.job;
  if (s.ocr_done && !isRunning(job) && !state.autoScene.has(id) && (!s.scene_done || (!s.understood && s.gpt.configured))) {
    state.autoScene.add(id);
    if (s.gpt.configured && !s.understood) suggestSounds();
    else lookAtPanels();
  }
  renderSounds();
}

async function lookAtPanels() {
  const id = state.chapter.id;
  try {
    const job = await api(`/api/sounds/scene?id=${enc(id)}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    if (state.sounds) state.sounds.job = job;
    renderSounds();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible de regarder les cases : ${e.message}`);
  }
}

function playUrl(button, url) {
  if (playing === button && !player.paused) {
    player.pause();
    button.classList.remove('on');
    playing = null;
    return;
  }
  playing?.classList.remove('on');
  playing = button;
  button?.classList.add('on');
  player.src = url;
  player.play().catch(() => toast('Lecture impossible'));
  player.onended = () => {
    button?.classList.remove('on');
    playing = null;
  };
}

function renderSounds() {
  const box = $('#sounds');
  const s = state.sounds;
  if (!box || !s) return;
  renderHead();
  const parts = [];
  const job = findEpisode(state.current)?.job || s.job;
  const busy = isRunning(job);
  if (['sounds', 'scene', 'understand'].includes(job?.kind) && (busy || job.status === 'error')) parts.push(jobCard(job));
  if (!s.ocr_done) {
    parts.push(el('div', { class: 'notice' }, icon('alert'), el('p', { text: 'Crée d’abord la vidéo : les bruitages sont repérés à la lecture du texte.' })));
    return box.replaceChildren(...parts);
  }
  if (!s.understood && !busy)
    parts.push(el('div', { class: 'notice' }, icon('sparkles'),
      el('p', { class: 'grow', text: s.gpt.configured
        ? `Je peux regarder ce qui se passe dans chaque case (${s.vision === 'local' ? 'en local, ≈ 10 min pour un épisode' : 'avec GPT'}), puis choisir les sons d’après l’histoire : un coup contre un mur, une lame qu’on dégaine, du sang…`
        : 'Pour des sons choisis d’après ce qui se passe dans chaque case, colle la clé GPT (Réglages). En attendant : d’après ce que montre l’image.' }),
      s.gpt.configured ? el('button', { type: 'button', class: 'pill accent', onclick: suggestSounds }, icon('sparkles'), 'Comprendre les cases') : null));
  parts.push(soundStrip(), soundStage(), musicCard(s));
  box.replaceChildren(...parts);
  $('#sound-strip .on')?.scrollIntoView({ block: 'nearest', inline: 'center' });
}

function musicCard(s) {
  return el(
    'div',
    { class: 'card music-card' },
    el('button', { type: 'button', class: 'play', 'aria-label': 'Écouter la musique', disabled: !s.music, onclick: (e) => playUrl(e.currentTarget, '/api/music') }, icon('play')),
    el('div', { class: 'grow' },
      el('b', { text: s.moods ? 'Musique selon l’ambiance : calme, tension, combat, tristesse' : s.music ? `Musique de fond : ${s.music}` : 'Pas de musique de fond' }),
      el('p', { class: 'muted', text: s.moods
        ? 'Elle change avec la scène et baisse quand on parle. Tes morceaux : un MP3 dans music/calm/, music/tension/, music/combat/ ou music/sad/.'
        : 'Elle tourne en boucle et baisse quand on parle. Pour la changer : un MP3 dans le dossier music/ du projet.' })),
  );
}

const soundName = (value) => {
  const s = state.sounds;
  const layers = String(value || '').split('+').filter((c) => s.categories[c]);
  return layers.length ? layers.map((c) => s.categories[c]).join(' + ') : 'Aucun son';
};

function soundCurrent() {
  // la case affichée : celle qu'on a ouverte, sinon la première à choisir
  const items = soundItems();
  const focus = items.find((x) => x.key === state.soundFocus);
  return focus || items.find((x) => state.soundKeys.has(x.key)) || null;
}

function soundStrip() {
  // la bande-son de l'épisode : chaque case qui peut avoir un son, dans l'ordre ; un clic l'ouvre
  const s = state.sounds;
  const items = soundItems();
  const current = soundCurrent();
  return el(
    'div',
    { class: 'card strip-card' },
    el('div', { class: 'focus-head' },
      el('b', { text: 'La bande-son de l’épisode' }),
      el('span', { class: 'muted grow', text: `${items.length - state.soundKeys.size} / ${items.length} choisis · ${items.filter((x) => (state.soundKeys.has(x.key) ? x.proposed : x.sound) !== s.none).length} avec un son` }),
      el('span', { class: 'legend' }, el('i', { class: 'todo' }), 'à choisir', el('i', { class: 'done' }), 'choisi', el('i', { class: 'none' }), 'sans son')),
    el('div', { class: 'sound-strip', id: 'sound-strip' },
      items.map((x) => {
        const todo = state.soundKeys.has(x.key) && !x.chosen;
        const value = todo ? x.proposed : x.sound;
        const [, , w, ch] = x.crop;
        const h = Math.min(ch, Math.round(1.3 * w));
        const cy = x.box ? x.box[1] + x.box[3] / 2 : ch / 2;
        const y = Math.max(0, Math.min(ch - h, Math.round(cy - h / 2)));
        return el('button', {
          type: 'button',
          class: `strip-item ${todo ? 'todo' : value === s.none ? 'none' : 'done'}${current?.key === x.key ? ' on' : ''}`,
          title: `${x.text ? `« ${x.text} »` : `Case ${x.index + 1}`} : ${soundName(value)}${todo ? ' (proposé)' : ''}`,
          onclick: () => {
            const here = soundCurrent();
            if (here && settleTimers.has(here.key)) {
              unsettle(here.key);
              state.soundKeys.delete(here.key);
            }
            state.soundFocus = x.key;
            state.soundLib = false;
            renderSounds();
          },
        },
          el('img', { src: `/api/crop?id=${enc(state.chapter.id)}&frame=${enc(x.frame)}&y=${y}&h=${h}&w=120`, alt: '', loading: 'lazy' }),
          el('span', { text: value === s.none ? '—' : soundName(value).split(' + ').map((n) => n.split(/[ ,]/)[0]).join(' + ') }));
      })),
  );
}

function soundStage() {
  const s = state.sounds;
  const item = soundCurrent();
  if (!item)
    return el('div', { class: 'notice queue-empty' }, icon('check'),
      el('p', { text: 'Toutes les cases ont leur son (ou rien). Pour changer d’avis : clique sur une case dans la bande-son.' }));
  return el('div', { class: 'queue', id: 'sound-queue' }, soundFocusCard(item));
}

function soundFocusCard(item) {
  const s = state.sounds;
  const todo = state.soundKeys.has(item.key) && !item.chosen;
  const leaving = state.soundKeys.has(item.key) && item.chosen; // choisi à l'instant : la suivante arrive
  const value = todo ? item.proposed : item.sound;
  const layers = value === s.none ? [] : value.split('+');
  const left = state.soundKeys.size;
  const [, , w, ch] = item.crop;
  const h = Math.min(ch, Math.round((item.box ? 1.0 : 1.6) * w));
  const cy = item.box ? item.box[1] + item.box[3] / 2 : ch / 2;
  const view = [0, Math.max(0, Math.min(ch - h, Math.round(cy - h / 2))), w, h];
  const seed = item.text || item.frame;
  const key = (k) => el('kbd', { text: k });
  const ideas = [...new Set([...item.recs, ...(todo ? [] : layers)])].filter((c) => !layers.includes(c)).slice(0, 4);
  const chip = (cat) =>
    el('span', { class: 'chip-pair' },
      el('button', { type: 'button', class: 'chip-btn plain', title: 'Écouter et choisir ce son', onclick: () => chooseSound(item, cat) }, icon('play'), s.categories[cat]),
      layers.length === 1 && layers[0] !== cat
        ? el('button', { type: 'button', class: 'chip-btn plain add', title: `Les deux : ${s.categories[layers[0]]} + ${s.categories[cat]}`, onclick: () => chooseSound(item, `${layers[0]}+${cat}`) }, '+')
        : null);
  return el(
    'div',
    { class: 'card review-focus sound-focus', 'data-key': item.key },
    el('div', { class: 'focus-head' },
      el('span', { class: 'chip', text: `Case ${item.index + 1}` }),
      el('span', { class: 'chip', text: item.text ? `bruitage dessiné « ${item.text} »` : 'personne ne parle' }),
      el('span', { class: 'muted grow', text: todo || leaving ? `${plural(left, 'case', 'cases')} à choisir` : 'Déjà choisi : tu peux changer d’avis' }),
      todo && left > 1
        ? el('button', { type: 'button', class: 'link quiet', title: 'Garder toutes les propositions telles quelles', onclick: () => acceptActions(soundItems().filter((x) => state.soundKeys.has(x.key))) }, `Tout accepter (${left})`)
        : null),
    el('div', { class: 'focus-body' },
      el('div', { class: 'shot', style: `aspect-ratio:${view[2]}/${view[3]}`, onmouseenter: (e) => showContext(e.currentTarget, item.crop, item.box ? [['bubble-box', item.box]] : [['frame-box', [0, 0, w, ch]]]), onmouseleave: hidePeek },
        el('img', { src: `/api/crop?id=${enc(state.chapter.id)}&frame=${enc(item.frame)}&y=${view[1]}&h=${view[3]}&w=720`, alt: '' }),
        item.box ? el('span', { class: 'bubble-box', style: boxStyle(item.box, view) }) : null),
      el('div', { class: 'line-body' },
        el('p', { class: 'muted small', text: 'Ce qui se passe' }),
        el('p', { class: 'quote', text: item.what || (item.seen.length ? `Je vois : ${item.seen.join(', ')}` : s.scene_done ? 'Rien de bruyant sur l’image.' : '…') }),
        el('div', { class: `proposal${todo ? '' : ' mine'}` },
          el('p', { class: 'muted small', text: todo ? 'Proposé' : 'Ton choix' }),
          el('button', { type: 'button', class: 'proposal-sound', disabled: !layers.length, title: 'Écouter ce son seul', onclick: (e) => playUrl(e.currentTarget, `/api/sfx_sample?cat=${enc(value)}&text=${enc(seed)}&id=${enc(state.chapter.id)}&key=${enc(item.key)}`) },
            layers.length ? icon('play') : null, el('b', { text: soundName(value) })),
          todo && item.why ? el('p', { class: 'muted', text: item.why }) : null,
          layers.length && item.strength ? el('p', { class: 'muted small', text: `Volume : ${{ 1: 'doux', 2: 'normal', 3: 'fort' }[item.strength]}, selon la force du moment` }) : null),
        ideas.length ? el('p', { class: 'muted small', text: layers.length === 1 ? 'Ou plutôt (+ pour mettre les deux)' : 'Ou plutôt' }) : null,
        el('div', { class: 'who-chips' }, ideas.map(chip)),
        el('button', { type: 'button', class: 'link quiet', onclick: () => { state.soundLib = !state.soundLib; renderSounds(); } },
          icon(state.soundLib ? 'down' : 'plus'), state.soundLib ? 'Fermer la bibliothèque' : 'Tous les sons…'),
        state.soundLib
          ? el('div', { class: 'sound-library' },
              s.families.map(([name, cats]) => el('div', { class: 'family' },
                el('span', { class: 'muted small', text: name }),
                el('div', { class: 'who-chips' }, cats.filter((c) => s.categories[c]).map(chip)))))
          : null)),
    el('div', { class: 'focus-actions' },
      el('button', { type: 'button', class: 'pill big', title: 'Pas de bruitage sur cette case', onclick: () => chooseSound(item, s.none) }, 'Aucun son', key('N')),
      el('button', { type: 'button', class: 'pill big', disabled: !item.frame, title: 'La voix de la case et ce son, comme dans la vidéo', onclick: (e) => playUrl(e.currentTarget, `/api/sounds/preview?id=${enc(state.chapter.id)}&frame=${enc(item.frame)}&sound=${enc(value)}&seed=${enc(seed)}&key=${enc(item.key)}`) },
        icon('play'), 'Écouter avec la voix', key('Espace')),
      todo
        ? el('button', { type: 'button', class: 'pill accent big', onclick: () => chooseSound(item, value, { listen: false }) }, icon('check'), value === s.none ? 'Valider : aucun son' : 'Valider', key('Entrée'))
        : leaving
          ? el('button', { type: 'button', class: 'pill accent big', disabled: true }, icon('check'), 'Choisi')
          : el('button', { type: 'button', class: 'pill big', onclick: () => resetSound(item) }, 'Remettre à choisir')),
  );
}

async function sendSounds(choices) {
  state.sounds = await api(`/api/sounds?id=${enc(state.chapter.id)}`, { method: 'POST', body: JSON.stringify({ choices }) });
}

async function chooseSound(item, value, { listen = true } = {}) {
  // le son est choisi tout de suite ; la case suivante arrive au bout de 2 s (la souris qui bouge dessus la retient)
  const s = state.sounds;
  if (listen && value !== s.none) playUrl(null, `/api/sfx_sample?cat=${enc(value)}&text=${enc(item.text || item.frame)}&id=${enc(state.chapter.id)}&key=${enc(item.key)}`);
  const wasTodo = state.soundKeys.has(item.key);
  try {
    await sendSounds([{ key: item.key, sound: value }]);
    state.soundFocus = item.key;
    renderSounds();
    renderHead();
    if (wasTodo)
      settle(item.key, SETTLE, () => {
        state.soundKeys.delete(item.key);
        const next = soundItems().find((x) => state.soundKeys.has(x.key) && x.key !== item.key);
        state.soundFocus = next?.key || null;
        state.soundLib = false;
        renderSounds();
      }, { collapse: false });
  } catch (e) {
    toast(`Non enregistré : ${e.message}`);
  }
}

async function resetSound(item) {
  try {
    await sendSounds([{ key: item.key, sound: null }]);
    state.soundKeys.add(item.key);
    state.soundFocus = item.key;
    renderSounds();
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function stepSound(delta) {
  const items = soundItems();
  const at = items.indexOf(soundCurrent());
  const next = items[Math.max(0, Math.min(items.length - 1, at + delta))];
  if (!next) return;
  const here = soundCurrent();
  if (here && settleTimers.has(here.key)) {
    unsettle(here.key); // on part avant la fin des 2 s : le choix est gardé
    state.soundKeys.delete(here.key);
  }
  state.soundFocus = next.key;
  state.soundLib = false;
  renderSounds();
}

document.addEventListener('keydown', (e) => {
  // sons au clavier : Entrée valider, N aucun son, Espace écouter avec la voix, ← → case d'avant / d'après
  if (state.screen !== 'sounds' || !state.sounds || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest?.('input, textarea, select')) return;
  const item = soundCurrent();
  if (!item) return;
  const card = $('.sound-focus');
  const k = e.key.toLowerCase();
  if (k === 'enter' || k === 'a') {
    e.preventDefault();
    if (state.soundKeys.has(item.key) && !item.chosen) chooseSound(item, item.proposed, { listen: false });
  } else if (k === 'n') chooseSound(item, state.sounds.none);
  else if (k === ' ') {
    e.preventDefault();
    card?.querySelector('.focus-actions .pill:nth-child(2)')?.click();
  } else if (k === 'arrowright') stepSound(1);
  else if (k === 'arrowleft') stepSound(-1);
});

async function acceptActions(items) {
  try {
    await sendSounds(items.map((x) => ({ key: x.key, sound: x.proposed })));
    for (const x of items) state.soundKeys.delete(x.key);
    state.soundFocus = null;
    renderSounds();
    toast(`${plural(items.length, 'case validée', 'cases validées')} (${items.filter((x) => x.proposed !== state.sounds.none).length} avec un son)`, {
      label: 'Annuler',
      run: async () => {
        await sendSounds(items.map((x) => ({ key: x.key, sound: null })));
        for (const x of items) state.soundKeys.add(x.key);
        renderSounds();
      },
    });
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function suggestSounds() {
  if (!state.sounds.gpt.configured) return openSettings();
  const id = state.chapter.id;
  try {
    const job = await api(`/api/sounds/suggest?id=${enc(id)}`, { method: 'POST' });
    const ep = findEpisode(id);
    if (ep) ep.job = job;
    state.sounds.job = job;
    renderSounds();
    schedulePoll(500);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function onSoundsJob(before, after) {
  if (isRunning(after)) {
    const card = $('#job-card');
    if (card && ['sounds', 'scene', 'understand'].includes(after.kind)) card.replaceWith(jobCard(after));
    else renderSounds();
    return;
  }
  if (isRunning(before)) {
    try {
      const s = await api(`/api/sounds?id=${enc(state.chapter.id)}`);
      if (state.screen === 'sounds') setSounds(s, true);
    } catch {}
  }
}

/* ---------- Écran Vidéo : regarder, et signaler un passage raté ---------- */

const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

async function openVideo() {
  const id = state.chapter.id;
  $('#view').replaceChildren(el('div', { class: 'head', id: 'head' }), el('div', { id: 'videoscreen' }, el('div', { class: 'skeleton short' })));
  state.videoInfo = null;
  renderHead();
  try {
    const v = await api(`/api/video_info?id=${enc(id)}`);
    if (state.chapter?.id !== id || state.screen !== 'video') return;
    state.videoInfo = v;
    renderVideo();
  } catch (e) {
    $('#videoscreen').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Impossible d’ouvrir la vidéo : ${e.message}` })));
  }
}

function frameAt(t) {
  const tl = state.videoInfo?.timeline || [];
  let found = tl[0];
  for (const f of tl) if (f.start <= t + 1e-3) found = f;
  return found;
}

function renderVideo() {
  const box = $('#videoscreen');
  const v = state.videoInfo;
  if (!box || !v) return;
  renderHead();
  if (!v.video) {
    box.replaceChildren(el('div', { class: 'notice' }, icon('alert'), el('p', { text: 'Pas encore de vidéo : clique sur « Créer la vidéo ».' })));
    return;
  }
  const player = el('video', { id: 'player', src: `/api/video?id=${enc(state.chapter.id)}&v=${Date.now()}`, controls: true, preload: 'metadata', playsinline: true });
  player.addEventListener('timeupdate', () => renderNow(player.currentTime));
  player.addEventListener('seeked', () => renderNow(player.currentTime, true));
  box.replaceChildren(
    el('div', { class: 'video-layout' },
      el('div', { class: 'video-frame' }, player),
      el('div', { class: 'video-side' },
        el('div', { class: 'card', id: 'now' }),
        el('div', { class: 'card', id: 'checks' }),
        el('div', { class: 'card', id: 'parts' }),
        el('div', { class: 'card', id: 'flags' }))),
  );
  if (!v.timeline.length) {
    $('#now').replaceChildren(el('p', { class: 'muted', text: 'Recrée la vidéo une fois pour pouvoir signaler un passage précis (la nouvelle vidéo garde l’emplacement de chaque case).' }));
  } else renderNow(0, true);
  renderChecks();
  renderParts();
  renderFlags();
}

function renderParts() {
  // les parties de 60–90 s pour TikTok : la vidéo, le titre et les hashtags à copier
  const v = state.videoInfo;
  const card = $('#parts');
  if (!card) return;
  const job = findEpisode(state.current)?.job || v.job;
  const busy = isRunning(job);
  const id = state.chapter.id;
  const copy = async (p) => {
    try {
      await navigator.clipboard.writeText(`${p.title}\n${p.hashtags.join(' ')}`);
      toast('Titre et hashtags copiés');
    } catch {
      toast('Copie impossible : sélectionne le texte à la main');
    }
  };
  const make = async () => {
    try {
      const j = await api(`/api/parts?id=${enc(id)}`, { method: 'POST' });
      const ep = findEpisode(id);
      if (ep) ep.job = j;
      renderParts();
      schedulePoll(500);
    } catch (e) {
      toast(`Impossible : ${e.message}`);
    }
  };
  fill(card,
    el('div', { class: 'row-between' },
      el('h3', { text: v.parts.length ? `Parties pour TikTok · ${v.parts.length}` : 'Parties pour TikTok' }),
      el('button', { type: 'button', class: 'pill', disabled: busy, onclick: make }, busy && job?.kind === 'parts' ? el('span', { class: 'spinner' }) : icon('scissors'), v.parts.length ? 'Refaire' : 'Découper')),
    v.parts.length
      ? el('div', { class: 'flag-list' },
          v.parts.map((p, i) =>
            el('div', { class: 'part' },
              el('a', { class: 'link', href: `/api/part_video?id=${enc(id)}&k=${i + 1}`, target: '_blank', title: 'Ouvrir ou enregistrer la vidéo' }, `${i + 1} · ${fmtTime(p.start)}–${fmtTime(p.end)}`),
              el('div', { class: 'grow' }, el('b', { text: p.title }), el('p', { class: 'muted', text: p.hashtags.join(' ') })),
              el('button', { type: 'button', class: 'chip-btn plain', onclick: () => copy(p) }, 'Copier'))))
      : el('p', { class: 'muted', text: 'Coupe la vidéo en parties de 60 à 90 s, sur des moments de suspense, avec « PART 2/5 » à l’écran, un titre et des hashtags.' }),
  );
}

function renderChecks() {
  // ce que le Studio a trouvé seul : voix qui ne dit pas le texte, voix manquante, case trop courte ou trop longue
  const v = state.videoInfo;
  const card = $('#checks');
  if (!card) return;
  const where = { short: 'cut', long: 'cut', missing: 'cast', heard: 'review' };
  const go = (c) => {
    state.focusFrame = c.frame;
    if (c.kind === 'heard') {
      state.reviewMode = 'all'; // le texte lu, à corriger (ou « pas du texte ») sur la bulle même
      state.focusKey = c.key || null;
    }
    switchScreen(where[c.kind] || 'cast');
  };
  const auto = Object.entries(v.auto || {}).filter(([, n]) => n);
  fill(card,
    el('h3', { text: v.checks.length ? `Contrôle automatique · ${v.checks.length} à revoir` : 'Contrôle automatique' }),
    auto.length ? el('p', { class: 'muted', text: `Décidé d’office par la machine : ${auto.map(([k, n]) => `${n} ${k}`).join(', ')} (tout se change dans les onglets).` }) : null,
    v.checks.length
      ? el('div', { class: 'flag-list' },
          v.checks.map((c) =>
            el('div', { class: 'flag' },
              el('button', { type: 'button', class: 'link', title: 'Revoir ce passage', onclick: () => seek(c.t) }, fmtTime(c.t)),
              el('span', { class: 'grow', text: c.text }),
              el('button', { type: 'button', class: 'chip-btn plain', onclick: () => go(c) }, 'Corriger'))))
      : el('p', { class: 'muted', text: v.listened ? 'Rien à signaler : chaque réplique a été réécoutée et la voix dit bien ce qui est écrit.' : 'La voix sera réécoutée (Whisper, en local) à la prochaine création de la vidéo.' }),
  );
}

let nowFrame = null;
function renderNow(t, force = false) {
  const v = state.videoInfo;
  const f = frameAt(t);
  const card = $('#now');
  if (!card || !f || (!force && nowFrame === f.frame)) return;
  nowFrame = f.frame;
  fill(card,
    el('h3', { text: `En ce moment · case ${f.index + 1} / ${v.timeline.length}` }),
    f.lines.length
      ? el('div', { class: 'now-lines' }, f.lines.map((l) => el('p', {}, el('b', { text: `${l.speaker} ` }), el('span', { class: 'muted', text: `(${l.voice}${l.emotion && l.emotion !== 'neutre' ? ` · ${l.emotion}` : ''}) ` }), `« ${l.text} »`)))
      : el('p', { class: 'muted', text: 'Personne ne parle dans cette case.' }),
    f.sounds.length ? el('p', { class: 'muted', text: `Son : ${f.sounds.join(', ')}` }) : null,
    el('p', { class: 'muted', style: 'margin-top:10px', text: 'Quelque chose ne va pas ici ?' }),
    el('div', { class: 'who-chips' },
      Object.entries(v.reasons).map(([k, label]) => el('button', { type: 'button', class: 'chip-btn plain', onclick: () => addFlag(f, k) }, icon('alert'), label))),
  );
}

async function addFlag(f, reason) {
  const t = $('#player')?.currentTime || f.start;
  try {
    state.videoInfo = await api(`/api/flags?id=${enc(state.chapter.id)}`, { method: 'POST', body: JSON.stringify({ frame: f.frame, t, reason }) });
    renderFlags();
    toast(`Signalé : ${state.videoInfo.reasons[reason]} à ${fmtTime(t)}`);
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

async function updateFlag(flag, body) {
  try {
    state.videoInfo = await api(`/api/flags/${flag.id}?id=${enc(state.chapter.id)}`, { method: 'PUT', body: JSON.stringify(body) });
    renderFlags();
  } catch (e) {
    toast(`Impossible : ${e.message}`);
  }
}

function renderFlags() {
  const v = state.videoInfo;
  const card = $('#flags');
  if (!card) return;
  const todo = v.flags.filter((f) => !f.done).length;
  const indexOf = (file) => v.timeline.find((x) => x.frame === file)?.index;
  fill(card,
    el('h3', { text: v.flags.length ? `Passages signalés · ${todo} à corriger` : 'Passages signalés' }),
    v.flags.length
      ? el('div', { class: 'flag-list' },
          [...v.flags].sort((a, b) => a.done - b.done || a.t - b.t).map((flag) =>
            el('div', { class: `flag${flag.done ? ' done' : ''}` },
              el('button', { type: 'button', class: 'link', title: 'Revoir ce passage', onclick: () => seek(flag.t) }, fmtTime(flag.t)),
              el('span', { class: 'grow', text: `${v.reasons[flag.reason]} · case ${(indexOf(flag.frame) ?? 0) + 1}` }),
              flag.done ? null : el('button', { type: 'button', class: 'chip-btn plain', onclick: () => fixFlag(flag) }, 'Corriger'),
              el('button', { type: 'button', class: `chip-btn plain${flag.done ? ' on' : ''}`, onclick: () => updateFlag(flag, { done: !flag.done }) }, icon('check'), flag.done ? 'Fait' : 'Marquer fait'),
              el('button', { type: 'button', class: 'link quiet', title: 'Supprimer', 'aria-label': 'Supprimer', onclick: () => updateFlag(flag, { delete: true }) }, icon('x')))))
      : el('p', { class: 'muted', text: 'Regarde la vidéo ; si un passage cloche, clique sur la raison ci-dessus au bon moment. Tu le retrouveras ici, avec un bouton pour aller le corriger.' }),
    v.flags.length && !todo ? el('p', { class: 'muted', text: 'Tout est corrigé : clique sur « Créer la vidéo » pour la mettre à jour.' }) : null,
  );
}

function seek(t) {
  const p = $('#player');
  if (!p) return;
  p.currentTime = t;
  p.play().catch(() => {});
}

function fixFlag(flag) {
  // va à l'endroit à corriger : la réplique (voix, texte), le son, ou la case dans la découpe
  state.focusFrame = flag.frame;
  const screen = { voice: 'cast', text: 'review', sound: 'sounds', cut: 'cut', other: 'cast' }[flag.reason] || 'cast';
  if (flag.reason === 'text') state.reviewMode = 'all';
  switchScreen(screen);
}

function focusFrameRow() {
  // après l'ouverture d'un écran : défile jusqu'à la première ligne de la case visée et la fait clignoter
  const file = state.focusFrame;
  const key = state.focusKey;
  if (!file) return;
  state.focusFrame = null;
  state.focusKey = null;
  setTimeout(() => {
    const rows = [...document.querySelectorAll('.line-row[data-key]')];
    const row = (key && rows.find((r) => r.dataset.key === key)) || rows.find((r) => r.dataset.key.startsWith(`${file}#`) || r.dataset.key === `frame:${file}`);
    if (row) {
      const folded = row.closest('details');
      if (folded && !folded.open) folded.open = true;
      row.scrollIntoView({ block: 'center' });
      row.classList.remove('flash');
      void row.offsetWidth;
      row.classList.add('flash');
    } else if (state.screen === 'cut') {
      const frame = state.videoInfo?.timeline.find((x) => x.frame === file);
      if (frame?.crop) focusDoubt({ y: frame.crop[1] + frame.crop[3] / 2, kind: 'tall', panel: state.panels.find((p) => p.y0 <= frame.crop[1] + 2 && frame.crop[1] < p.y1) });
    } else toast('Cette case n’a rien à corriger ici');
  }, 400);
}

/* ---------- Tout en un clic : un lien → la vidéo ---------- */

function importCard() {
  const job = state.library?.import;
  const running = isRunning(job);
  if (!job || (!running && job.status !== 'error' && !(job.chapters || []).length)) return null;
  let text;
  if (running) text = job.step === 'download' ? 'Téléchargement… Si une fenêtre de navigateur demande une vérification, passe-la.' : 'En attente…';
  else if (job.status === 'error') text = `Import impossible : ${job.error}`;
  else text = `${plural(job.chapters.length, 'chapitre ajouté', 'chapitres ajoutés')} : la vidéo se fait toute seule (suis l’avancement ci-dessous).`;
  return el('div', { class: `import-card${job.status === 'error' ? ' error' : ''}` }, running ? el('span', { class: 'spinner' }) : icon(job.status === 'error' ? 'alert' : 'check'), el('p', { text }));
}

function openImport() {
  $('#import')?.remove();
  const url = el('input', { class: 'field', placeholder: 'https://… (la page de la série)', spellcheck: 'false' });
  const chapters = el('input', { class: 'field', placeholder: 'vide = le premier · 12 · 1-5 · latest', spellcheck: 'false' });
  const auto = el('input', { type: 'checkbox', checked: true });
  const status = el('p', { class: 'muted', text: '' });
  const close = () => $('#import')?.remove();
  const go = async () => {
    try {
      const job = await api('/api/import', { method: 'POST', body: JSON.stringify({ url: url.value, chapters: chapters.value, auto: auto.checked }) });
      state.library.import = job;
      close();
      renderLibrary();
      schedulePoll(800);
      toast('C’est parti : téléchargement, puis toute la vidéo');
    } catch (e) {
      status.textContent = e.message;
    }
  };
  document.body.append(
    el('div', { id: 'import', class: 'modal', onclick: (e) => e.target.id === 'import' && close() },
      el('div', { class: 'card modal-card' },
        el('h3', { text: 'Ajouter des chapitres' }),
        el('p', { class: 'muted', text: 'Colle le lien de la série : le Studio télécharge les chapitres, les découpe, lit le texte, cherche les personnages, fait relire par GPT, choisit les voix et les sons, puis crée la vidéo. Tu valideras ensuite dans les onglets.' }),
        el('label', {}, 'Lien de la série', url),
        el('label', {}, 'Chapitres', chapters),
        el('label', { class: 'check' }, auto, 'Tout faire (relecture GPT, voix, sons) — sinon seulement la vidéo de base'),
        status,
        el('div', { class: 'actions', style: 'justify-content:flex-end' },
          el('button', { type: 'button', class: 'pill', onclick: close }, 'Fermer'),
          el('button', { type: 'button', class: 'pill accent', onclick: go }, icon('sparkles'), 'Lancer')))),
  );
  url.focus();
}

async function runAuto() {
  const ch = state.chapter;
  if (ch.manual_frames && !confirm(`Remplacer les ${ch.manual_frames} frames faites à la main par cette découpe ?`)) return;
  if (state.screen === 'cut') await saveNow();
  try {
    const job = await api(`/api/auto?id=${enc(ch.id)}`, { method: 'POST' });
    ch.job = job;
    const ep = findEpisode(ch.id);
    if (ep) ep.job = job;
    renderHead();
    renderLibrary();
    schedulePoll(500);
    toast('Tout se fait : visages, relecture, voix, sons, puis la vidéo');
  } catch (e) {
    toast(`Impossible : ${e.message}`);
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
    const progressBefore = JSON.stringify(findEpisode(state.current)?.progress);
    const jobsBefore = new Map((state.library?.series || []).flatMap((s) => s.chapters.map((c) => [c.id, c.job])));
    state.library = await api('/api/library');
    for (const s of state.library.series) for (const c of s.chapters) dockFinished(jobsBefore.get(c.id), c.job, c.id);
    renderDock();
    renderLibrary();
    const after = findEpisode(state.current)?.job;
    if (state.chapter && JSON.stringify(before) === JSON.stringify(after) && progressBefore !== JSON.stringify(findEpisode(state.current)?.progress)) renderHead();
    if (state.chapter && state.screen === 'video' && JSON.stringify(before) !== JSON.stringify(after)) {
      renderHead();
      if (isRunning(before) && !isRunning(after)) openVideo();
    } else if (state.chapter && state.screen === 'sounds' && JSON.stringify(before) !== JSON.stringify(after)) {
      renderHead();
      await onSoundsJob(before, after);
    } else if (state.chapter && state.screen === 'review' && JSON.stringify(before) !== JSON.stringify(after)) {
      await onReviewJob(before, after);
    } else if (state.chapter && state.screen === 'cast' && JSON.stringify(before) !== JSON.stringify(after)) {
      await onCastJob(before, after);
    } else if (state.chapter && JSON.stringify(before) !== JSON.stringify(after)) {
      renderHead();
      // pendant un travail on ne redessine que la carte d'avancement (l'aperçu reste en place)
      const card = $('#job-card');
      if (isRunning(after) && isRunning(before) && card) card.replaceWith(jobCard(after));
      else {
        renderSide();
        if (isRunning(before) && after?.status === 'done') $('#side').scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
  } catch {}
  const busy = isRunning(state.library?.import) || state.library?.series.some((s) => s.chapters.some((c) => isRunning(c.job)));
  schedulePoll(busy ? 1500 : 10000);
}

document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && state.chapter && state.screen === 'cut') {
    event.preventDefault();
    undo();
  }
});

window.addEventListener('hashchange', () => {
  const { id, screen } = parseHash();
  if (id && id !== state.current && findEpisode(id)) openChapter(id, screen);
  else if (id === state.current && screen !== state.screen) switchScreen(screen);
});

$('main').addEventListener('scroll', hidePeek, { passive: true });
$('#settings-btn').addEventListener('click', openSettings);

for (const slot of document.querySelectorAll('[data-icon]')) slot.replaceChildren(icon(slot.dataset.icon));

(async function start() {
  try {
    state.library = await api('/api/library');
  } catch (e) {
    $('#view').replaceChildren(el('div', { class: 'notice error' }, icon('alert'), el('p', { text: `Serveur injoignable : ${e.message}` })));
    return;
  }
  renderLibrary();
  const { id, screen } = parseHash();
  if (id && findEpisode(id)) openChapter(id, screen);
  else renderHome();
  schedulePoll(10000);
})();
