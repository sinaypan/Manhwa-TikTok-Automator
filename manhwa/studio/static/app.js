'use strict';
// Manhwa Studio : bibliothèque (séries → épisodes), écrans Découpe et Personnages.

const STRIP_W = 380; // largeur d'affichage du strip, comme #strip dans app.css
const STEP_NAMES = ['Pages', 'Découpe', 'Texte', 'Voix', 'Vidéo'];
const JOB_STEPS = [
  ['frames', 'Frames 9:16'],
  ['ocr', 'Lecture du texte'],
  ['tts', 'Voix'],
  ['render', 'Rendu vidéo'],
];
const KIND_STEPS = {
  faces: [['faces', 'Recherche des visages']],
  wiki: [['wiki', 'Lecture du wiki']],
  wiki_images: [
    ['wiki_images', 'Images du wiki'],
    ['wiki_faces', 'Visages du wiki'],
  ],
};
const KIND_TITLES = { faces: 'Recherche des personnages', wiki: 'Lecture du wiki', wiki_images: 'Images du wiki' };
const SCREENS = [
  ['cut', 'Découpe'],
  ['cast', 'Personnages'],
];
const TALL_DOUBT = 2; // une case de plus de 2 écrans cache sans doute une coupe

const ICONS = {
  sparkles: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z',
  play: 'M7 4l12 8-12 8z',
  reset: 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  check: 'M20 6 9 17l-5-5',
  alert: 'M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  down: 'M12 5v14M19 12l-7 7-7-7',
  scissors: 'M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  plus: 'M12 5v14M5 12h14',
  x: 'M18 6 6 18M6 6l12 12',
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
  screen: 'cut', // 'cut' (Découpe) ou 'cast' (Personnages)
  cast: null, // détail renvoyé par /api/cast
  sel: new Set(), // visages sélectionnés (à ranger)
  lineFilter: 'todo', // répliques : 'todo' (à valider) ou 'all'
  pendingKeys: new Set(), // répliques « à valider » à l'ouverture (restent affichées une fois validées)
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
  return JOB_STEPS.findIndex(([step]) => step === job.step) + 1;
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
  history.replaceState(null, '', `#${enc(state.current)}${state.screen === 'cast' ? '/personnages' : ''}`);
}

function parseHash() {
  // « #Série%2Fchapter-001 » ou « #Série%2Fchapter-001/personnages »
  const [raw, screen] = location.hash.slice(1).split('/');
  return { id: decodeURIComponent(raw || ''), screen: screen === 'personnages' ? 'cast' : 'cut' };
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
  if (screen === 'cast') openCast();
  else renderChapter(false);
  $('main').scrollTop = 0;
}

function renderHead() {
  const ch = state.chapter;
  const head = $('#head');
  if (!head) return;
  const job = findEpisode(ch.id)?.job || ch.job;
  const running = isRunning(job);
  const title = el('h2', { text: `${ch.series} · ${ch.name.replace('chapter-', 'Épisode ')}` });
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
  const steps = KIND_STEPS[job.kind] || JOB_STEPS;
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
  const list = state.cast?.characters || [];
  const i = list.findIndex((c) => c.id === cid);
  if (i < 0) return '?';
  return list[i].name || `Perso ${i + 1}`;
}

function avatar(cid, size = '') {
  if (cid === state.cast.narrator) return el('span', { class: `avatar narrator ${size}` }, icon('sparkles'));
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
      wikiStatus(),
    ),
    el('div', { class: 'cast-grid' }, cards),
    silent.length
      ? el(
          'div',
          { class: 'silent-block' },
          el('h4', { text: 'Ne parlent pas' }),
          el('p', { class: 'muted', text: 'Jamais proposés pour une réplique. Clique sur « Parle » pour les remettre.' }),
          el('div', { class: 'cast-grid' }, silent.map(charCard)),
        )
      : null,
    elsewhere.length ? el('p', { class: 'muted elsewhere', text: `Déjà vus dans la série : ${elsewhere.map((ch) => charLabel(ch.id)).join(', ')}.` }) : null,
    c.rejected.length
      ? el('details', { class: 'rejected' }, el('summary', { text: `${plural(c.rejected.length, 'forme écartée', 'formes écartées')} (pas des visages)` }), el('div', { class: 'faces' }, c.rejected.map(faceThumb)))
      : null,
  );
}

const person = (wid) => state.cast.people.find((w) => w.id === wid);

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
    el('div', { class: 'faces' }, ch.faces.map(faceThumb)),
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
  const proposals = c.lines.filter((l) => !l.speaker && l.suggestion).length;
  const shown = state.lineFilter === 'todo' ? c.lines.filter((l) => state.pendingKeys.has(l.key)) : c.lines;
  const setFilter = (key) => {
    state.lineFilter = key;
    state.pendingKeys = new Set(c.lines.filter((l) => !l.speaker).map((l) => l.key));
    $('#speak').replaceWith(linesSection());
  };
  const filter = el(
    'div',
    { class: 'tabs small' },
    [
      ['todo', `À valider · ${total - done}`],
      ['all', `Toutes · ${total}`],
    ].map(([key, label]) => el('button', { type: 'button', class: state.lineFilter === key ? 'on' : '', onclick: () => setFilter(key) }, label)),
  );
  let body;
  if (!c.ocr_done) body = el('p', { class: 'muted', text: 'Le texte n’a pas encore été lu : crée d’abord la vidéo.' });
  else if (!total) body = el('p', { class: 'muted', text: 'Aucune réplique dans ce chapitre.' });
  else if (!shown.length) body = el('div', { class: 'notice' }, icon('check'), el('p', { text: 'Toutes les répliques ont leur personnage.' }));
  else body = el('div', { class: 'lines' }, shown.map(lineRow));
  return el(
    'section',
    { class: 'cast-block', id: 'speak' },
    el(
      'div',
      { class: 'block-head row' },
      el('div', { class: 'grow' }, el('h3', { text: 'Qui parle' }), el('p', { class: 'muted', text: 'Clique sur la bonne tête, sur l’image ou dessous. En pointillés : la proposition. Servira à donner une voix à chaque personnage.' })),
      el('div', { class: 'actions' }, filter, proposals ? el('button', { type: 'button', class: 'pill accent', onclick: acceptProposals }, icon('check'), `Valider les ${proposals} propositions`) : null),
    ),
    el('div', { class: 'bar' }, el('span', { style: `width:${total ? (100 * done) / total : 0}%` })),
    body,
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
      el(
        'div',
        { class: 'who-chips' },
        options.map(chip),
        chip(c.narrator),
        others.length
          ? el(
              'select',
              { class: 'chip-btn', 'aria-label': 'Un autre personnage', onchange: (e) => e.target.value && setSpeaker(l, e.target.value) },
              el('option', { value: '', text: 'Autre…' }),
              others.map((ch) => el('option', { value: ch.id, text: charLabel(ch.id) })),
            )
          : null,
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
    if (before !== cid && fresh) toast(`« ${l.text.slice(0, 32)}${l.text.length > 32 ? '…' : ''} » → ${cid ? charLabel(cid) : 'personne'}`, { label: 'Annuler', run: () => setSpeaker(fresh, before) });
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
  old.querySelector('.bar').replaceWith(fresh.querySelector('.bar'));
}

async function acceptProposals() {
  const todo = state.cast.lines.filter((l) => !l.speaker && l.suggestion);
  try {
    await sendSpeakers(todo.map((l) => ({ key: l.key, char: l.suggestion })));
    $('#speak').replaceWith(linesSection());
    renderHead();
    toast(plural(todo.length, 'réplique validée', 'répliques validées'), {
      label: 'Annuler',
      run: async () => {
        await sendSpeakers(todo.map((l) => ({ key: l.key, char: null })));
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
    if (state.chapter && state.screen === 'cast' && JSON.stringify(before) !== JSON.stringify(after)) {
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
  const busy = state.library?.series.some((s) => s.chapters.some((c) => isRunning(c.job)));
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
