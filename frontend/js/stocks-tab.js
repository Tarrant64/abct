/**
 * Stocks Tab (WQ-0382) -- manual stock/ETF holdings on the keyless stock feed.
 *
 * Assets-page tab mirroring the Custom Tokens tab's behavior:
 *   - lazy-loaded on first tab visit (switchAssetsTab hook in assets.html)
 *   - tracked/untracked toggle feeds the portfolio total (stocksValue)
 *   - add dialog validates the ticker against the live feed (CNBC/Nasdaq)
 *     before POSTing, then backfills history server-side
 *
 * Depends on app.js globals: API_BASE, authFetch, showStatus, formatUSD,
 * setSafeHTML, scheduleUpdateTotalPortfolioValue, isDemoMode.
 */

// `stocks` and `stocksValue` are DECLARED in app.js: classic top-level `let`
// bindings are shared across scripts, so re-declaring them HERE would throw a
// SyntaxError that kills the whole file. Assign only.
let isTogglingStock = false;

async function loadStocks() {
    try {
        const response = await authFetch(`${API_BASE}/stocks`);
        const data = await response.json();
        stocks = data.stocks || [];
        stocksValue = data.tracked_total_usd || 0;
        displayStocks(data);
    } catch (error) {
        console.error('Error loading stocks:', error);
    }
}

function displayStocks(data) {
    const list = document.getElementById('stocksList');
    const summary = document.getElementById('stocksSummary');
    if (!list) return;

    if (summary) {
        const count = (data.stocks || []).length;
        const tracked = data.tracked_total_usd || 0;
        setSafeHTML(summary, `
            <span>${count} holding${count !== 1 ? 's' : ''}</span>
            ${tracked > 0 ? `<span class="tracked-value">Tracked: ${formatUSD(tracked)}</span>` : ''}
        `);
    }

    if (!data.stocks || data.stocks.length === 0) {
        setSafeHTML(list, '<p class="empty-state">No stocks tracked yet. Use "+ Add Stock" to add shares or ETF units manually (prices refresh at market open, midday and close).</p>');
        scheduleUpdateTotalPortfolioValue();
        return;
    }

    let html = '';
    for (const s of data.stocks) {
        const isTracked = s.include_in_total === 1;
        const qty = Number(s.quantity).toLocaleString();
        const price = s.price_usd != null ? `$${s.price_usd.toFixed(2)}` : '--';
        const value = s.value_usd != null ? formatUSD(s.value_usd) : 'N/A';
        const chg = s.change_pct;
        const chgHtml = chg == null ? '' :
            `<span class="stock-change ${chg >= 0 ? 'up' : 'down'}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</span>`;
        const pnlHtml = s.unrealized_pnl_usd != null ?
            `<span class="stock-pnl ${s.unrealized_pnl_usd >= 0 ? 'up' : 'down'}" title="Unrealized P&L">${s.unrealized_pnl_usd >= 0 ? '+' : '-'}${formatUSD(Math.abs(s.unrealized_pnl_usd))}</span>` : '';
        const stamp = s.last_price_update ?
            `<span class="stock-stamp">${formatRefreshTimestamp(s.last_price_update)}</span>` : '';
        const valueNum = s.value_usd || 0;

        html += `
            <div class="custom-token-item stock ${isTracked ? 'tracked' : ''}"
                 data-stock-id="${s.id}" data-value="${valueNum}">
                <div class="token-toggle">
                    <label class="toggle-switch">
                        <input type="checkbox" ${isTracked ? 'checked' : ''}
                               onchange="toggleStockTracking(${s.id}, this.checked, ${valueNum})">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="token-info">
                    <div class="token-name">${escapeHtmlStock(s.name || s.symbol)}</div>
                    <div class="token-meta">
                        <span class="token-chain">${escapeHtmlStock(s.symbol)}</span>
                        <span class="token-price">${price}</span>
                        ${chgHtml}
                        ${stamp}
                    </div>
                </div>
                <div class="token-values">
                    <div class="token-quantity">${qty} sh</div>
                    <div class="token-usd">${value} ${pnlHtml}</div>
                </div>
                <button class="delete-token-btn" onclick="deleteStock(${s.id})" title="Remove holding">&times;</button>
            </div>
        `;
    }
    setSafeHTML(list, html);
    scheduleUpdateTotalPortfolioValue();
}

function escapeHtmlStock(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function openAddStockModal() {
    if (window.isDemoMode && window.isDemoMode()) { window.showDemoModeAlert(); return; }
    const modal = document.getElementById('addStockModal');
    document.getElementById('stockSymbolInput').value = '';
    document.getElementById('stockQuantityInput').value = '';
    document.getElementById('stockCostBasisInput').value = '';
    const result = document.getElementById('stockLookupResult');
    result.classList.add('hidden');
    setSafeHTML(result, '');
    window._stockLookup = null;
    modal.classList.remove('hidden');
    document.getElementById('stockSymbolInput').focus();
}

function closeStockModal() {
    document.getElementById('addStockModal').classList.add('hidden');
}

let _stockLookupTimer = null;

// Debounced live validation as the user types the ticker
function onStockSymbolInput() {
    clearTimeout(_stockLookupTimer);
    const symbol = document.getElementById('stockSymbolInput').value.trim().toUpperCase();
    const result = document.getElementById('stockLookupResult');
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol)) {
        result.classList.add('hidden');
        window._stockLookup = null;
        return;
    }
    _stockLookupTimer = setTimeout(async () => {
        try {
            const resp = await authFetch(`${API_BASE}/stocks/search?q=${encodeURIComponent(symbol)}`);
            const data = await resp.json();
            result.classList.remove('hidden');
            if (data.found) {
                window._stockLookup = data;
                const cls = (data.asset_class || 'stock').toUpperCase();
                const chg = data.change_pct;
                result.className = 'token-lookup-result';
                setSafeHTML(result, `
                    <span class="stock-found">&#10003; <strong>${escapeHtmlStock(data.name || data.symbol)}</strong>
                    (${cls} &middot; ${escapeHtmlStock(data.exchange || '')})</span>
                    <span class="stock-found-price">$${Number(data.price_usd).toFixed(2)}
                    ${chg != null ? `<span class="stock-change ${chg >= 0 ? 'up' : 'down'}">${chg >= 0 ? '+' : ''}${Number(chg).toFixed(2)}%</span>` : ''}
                    <small>via ${data.source}</small></span>
                `);
                // auto-class the select from the feed
                const sel = document.getElementById('stockClassSelect');
                if (sel && data.asset_class) sel.value = data.asset_class;
            } else {
                window._stockLookup = null;
                result.className = 'token-lookup-result error';
                setSafeHTML(result, `<span>No public quote found for ${escapeHtmlStock(symbol)} -- check the exact listed ticker.</span>`);
            }
        } catch (e) {
            console.error('stock lookup failed:', e);
        }
    }, 400);
}

async function submitStockAdd() {
    const result = document.getElementById('stockLookupResult');
    const symbol = document.getElementById('stockSymbolInput').value.trim().toUpperCase();
    const quantity = parseFloat(document.getElementById('stockQuantityInput').value);
    const costBasis = document.getElementById('stockCostBasisInput').value;
    const assetClass = document.getElementById('stockClassSelect').value;

    if (!symbol || !(quantity > 0)) {
        result.classList.remove('hidden');
        result.className = 'token-lookup-result error';
        setSafeHTML(result, '<span>Enter a ticker and a quantity greater than zero.</span>');
        return;
    }

    const btn = document.getElementById('stockAddBtn');
    btn.disabled = true;
    btn.textContent = 'Adding...';
    try {
        const body = { symbol, quantity, asset_class: assetClass };
        if (costBasis) body.cost_basis = parseFloat(costBasis);
        const resp = await authFetch(`${API_BASE}/stocks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            result.classList.remove('hidden');
            result.className = 'token-lookup-result error';
            setSafeHTML(result, `<span>${escapeHtmlStock(data.detail || 'Could not add ' + symbol)}</span>`);
            return;
        }
        closeStockModal();
        await loadStocks();
        showStatus(`${symbol} added -- ${data.stock && data.stock.price_usd != null ? 'priced at $' + data.stock.price_usd.toFixed(2) : 'awaiting next scheduled price run'}`, 'success');
    } catch (e) {
        console.error('Error adding stock:', e);
        result.classList.remove('hidden');
        result.className = 'token-lookup-result error';
        setSafeHTML(result, '<span>Error adding stock. Please try again.</span>');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Add Stock';
    }
}

async function toggleStockTracking(stockId, include, stockValue) {
    if (isTogglingStock) {
        const item = document.querySelector(`.stock[data-stock-id="${stockId}"] input[type="checkbox"]`);
        if (item) item.checked = !include;
        return;
    }
    isTogglingStock = true;
    const item = document.querySelector(`.stock[data-stock-id="${stockId}"]`);
    if (item) item.classList.toggle('tracked', include);
    const previous = stocksValue;
    stocksValue += include ? stockValue : -stockValue;
    scheduleUpdateTotalPortfolioValue();
    try {
        const resp = await authFetch(`${API_BASE}/stocks/${stockId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_in_total: include ? 1 : 0 })
        });
        if (!resp.ok) throw new Error('toggle failed');
    } catch (e) {
        console.error('Error toggling stock tracking:', e);
        if (item) {
            item.classList.toggle('tracked', !include);
            const cb = item.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = !include;
        }
        stocksValue = previous;
        scheduleUpdateTotalPortfolioValue();
    } finally {
        isTogglingStock = false;
    }
}

async function deleteStock(stockId) {
    if (window.isDemoMode && window.isDemoMode()) { window.showDemoModeAlert(); return; }
    if (!confirm('Remove this stock holding?')) return;
    try {
        const resp = await authFetch(`${API_BASE}/stocks/${stockId}`, { method: 'DELETE' });
        if (resp.ok) {
            await loadStocks();
            showStatus('Stock holding removed', 'success');
        } else {
            showStatus('Error removing stock holding', 'error');
        }
    } catch (e) {
        console.error('Error deleting stock:', e);
        showStatus('Error removing stock holding', 'error');
    }
}
