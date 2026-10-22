/**
 * V2 Stocks Tab (WQ-0383 follow-on) — manual stock/ETF holdings on the
 * keyless stock feed, for the /next Assets page.
 *
 * Mirrors the v1 stocks-tab.js behavior against the same backend endpoints
 * (/stocks, /stocks/search, /stocks/{id}, /stocks/scheduler):
 *   - lazy-loaded on first tab visit (loadStocksTab hook in assets.html)
 *   - add modal validates the ticker against the live feed before POSTing
 *   - tracked/untracked toggle; values feed the hero through /portfolio/instant
 *
 * Depends on v2 globals: v2Fetch, setSafeHTML, escapeHtml, formatCurrency,
 * formatPrice, showToast.
 */

let v2StocksData = null;      // last /stocks payload
let v2StockLookup = null;     // last successful /stocks/search result
let v2StockEditId = null;     // id being edited (null = add mode)
let _v2StockLookupTimer = null;

async function loadStocksTab() {
    try {
        const resp = await v2Fetch('/stocks');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        v2StocksData = data;
        renderStocksTab(data);
    } catch (e) {
        console.error('Error loading stocks:', e);
        const container = document.getElementById('stocksContent');
        if (container) {
            setSafeHTML(container, '<div class="v2-empty" style="padding:48px"><div class="v2-empty-title">Stocks unavailable</div><div class="v2-empty-desc">Could not load stock holdings. Reload to retry.</div></div>');
        }
    }
}

function renderStocksTab(data) {
    const container = document.getElementById('stocksContent');
    const summary = document.getElementById('stocksSummary');
    if (!container) return;
    const stocks = (data && data.stocks) || [];
    const tracked = (data && data.tracked_total_usd) || 0;
    if (summary) {
        summary.textContent = stocks.length
            ? stocks.length + ' holding' + (stocks.length !== 1 ? 's' : '') +
              (tracked > 0 ? ' · tracked ' + formatCurrency(tracked) : '')
            : '';
    }
    if (!stocks.length) {
        setSafeHTML(container, '<div class="v2-empty" style="padding:48px"><div class="v2-empty-title">No stocks tracked</div><div class="v2-empty-desc">Add shares or ETF units manually — prices refresh at market open, midday and close.</div></div>');
        return;
    }
    let html = '<table class="v2-table"><thead><tr><th>Symbol</th><th>Name</th><th>Custodian</th><th class="right">Qty</th><th class="right">Price</th><th class="right">Day</th><th class="right">Value</th><th></th></tr></thead><tbody>';
    stocks.forEach(function (s) {
        const chg = s.change_pct;
        const chgHtml = chg == null ? '<span style="color:var(--v2-text-muted)">--</span>'
            : '<span style="color:' + (chg >= 0 ? 'var(--v2-green, #16a34a)' : 'var(--v2-red, #dc2626)') + '">' +
              (chg >= 0 ? '+' : '') + Number(chg).toFixed(2) + '%</span>';
        const pnl = s.unrealized_pnl_usd != null
            ? ' <span style="font-size:11px;color:' + (s.unrealized_pnl_usd >= 0 ? 'var(--v2-green, #16a34a)' : 'var(--v2-red, #dc2626)') + '">' +
              (s.unrealized_pnl_usd >= 0 ? '+' : '-') + formatCurrency(Math.abs(s.unrealized_pnl_usd)) + '</span>'
            : '';
        // Click anywhere on the row (outside the checkbox/delete) to edit it (WQ-0384).
        html += '<tr style="opacity:' + (s.include_in_total === 1 ? '1' : '0.55') + ';cursor:pointer" ' +
            'onclick="v2OpenEditStockModal(' + s.id + ')" title="Click to edit">' +
            '<td onclick="event.stopPropagation()"><input type="checkbox" ' + (s.include_in_total === 1 ? 'checked' : '') +
            ' style="margin-right:8px;vertical-align:middle" title="Include in portfolio total" ' +
            'onchange="v2ToggleStock(' + s.id + ', this.checked)">' +
            '<strong>' + escapeHtml(s.symbol) + '</strong></td>' +
            '<td>' + escapeHtml(s.name || s.symbol) + '</td>' +
            '<td style="color:var(--v2-text-secondary)">' + (s.description ? escapeHtml(s.description) : '<span style="color:var(--v2-text-muted)">--</span>') + '</td>' +
            '<td class="right v2-blur">' + Number(s.quantity).toLocaleString() + '</td>' +
            '<td class="right">' + (s.price_usd != null ? formatPrice(s.price_usd) : '--') + '</td>' +
            '<td class="right">' + chgHtml + '</td>' +
            '<td class="right v2-blur">' + (s.value_usd != null ? formatCurrency(s.value_usd) + pnl : '--') + '</td>' +
            '<td class="right" onclick="event.stopPropagation()"><button class="v2-btn v2-btn-ghost v2-btn-sm" style="color:var(--v2-red)" ' +
            'onclick="v2DeleteStock(' + s.id + ')" title="Remove holding">&times;</button></td>' +
            '</tr>';
    });
    html += '</tbody></table>';
    setSafeHTML(container, html);
}

// One modal for both add and edit (WQ-0384): pass a stock id to edit.
function v2OpenAddStockModal() { v2OpenStockModal(null); }

function v2OpenEditStockModal(stockId) { v2OpenStockModal(stockId); }

function v2OpenStockModal(stockId) {
    const stock = stockId ? (v2StocksData && (v2StocksData.stocks || []).find(s => s.id === stockId)) : null;
    v2StockEditId = stock ? stockId : null;
    v2StockLookup = stock ? { found: true, asset_class: stock.asset_class } : null;

    document.getElementById('v2StockModalTitle').textContent =
        stock ? ('Edit ' + stock.symbol) : 'Add Stock / ETF Holding';
    const symInput = document.getElementById('v2StockSymbol');
    symInput.value = stock ? stock.symbol : '';
    symInput.readOnly = !!stock;  // the ticker identifies the holding; not editable
    document.getElementById('v2StockQty').value = stock ? stock.quantity : '';
    document.getElementById('v2StockCost').value = (stock && stock.cost_basis != null) ? stock.cost_basis : '';
    document.getElementById('v2StockDesc').value = (stock && stock.description) ? stock.description : '';

    const result = document.getElementById('v2StockLookupResult');
    if (result) { result.style.display = 'none'; setSafeHTML(result, ''); }
    document.getElementById('v2StockAddBtn').textContent = stock ? 'Save Changes' : 'Add Stock';

    document.getElementById('v2StockOverlay').classList.add('open');
    document.getElementById('v2StockModal').classList.add('open');
    (stock ? document.getElementById('v2StockQty') : symInput).focus();
}

function v2CloseAddStockModal() {
    document.getElementById('v2StockOverlay').classList.remove('open');
    document.getElementById('v2StockModal').classList.remove('open');
}

// Debounced live ticker validation as the user types
function v2OnStockSymbolInput() {
    clearTimeout(_v2StockLookupTimer);
    const symbol = document.getElementById('v2StockSymbol').value.trim().toUpperCase();
    const result = document.getElementById('v2StockLookupResult');
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol)) {
        result.style.display = 'none';
        v2StockLookup = null;
        return;
    }
    _v2StockLookupTimer = setTimeout(async function () {
        try {
            const resp = await v2Fetch('/stocks/search?q=' + encodeURIComponent(symbol));
            const data = await resp.json();
            result.style.display = 'block';
            if (data.found) {
                v2StockLookup = data;
                const chg = data.change_pct;
                setSafeHTML(result,
                    '<span style="color:var(--v2-green, #16a34a)">&#10003; <strong>' + escapeHtml(data.name || data.symbol) + '</strong>' +
                    ' (' + escapeHtml((data.asset_class || 'stock').toUpperCase()) +
                    (data.exchange ? ' &middot; ' + escapeHtml(data.exchange) : '') + ')</span>' +
                    ' <span style="color:var(--v2-text-secondary)">' + formatPrice(Number(data.price_usd)) +
                    (chg != null ? ' <span style="color:' + (chg >= 0 ? 'var(--v2-green, #16a34a)' : 'var(--v2-red, #dc2626)') + '">' +
                        (chg >= 0 ? '+' : '') + Number(chg).toFixed(2) + '%</span>' : '') +
                    ' <small style="color:var(--v2-text-muted)">via ' + escapeHtml(data.source || 'feed') + '</small></span>');
            } else {
                v2StockLookup = null;
                setSafeHTML(result, '<span style="color:var(--v2-red)">No public quote found for ' + escapeHtml(symbol) + ' — check the exact listed ticker.</span>');
            }
        } catch (e) {
            console.error('stock lookup failed:', e);
        }
    }, 400);
}

async function v2SubmitStockAdd() {
    const result = document.getElementById('v2StockLookupResult');
    const symbol = document.getElementById('v2StockSymbol').value.trim().toUpperCase();
    const quantity = parseFloat(document.getElementById('v2StockQty').value);
    const costBasis = document.getElementById('v2StockCost').value;
    const description = document.getElementById('v2StockDesc').value.trim();

    function showErr(msg) {
        result.style.display = 'block';
        setSafeHTML(result, '<span style="color:var(--v2-red)">' + escapeHtml(msg) + '</span>');
    }
    if (!symbol || !(quantity > 0)) return showErr('Enter a ticker and a quantity greater than zero.');

    const btn = document.getElementById('v2StockAddBtn');
    btn.disabled = true;
    const editing = v2StockEditId != null;
    btn.textContent = editing ? 'Saving...' : 'Adding...';
    try {
        let resp;
        if (editing) {
            // Edit: PUT the mutable fields; description always sent (empty = clear).
            const body = { quantity: quantity, description: description || null };
            if (costBasis) body.cost_basis = parseFloat(costBasis);
            else body.cost_basis = null;
            resp = await v2Fetch('/stocks/' + v2StockEditId, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
        } else {
            const body = { symbol: symbol, quantity: quantity, asset_class: (v2StockLookup && v2StockLookup.asset_class) || 'stock' };
            if (costBasis) body.cost_basis = parseFloat(costBasis);
            if (description) body.description = description;
            resp = await v2Fetch('/stocks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
        }
        const data = await resp.json().catch(function () { return {}; });
        if (!resp.ok) return showErr(data.detail || ('Could not ' + (editing ? 'update ' : 'add ') + symbol));
        v2CloseAddStockModal();
        v2InvalidateStockCaches();
        await loadStocksTab();
        const priced = data.stock && data.stock.price_usd != null
            ? ' — priced at ' + formatPrice(data.stock.price_usd) : '';
        showToast(symbol + (editing ? ' updated' : ' added') + priced, 'success');
    } catch (e) {
        console.error('Error saving stock:', e);
        showErr('Error saving stock. Please try again.');
    } finally {
        btn.disabled = false;
        btn.textContent = editing ? 'Save Changes' : 'Add Stock';
    }
}

// After any stock mutation, drop the dashboard caches so the hero/table pick
// the new value up on the next load instead of serving a stale 30-60s entry.
function v2InvalidateStockCaches() {
    if (typeof V2_CACHE === 'undefined') return;
    V2_CACHE.clearByPrefix('/stocks');
    V2_CACHE.clearByPrefix('/portfolio/instant');
    V2_CACHE.clearByPrefix('/portfolio/all-holdings');
    V2_CACHE.clearByPrefix('/portfolio/summary');
}

async function v2ToggleStock(stockId, include) {
    try {
        const resp = await v2Fetch('/stocks/' + stockId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_in_total: include ? 1 : 0 })
        });
        if (!resp.ok) throw new Error('toggle failed');
        v2InvalidateStockCaches();
        await loadStocksTab();
    } catch (e) {
        console.error('Error toggling stock tracking:', e);
        showToast('Could not update tracking', 'error');
        await loadStocksTab();
    }
}

async function v2DeleteStock(stockId) {
    if (!confirm('Remove this stock holding?')) return;
    try {
        const resp = await v2Fetch('/stocks/' + stockId, { method: 'DELETE' });
        if (resp.ok) {
            v2InvalidateStockCaches();
            await loadStocksTab();
            showToast('Stock holding removed', 'success');
        } else {
            showToast('Error removing stock holding', 'error');
        }
    } catch (e) {
        console.error('Error deleting stock:', e);
        showToast('Error removing stock holding', 'error');
    }
}
