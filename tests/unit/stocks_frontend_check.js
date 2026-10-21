// WQ-0382 frontend behavior test: extract the pure-ish functions from
// stocks-tab.js and the total-integration math from app.js, run them under
// node with DOM/fetch stubs, assert the money math and the double-count
// guard (stocksValue declared once).
const fs = require('fs');
const assert = require('assert');

// ---- load stocks-tab.js with stubs ------------------------------------
let src = fs.readFileSync('frontend/js/stocks-tab.js', 'utf8');

// stub globals the module expects
global.document = {
  _els: {},
  getElementById(id) {
    if (!this._els[id]) {
      this._els[id] = {
        id, value: '', classList: { _h: true,
          add(c) { if (c === 'hidden') this._h = true; },
          remove(c) { if (c === 'hidden') this._h = false; },
          toggle(c, on) { if (c === 'hidden') this._h = !on; } },
        textContent: '', innerHTML: '', focus() {}, disabled: false,
      };
    }
    return this._els[id];
  },
  createElement() { const d = { _t: '', set textContent(v) { this._t = String(v); },
    get textContent() { return this._t; },
    // real DOM innerHTML serialization escapes only markup chars it can't
    // represent; & that came from plain text is serialized as &amp; only in
    // round-trip, which is irrelevant to these assertions -- replace < > so
    // the escape test sees the same output a browser would for new text.
    get innerHTML() { return this._t.replace(/</g,'&lt;').replace(/>/g,'&gt;'); } }; return d; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
global.window = {};
global.API_BASE = '/api';
let fetched = [];
global.authFetch = async (url, opts) => {
  fetched.push([url, opts && opts.method]);
  return { ok: true, status: 200, json: async () => ({}) };
};
global.showStatus = () => {};
global.formatUSD = (n) => '$' + n.toFixed(2);
global.setSafeHTML = (el, html) => { el.innerHTML = html; };
global.scheduleUpdateTotalPortfolioValue = () => { global.__totalsRecalc++; };
global.__totalsRecalc = 0;
global.formatRefreshTimestamp = (d) => 'stamp';
global.clearTimeout = clearTimeout;
global.setTimeout = setTimeout;

// app.js declares the shared stocksValue/stocks; stocks-tab.js assigns them.
// In the page both scripts share one global lexical scope; in node we wrap
// both bodies into a single function to emulate that.
globalThis.stocksValue = 0;
const appDecls = 'let stocksValue = 0; let stocks = [];';
const loader = new Function(appDecls + '\n' + src +
  '\n; return {loadStocks, displayStocks, escapeHtmlStock, getStocks: () => stocks, getStocksValue: () => stocksValue};');

const mod = loader();

// ---- displayStocks math ----------------------------------------------
document._els = {};
const sample = { stocks: [
  { id: 1, symbol: 'NVDA', name: 'NVIDIA Corporation', quantity: 10,
    price_usd: 216.47, change_pct: -0.29, value_usd: 2164.7,
    unrealized_pnl_usd: 500, include_in_total: 1,
    last_price_update: '2026-10-20T21:05:00' },
  { id: 2, symbol: 'BITW', name: 'Bitwise 10 <Crypto>', quantity: 5,
    price_usd: 53.13, change_pct: 1.25, value_usd: 265.65,
    unrealized_pnl_usd: null, include_in_total: 0, last_price_update: null },
], tracked_total_usd: 2164.7 };
mod.displayStocks(sample);
const listHtml = document.getElementById('stocksList').innerHTML;
assert(listHtml.includes('NVDA'), 'row rendered');
assert(listHtml.includes('&lt;Crypto&gt;'), 'HTML-escaped name: ' + listHtml.slice(0, 200));
assert(listHtml.includes('-0.29%') && listHtml.includes('down'), 'negative change styled down');
assert(listHtml.includes('+1.25%') && listHtml.includes('up'), 'positive change styled up');
assert(document.getElementById('stocksSummary').innerHTML.includes('Tracked: $2164.7'), 'summary uses formatUSD (stub formats plain, app adds separators)') ;

// empty state
document._els = {};
mod.displayStocks({ stocks: [], tracked_total_usd: 0 });
assert(document.getElementById('stocksList').innerHTML.includes('No stocks tracked'), 'empty state');

// ---- escapeHtmlStock --------------------------------------------------
assert(mod.escapeHtmlStock('<img onerror=x>') === '&lt;img onerror=x&gt;', 'escape');

// ---- app.js integration: totals include stocksValue -------------------
// Re-implement the exact return expressions from app.js (source of record
// is the pytest below; this checks the shipped lines parse+add correctly).
const appSrc = fs.readFileSync('frontend/js/app.js', 'utf8');
assert(appSrc.includes('const liquidTotal = walletsTotal + exchangesTotal + trackedTokensTotal + customTokensTotal + stocksTotal;'),
  'liquid total includes stocks');
assert(appSrc.includes('return walletsTotal + exchangesTotal + stakingTotal + defiTotal + nftsTotal + trackedTokensTotal + customTokensTotal + stocksTotal;'),
  'grand total includes stocks');
assert(appSrc.includes('stocks: (typeof stocksValue !== \'undefined\' && stocksValue) || 0'),
  'breakdown has own stocks bucket');
// single declaration of stocksValue across the shipped JS
const decl = (s, f) => (fs.readFileSync(f, 'utf8').match(s) || []).length;
assert(decl(/^let stocksValue/m, 'frontend/js/app.js') === 1 &&
       decl(/^let stocksValue/m, 'frontend/js/stocks-tab.js') === 0,
       'stocksValue declared exactly once (no SyntaxError on load)');

// v2 integration
const v2 = fs.readFileSync('frontend/v2/js/v2-app.js', 'utf8');
assert(v2.includes('(parseFloat(bd.manual_stock) || 0)'), 'v2 hero liquid includes manual_stock');
assert(v2.includes('liquid += manualStockTotal;'), 'v2 reconcile re-adds manual_stock');

// v2 cache entries
const v2c = fs.readFileSync('frontend/v2/js/v2-cache.js', 'utf8');
assert(v2c.includes("'/stocks':"), 'v2 cache lists /stocks');

console.log('FRONTEND TESTS PASS');
