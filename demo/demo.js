// What needs OCR? The page, drawn by pdf.js, with every route the router gives boxed on top of it (sent to
// OCR, skipped, or already read), and the routes listed beside it with the reason for each. The samples
// also carry what Tesseract read in their crops, made beforehand (tools/samples.py), so for them the
// merged word list can be shown: the file's own words and the OCR words that add to them, merged here by
// the same code as router-cli --merge. Everything runs in this page: the file is never uploaded.
import init, { routes_json, merge_json, min_conf } from './router_wasm.js';

// pdf.js and the WebAssembly module load on first use, not with the page, so the page itself stays light
let pdfjs = null;
async function loadPdfjs() {
  if (!pdfjs) {
    const lib = await import('./pdfjs/pdf.min.mjs');
    lib.GlobalWorkerOptions.workerSrc = new URL('./pdfjs/pdf.worker.min.mjs', import.meta.url).href;
    pdfjs = lib;
  }
  return pdfjs;
}

const root = document.getElementById('demo');
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? '' : v);
  }
  n.append(...kids.flat().filter((k) => k != null && k !== false));
  return n;
};

const SAMPLES = [['contract', 'Contract'], ['poster', 'Poster'], ['notice', 'Garbled letter']];
const SOURCE = { image: 'Image', vector: 'Letters drawn as shapes', words: 'Text that doesn’t decode' };
const DECISION = { ocr: 'sent to OCR', skip: 'not sent to OCR', text_layer: 'already read' };
const WORD = { file: 'the file’s own text', file_ocr_layer: 'an OCR layer already in the file', ocr: 'read by OCR' };
const KIND = { text: 'text', photo: 'a photo', graphic: 'a graphic', blank: 'a blank sheet' };
const pct = (v) => `${Math.round(v * 100)}%`;

const input = el('input', { type: 'file', id: 'wn-file', accept: 'application/pdf,.pdf', class: 'sr-only' });
const zone = el('div', { class: 'wn-drop' },
  el('p', {}, 'Drop a PDF here, choose one, or try a sample.'),
  el('div', { class: 'wn-actions' },
    el('label', { for: 'wn-file', class: 'wn-btn' }, 'Choose a PDF'), input,
    SAMPLES.map(([f, label]) => el('button', { type: 'button', class: 'wn-btn ghost', onclick: () => sample(f, label) }, label))));
const status = el('p', { class: 'wn-status', 'aria-live': 'polite' });
const bar = el('div', { class: 'wn-bar', hidden: true });
const stage = el('div', { class: 'wn-stage' });
const list = el('ol', { class: 'wn-list', 'aria-label': 'Routes on this page' });
const view = el('div', { class: 'wn-view', hidden: true }, stage, list);
const note = el('p', { class: 'wn-note' });
root.replaceChildren(zone, status, bar, view, note);
const NOTE = 'Your file stays on your device: it’s read in this page and never uploaded. OCR itself doesn’t run here, so for your own files the demo shows what would be sent to it.';
note.textContent = NOTE;

let ready = null;
let routes = null, words = null, pdf = null, pdfReady = false, index = 0, mode = 'routes', renderTask = null;

async function load(fileName, bytes, crops) {
  status.textContent = 'Reading…';
  await (ready ||= init());
  const t = performance.now();
  routes = JSON.parse(routes_json(bytes));
  const ms = performance.now() - t;
  words = crops != null ? JSON.parse(merge_json(bytes, crops, min_conf())) : null;
  if (!words) mode = 'routes';
  if (routes.status !== 'ok') {
    bar.hidden = true; view.hidden = true;
    status.textContent = routes.status === 'not_pdf' ? 'That isn’t a PDF.' : 'This PDF is encrypted with a password, or with a method this tool doesn’t support.';
    return;
  }
  const all = routes.pages.flatMap((p) => p.routes);
  const sent = all.filter((r) => r.decision === 'ocr');
  const area = routes.pages.reduce((a, p) => a + p.width * p.height, 0);
  const ocrArea = routes.pages.reduce((a, p) => a + union(p.routes.filter((r) => r.decision === 'ocr'), p), 0);
  const took = ms < 0.1 ? 'under 0.1' : ms < 10 ? ms.toFixed(1) : Math.round(ms);
  const n = routes.pages.length;
  status.textContent = `${fileName}: ${n} page${n === 1 ? '' : 's'}, ${sent.length} part${sent.length === 1 ? '' : 's'} to send to OCR, ${area ? (100 * ocrArea / area).toFixed(1) : 0}% of the page area, routed in ${took} ms in your browser.`;
  note.textContent = words ? `${NOTE} This sample carries what Tesseract 5.4.0 read in its crops, made beforehand; OCR words under ${pct(min_conf())} confidence are left out.` : NOTE;
  if (pdf) pdf.destroy().catch(() => {});
  pdf = null;
  pdfReady = false;
  index = 0;
  show();
  const mine = routes;
  loadPdfjs().then((lib) => {
    if (routes !== mine) return; // another file was chosen meanwhile
    const task = lib.getDocument({ data: bytes.slice(), isEvalSupported: false });
    pdf = task;
    task.promise.then(() => { if (pdf === task) { pdfReady = true; drawPage(); } }, () => { if (pdf === task) pdf = null; });
  }, () => { /* without pdf.js the boxes and the list still show */ });
}

// the area under the union of some boxes on a page, on a grid of 4 points
function union(boxes, page) {
  if (!boxes.length) return 0;
  let hit = 0;
  for (let y = 2; y < page.height; y += 4) {
    for (let x = 2; x < page.width; x += 4) {
      if (boxes.some((b) => x >= b.x0 && x <= b.x1 && y >= b.y0 && y <= b.y1)) hit++;
    }
  }
  return hit * 16;
}

function show() {
  const page = routes.pages[index];
  bar.hidden = false; view.hidden = false;
  const n = (d) => page.routes.filter((r) => r.decision === d).length;
  const counts = [`${n('ocr')} to OCR`, `${n('skip')} skipped`];
  if (n('text_layer')) counts.push(`${n('text_layer')} already read`);
  if (mode === 'words') {
    const ws = words.pages[index].words;
    const o = ws.filter((w) => w.source === 'ocr').length;
    counts.splice(0, counts.length, `${ws.length - o} words from the file`, `${o} from OCR`);
  }
  const tab = (m, label) => el('button', { type: 'button', class: 'wn-btn ghost', 'aria-pressed': String(mode === m), disabled: m === 'words' && !words,
    title: m === 'words' && !words ? 'Only the samples carry OCR results' : null, onclick: () => { mode = m; show(); } }, label);
  bar.replaceChildren(
    el('button', { type: 'button', class: 'wn-btn ghost', disabled: index === 0, onclick: () => go(-1), 'aria-label': 'Previous page' }, '‹'),
    el('span', { class: 'wn-page' }, `Page ${index + 1} of ${routes.pages.length}`),
    el('button', { type: 'button', class: 'wn-btn ghost', disabled: index === routes.pages.length - 1, onclick: () => go(1), 'aria-label': 'Next page' }, '›'),
    el('span', { class: 'wn-counts' }, counts.join(' · ')),
    el('span', { class: 'wn-views' }, tab('routes', 'Routes'), tab('words', 'Words')));
  list.setAttribute('aria-label', mode === 'words' ? 'Words on this page' : 'Routes on this page');
  if (mode === 'words') listWords(); else listRoutes(page);
  drawPage();
}

function go(d) { index = Math.max(0, Math.min(routes.pages.length - 1, index + d)); show(); }

async function drawPage() {
  const page = routes.pages[index];
  const width = Math.max(240, stage.clientWidth || 600);
  const scale = width / page.width;
  const canvas = el('canvas', { 'aria-hidden': 'true', hidden: true });
  const overlay = el('div', { class: 'wn-overlay' });
  stage.replaceChildren(canvas, overlay);
  stage.style.height = `${page.height * scale}px`;
  const want = index;
  const box = (b, cls, k, title) => overlay.append(el('div', {
    class: `wn-box ${cls}`, 'data-k': k, title,
    style: `left:${b.x0 * scale}px;top:${b.y0 * scale}px;width:${Math.max(1, (b.x1 - b.x0) * scale)}px;height:${Math.max(1, (b.y1 - b.y0) * scale)}px`,
  }));
  if (mode === 'words') {
    words.pages[index].words.forEach((w, k) => box(w, `word ${w.source === 'file' ? 'file ' : ''}s-${w.source}`, w.source === 'ocr' ? `c${w.crop}` : null, `${w.t} · ${WORD[w.source]}`));
  } else {
    page.routes.forEach((r, k) => box(r, `${r.decision} d-${r.decision}`, k, label(r)));
  }
  // draw the page only when pdf.js has the document; until then the boxes stand alone
  if (pdf && pdfReady) {
    try {
      const doc = await pdf.promise;
      if (want !== index) return;
      canvas.hidden = false;
      const p = await doc.getPage(index + 1);
      const vp = p.getViewport({ scale });
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(vp.width * dpr);
      canvas.height = Math.floor(vp.height * dpr);
      canvas.style.width = `${vp.width}px`;
      canvas.style.height = `${vp.height}px`;
      if (renderTask) renderTask.cancel();
      renderTask = p.render({ canvasContext: canvas.getContext('2d'), viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null });
      await renderTask.promise.catch(() => {});
      stage.dataset.rendered = String(want + 1); // the page number just drawn, for tools/demo_check.mjs
    } catch { /* the boxes and the list still show without the drawing */ }
  }
}

const reason = (r, k) => r.reasons.find(([n]) => n === k)?.[1];

// why the router decided as it did, in words
function why(r) {
  if (r.source === 'image') {
    if (r.decision === 'text_layer') return `invisible text, an earlier OCR, covers ${pct(reason(r, 'layer_cover'))} of it`;
    if (reason(r, 'no_pixels') != null) return 'its pixels can’t be read here, so it’s judged on its size and place alone';
    const kind = r.reasons.find(([n]) => n in KIND);
    const parts = [];
    if (kind) parts.push(`it looks like ${KIND[kind[0]]}`);
    const t = reason(r, 'has_text');
    if (t != null) parts.push(t >= 0.5 ? 'its pixels show text' : t > 0.05 ? 'its pixels show a little text' : 'its pixels show no text');
    if (reason(r, 'text_layer') != null) parts.push('an earlier OCR’s invisible text already lies over it');
    if (reason(r, 'under_text') != null) parts.push('the file’s own text lies over it');
    return parts.join(', ');
  }
  if (r.source === 'vector') {
    const n = reason(r, 'letters');
    return n != null ? `a drawing with ${n} letter shapes in it` : 'no text in the file here, only shapes';
  }
  return `${pct(reason(r, 'undecodable'))} of this font’s ${reason(r, 'font_words')} words copy out as characters that mean nothing`;
}

function label(r) {
  return `${SOURCE[r.source]} · ${DECISION[r.decision]}${r.decision === 'ocr' ? `, ${pct(r.confidence)} sure` : ''} · ${why(r)}`;
}

function listRoutes(page) {
  list.replaceChildren(...page.routes.map((r, k) => el('li', { class: `wn-item d-${r.decision}`, 'data-k': k },
    el('span', { class: 'what' }, SOURCE[r.source]),
    ` · ${DECISION[r.decision]}${r.decision === 'ocr' ? `, ${pct(r.confidence)} sure` : ''}`,
    r.source === 'image' && r.decision === 'ocr' && el('span', { class: 'why' }, `to be read at ${Math.round(Math.min(400, Math.max(300, r.dpi)))} dpi`),
    el('span', { class: 'why' }, why(r)))));
  if (!page.routes.length) list.replaceChildren(el('li', { class: 'wn-empty' }, 'Nothing here needs OCR: there are no images, no letters drawn as shapes, and the text decodes.'));
}

// the OCR words, crop by crop, and a count of the file's own
function listWords() {
  const ws = words.pages[index].words;
  const file = ws.filter((w) => w.source !== 'ocr');
  const crops = new Map();
  for (const w of ws.filter((w) => w.source === 'ocr')) {
    if (!crops.has(w.crop)) crops.set(w.crop, []);
    crops.get(w.crop).push(w);
  }
  const items = [...crops].map(([c, cw]) => el('li', { class: 'wn-item s-ocr', 'data-k': `c${c}` },
    el('span', { class: 'what' }, `Read by OCR, crop ${c + 1}`), ` · ${cw.length} word${cw.length === 1 ? '' : 's'}, ${pct(cw.reduce((a, w) => a + w.confidence, 0) / cw.length)} sure on average`,
    el('span', { class: 't' }, cw.map((w) => w.t).join(' '))));
  const layer = file.filter((w) => w.source === 'file_ocr_layer').length;
  items.push(el('li', { class: `wn-item ${layer ? 's-file_ocr_layer' : 's-file'}` },
    el('span', { class: 'what' }, `${file.length} word${file.length === 1 ? '' : 's'} from the file`),
    layer ? ` · ${layer} of them from an OCR layer already in it` : '',
    el('span', { class: 't' }, file.slice(0, 40).map((w) => w.t).join(' ') + (file.length > 40 ? ' …' : ''))));
  list.replaceChildren(...items);
}

// hover either side lights up both
function light(k, on) {
  for (const n of root.querySelectorAll(`[data-k="${k}"]`)) n.classList.toggle('hot', on);
  if (on) root.querySelector(`.wn-list [data-k="${k}"]`)?.scrollIntoView({ block: 'nearest' });
}
for (const pane of [stage, list]) {
  pane.addEventListener('pointerover', (e) => { const k = e.target.closest('[data-k]')?.dataset.k; if (k) light(k, true); });
  pane.addEventListener('pointerout', (e) => { const k = e.target.closest('[data-k]')?.dataset.k; if (k) light(k, false); });
}

async function sample(name, label) {
  const [pdfRes, ocrRes] = await Promise.all([fetch(new URL(`samples/${name}.pdf`, import.meta.url)), fetch(new URL(`samples/${name}.ocr.json`, import.meta.url))]);
  load(`Sample: ${label}`, new Uint8Array(await pdfRes.arrayBuffer()), ocrRes.ok ? await ocrRes.text() : null);
}

input.addEventListener('change', async () => {
  const f = input.files?.[0];
  if (f) load(f.name, new Uint8Array(await f.arrayBuffer()), null);
});
zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
zone.addEventListener('dragleave', () => zone.classList.remove('over'));
zone.addEventListener('drop', async (e) => {
  e.preventDefault();
  zone.classList.remove('over');
  const f = e.dataTransfer?.files?.[0];
  if (f) load(f.name, new Uint8Array(await f.arrayBuffer()), null);
});
// #sample=contract (or poster, notice) opens a sample straight away
const fromHash = () => {
  const s = new URLSearchParams(location.hash.slice(1)).get('sample');
  const hit = SAMPLES.find(([f]) => f === s);
  if (hit) sample(...hit);
};
window.addEventListener('hashchange', fromHash);
fromHash();

let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (routes && !view.hidden) drawPage(); }, 150); });
