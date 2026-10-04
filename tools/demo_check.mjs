// Drive the demo in headless Chrome over the DevTools protocol, in real time (adapted from
// where-are-the-regions'). For each sample: wait for the page drawing, check the number of parts sent to
// OCR, go to the first page with routes and check that hovering its first route lights up its box, then
// switch to the merged words and check OCR words are there. Console errors and exceptions fail it, and
// each view is screenshotted.
// usage: node tools/demo_check.mjs <base url> <out dir> [chrome.exe]
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [base, outDir, chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe'] = process.argv.slice(2);
const port = 9335;
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${port}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'wnchk-'))}`, '--window-size=1280,1100', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 50; i++) {
    try { const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); const p = l.find((t) => t.type === 'page'); if (p) return p; } catch {}
    await sleep(200);
  }
  throw new Error('no Chrome target');
}

const t = await target();
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0;
const waiting = new Map();
const log = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) log.push(`console.${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(' ')}`);
  if (m.method === 'Runtime.exceptionThrown') log.push(`exception: ${m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text}`);
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') log.push(`log: ${m.params.entry.text}`);
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');

let failed = 0;
const LABEL = { contract: 'Contract', poster: 'Poster', notice: 'Garbled letter' };
// parts sent to OCR in the whole file, and the first page that has routes
const WANT = { contract: [1, 2], poster: [6, 1], notice: [1, 1] };
const read = () => evaluate(`(() => { const c = document.querySelector('.wn-stage canvas'); return {
  drawn: !!c && !c.hidden && c.width > 0, page: document.querySelector('.wn-stage')?.dataset.rendered,
  boxes: document.querySelectorAll('.wn-box').length, items: document.querySelectorAll('.wn-item').length,
  ocrWords: document.querySelectorAll('.wn-box.s-ocr').length, status: document.querySelector('.wn-status')?.textContent }; })()`);
const until = async (test) => { let s; for (let i = 0; i < 80; i++) { await sleep(250); s = await read(); if (s && test(s)) break; } return s; };
const shoot = async (name) => { const shot = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(outDir, name), Buffer.from(shot.result.data, 'base64')); };
for (const s of Object.keys(LABEL)) {
  log.length = 0;
  // start from a blank page each time, so the previous sample's state isn't read
  await send('Page.navigate', { url: 'about:blank' });
  await sleep(200);
  await send('Page.navigate', { url: `${base}#sample=${s}` });
  const [parts, first] = WANT[s];
  let state = await until((x) => x.drawn && x.page === '1' && x.status?.startsWith(`Sample: ${LABEL[s]}:`));
  const counted = state?.status?.includes(`, ${parts} part${parts === 1 ? '' : 's'} to send to OCR,`);
  for (let p = 1; p < first; p++) await evaluate(`document.querySelector('[aria-label="Next page"]').click()`);
  state = await until((x) => x.drawn && x.page === String(first));
  const hover = await evaluate(`(() => { const w = document.querySelector('.wn-list [data-k]'); if (!w) return 'no items';
    w.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
    const k = w.dataset.k; const box = document.querySelector('.wn-overlay [data-k="' + k + '"]');
    const ok = w.classList.contains('hot') && !!box && box.classList.contains('hot');
    w.dispatchEvent(new PointerEvent('pointerout', { bubbles: true })); return ok ? 'ok' : 'not lit'; })()`);
  await shoot(`demo-${s}-routes.png`);
  await evaluate(`[...document.querySelectorAll('.wn-views button')].find((b) => b.textContent === 'Words').click()`);
  const words = await until((x) => x.drawn && x.ocrWords > 0);
  await shoot(`demo-${s}-words.png`);
  const ok = !!(state?.drawn && counted && state.boxes > 0 && hover === 'ok' && words?.ocrWords > 0
    && !log.some((l) => /exception|console.error/.test(l)));
  if (!ok) failed++;
  console.log(JSON.stringify({ sample: s, ok, counted, ...state, hover, ocrWords: words?.ocrWords, log }));
}
ws.close();
proc.kill();
process.exit(failed ? 1 : 0);
