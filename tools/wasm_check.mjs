// Check the browser build against router-cli: for every file in the OCR results given, the wasm's
// routes_json must equal router-cli's line for it, and merge_json, given that file's crops, must equal
// router-cli --merge's line, byte for byte once router-cli's "file" key (and, merged, its "ocr" key) is
// taken out. The wasm is the one in wasm/pkg, built with wasm-pack --target web.
//
// usage: node tools/wasm_check.mjs <ocr results.jsonl>...
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const cli = join(root, 'router', 'target', 'release', process.platform === 'win32' ? 'router-cli.exe' : 'router-cli');
const wasm = await import(new URL('../wasm/pkg/router_wasm.js', import.meta.url));
await wasm.default({ module_or_path: readFileSync(join(root, 'wasm', 'pkg', 'router_wasm_bg.wasm')) });

// router-cli's line without its file key, and without the ocr key a merged line has
const strip = (line) => line.replace(/^\{"file":("(?:[^"\\]|\\.)*"),/, '{').replace(/^(\{"status":"[^"]*"),"ocr":(?:true|false),/, '$1,');

const results = process.argv.slice(2);
if (!results.length) {
  console.error('usage: node tools/wasm_check.mjs <ocr results.jsonl>...');
  process.exit(2);
}
let files = 0, bad = 0;
const tmp = mkdtempSync(join(tmpdir(), 'wasm-check-'));
for (const res of results) {
  const lines = readFileSync(res, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  const list = join(tmp, 'list.txt');
  writeFileSync(list, lines.map((l) => l.file).join('\n'));
  const run = (args) => execFileSync(cli, args, { encoding: 'utf8', maxBuffer: 1 << 30 }).split('\n').filter((l) => l.trim());
  const routes = run(['--list', list]);
  const merged = run(['--merge', res, '--list', list]);
  lines.forEach((l, k) => {
    const bytes = readFileSync(l.file);
    files++;
    const r = wasm.routes_json(bytes), m = wasm.merge_json(bytes, JSON.stringify(l.pages), wasm.min_conf());
    if (r !== strip(routes[k])) { bad++; console.log(`routes differ: ${l.file}`); }
    if (m !== strip(merged[k])) { bad++; console.log(`merged words differ: ${l.file}`); }
  });
  console.log(`${res}: ${lines.length} files`);
}
rmSync(tmp, { recursive: true, force: true });
console.log(`${files} files, ${bad} differences`);
process.exit(bad ? 1 : 0);
