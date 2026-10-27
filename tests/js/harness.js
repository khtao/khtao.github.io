/**
 * Shared harness for the DOM-level regression tests.
 *
 * The site is a single index.html with one classic <script> block, so every
 * helper it defines lives in the page's global scope. jsdom lets us reach them
 * with window.eval(...), which is how the tests below poke at internals that
 * are not exported (frameLazy, rawObservers, prettyURL, ...).
 *
 * Each test gets a FRESH jsdom instance: localStorage, frameLazy and the
 * observer list are all module-level mutable state, and reusing one instance
 * would let a leak hide behind another test's cleanup.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const HTML_PATH = path.join(ROOT, 'index.html');
const HTML = fs.readFileSync(HTML_PATH, 'utf8');

/** Serve ./xxx from the real repo so the page can boot for real. */
function makeFetch() {
  return async (u) => {
    const rel = decodeURIComponent(String(u).split('?')[0].replace(/^\.\//, ''));
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) {
      return { ok: false, status: 404, text: async () => '' };
    }
    return { ok: true, status: 200, text: async () => fs.readFileSync(p, 'utf8') };
  };
}

/** Minimal browser APIs jsdom lacks. */
function patchWindow(w) {
  w.fetch = makeFetch();
  w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
  w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  w.MutationObserver = w.MutationObserver || class { observe() {} disconnect() {} };
  w.scrollTo = () => {};
  if (!w.requestAnimationFrame) w.requestAnimationFrame = (fn) => setTimeout(() => fn(0), 0);
  return w;
}

/**
 * Boot the page. Resolves once the first render has happened.
 * @param {object} opts  {url, quiet}
 */
async function boot(opts = {}) {
  const vc = new VirtualConsole();
  const errors = [];
  if (!opts.quiet) vc.on('jsdomError', () => {});   // CSS parse noise
  vc.on('error', (m) => errors.push(String(m)));
  const dom = new JSDOM(HTML, {
    url: opts.url || 'https://khtao.github.io/',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse: patchWindow,
  });
  const W = dom.window;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  await wait(opts.settle === undefined ? 1400 : opts.settle);
  return { W, D: W.document, wait, errors, dom, close: () => W.close() };
}

/**
 * A page instance without waiting for the full boot (fast, for unit-ish tests).
 * Async on purpose: closing a window while its start-up promise chain is still
 * settling leaves shared jsdom state inconsistent and makes the NEXT instance
 * boot with `cfg` undefined — so we always let it settle a tick first.
 */
async function bare(opts = {}) {
  const dom = new JSDOM(HTML, {
    url: opts.url || 'https://khtao.github.io/',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(),
    beforeParse: patchWindow,
  });
  await wait(opts.settle === undefined ? 150 : opts.settle);
  return { W: dom.window, D: dom.window.document, dom, close: () => dom.window.close() };
}

/* ------------------------------- assertions ------------------------------- */

class Suite {
  constructor(name) {
    this.name = name;
    this.pass = 0;
    this.fail = 0;
    this.lines = [];
  }
  ok(cond, msg, detail) {
    if (cond) { this.pass++; this.lines.push(`  ✓ ${msg}`); }
    else { this.fail++; this.lines.push(`  ✗ ${msg}${detail ? `  → ${detail}` : ''}`); }
    return !!cond;
  }
  eq(actual, expected, msg) {
    return this.ok(actual === expected, msg, `期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`);
  }
  report() {
    console.log(`\n【${this.name}】${this.fail === 0 ? '全部通过' : '有失败'}  ${this.pass} 通过 / ${this.fail} 失败`);
    this.lines.forEach((l) => console.log(l));
    return this.fail;
  }
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

module.exports = { boot, bare, wait, Suite, ROOT, HTML };
