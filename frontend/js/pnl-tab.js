/**
 * P&L Tab - Profit & Loss tracking UI for the Assets page.
 *
 * Renders summary cards, positions table, realized history,
 * monthly chart (Chart.js), and manual lot entry form.
 */

// --- Module state ---
let _pnlSummary = null;
let _pnlUnrealized = [];
let _pnlRealized = [];
let _pnlMonthly = [];
let _pnlSortCol = 'unrealized_gain';
let _pnlSortAsc = false;
let _pnlCurrentSubView = 'positions';
let _pnlRealizedLoaded = false;
let _pnlTimeLoaded = false;
let _pnlChart = null;
let _pnlExpandedSymbol = null;

// --- Entry point ---

async function loadPnlTab() {
    const container = document.getElementById('pnlContent');
    if (!container) return;

    setSafeHTML(container, '<p class="loading-state">Loading P&L data...</p>');

    try {
        const [summaryRes, unrealizedRes] = await Promise.all([
            authFetch('/pnl/summary'),
            authFetch('/pnl/unrealized')
        ]);

        if (!summaryRes.ok || !unrealizedRes.ok) {
            throw new Error('Failed to fetch P&L data');
        }

        _pnlSummary = await summaryRes.json();
        _pnlUnrealized = await unrealizedRes.json();

        renderPnlTab();
    } catch (err) {
        console.error('P&L load error:', err);
        setSafeHTML(container, `
            <div class="pnl-empty-state">
                <p>Failed to load P&L data. Make sure the P&L engine has been initialized.</p>
                <button class="btn btn-primary btn-small" data-action="compute">Compute from Exchanges</button>
            </div>
        `);
        container.querySelectorAll('[data-action="compute"]').forEach(btn => {
            btn.addEventListener('click', () => refreshPnl());
        });
    }
}

// --- Full tab render ---

function renderPnlTab() {
    const container = document.getElementById('pnlContent');
    if (!container) return;

    const hasData = _pnlSummary && (_pnlSummary.assets_count > 0 || _pnlSummary.total_realized !== 0);

    let html = '';

    // Header row with actions
    html += `
        <div class="pnl-header-row">
            <h2 style="margin:0; color:#e0e0e0;">Profit &amp; Loss</h2>
            <div class="pnl-header-actions">
                <button class="btn btn-secondary btn-small" data-action="refresh" title="Recompute P&L from exchange data">&#10227; Refresh</button>
                <button class="btn btn-primary btn-small" data-action="add-entry">+ Add Entry</button>
            </div>
        </div>
    `;

    if (!hasData) {
        html += `
            <div class="pnl-empty-state">
                <h3 style="color:#e0e0e0;">No cost basis data yet</h3>
                <p>Import transactions from exchanges or add entries manually to start tracking profit &amp; loss.</p>
                <button class="btn btn-primary btn-small" data-action="compute">Compute from Exchanges</button>
                <button class="btn btn-secondary btn-small" data-action="add-entry">+ Add Entry</button>
            </div>
        `;
        setSafeHTML(container, html);
        _attachPnlHeaderListeners(container);
        return;
    }

    // Summary cards
    html += renderPnlSummary(_pnlSummary);

    // Gainers/Losers
    html += renderGainersLosers(_pnlSummary);

    // Sub-tabs
    html += `
        <div class="pnl-subtabs" id="pnlSubtabs">
            <button class="pnl-subtab-btn active" data-subview="positions">Positions</button>
            <button class="pnl-subtab-btn" data-subview="realized">Realized History</button>
            <button class="pnl-subtab-btn" data-subview="time">Time View</button>
        </div>
    `;

    // Sub-view content area
    html += '<div id="pnlSubViewContent"></div>';

    setSafeHTML(container, html);
    _attachPnlHeaderListeners(container);

    // Attach sub-tab listeners
    container.querySelectorAll('.pnl-subtab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchPnlSubView(btn.dataset.subview);
        });
    });

    // Render default sub-view
    switchPnlSubView('positions');
}

function _attachPnlHeaderListeners(container) {
    container.querySelectorAll('[data-action="refresh"]').forEach(btn => {
        btn.addEventListener('click', () => refreshPnl());
    });
    container.querySelectorAll('[data-action="add-entry"]').forEach(btn => {
        btn.addEventListener('click', () => openManualLotModal());
    });
    container.querySelectorAll('[data-action="compute"]').forEach(btn => {
        btn.addEventListener('click', () => refreshPnl());
    });
}

// --- Refresh P&L ---

let _pnlComputeInProgress = false;
let _pnlPollTimer = null;
let _pnlLastStatusMsg = '';

async function refreshPnl() {
    if (_pnlComputeInProgress) {
        showStatus('P&L computation already in progress...');
        return;
    }

    _pnlComputeInProgress = true;
    _pnlLastStatusMsg = '';
    showStatus('Starting P&L computation...');

    try {
        // Fire-and-forget: backend returns 202 immediately, runs in background
        const res = await authFetch('/pnl/compute?include_wallets=true', { method: 'POST' });
        if (res.status === 409) {
            // Already running — just attach to the existing poll
        } else if (!res.ok) {
            throw new Error('Compute failed to start');
        }

        // Poll status until complete or error
        await _pollUntilComplete();

        // Reset lazy-load flags so sub-views reload
        _pnlRealizedLoaded = false;
        _pnlTimeLoaded = false;
        _pnlExpandedSymbol = null;

        // Reload tab data
        window._pnlLoaded = false;
        await loadPnlTab();
        showStatus('P&L data refreshed successfully');
    } catch (err) {
        _stopProgressPolling();
        console.error('P&L refresh error:', err);
        showStatus(err.message || 'Failed to refresh P&L data', true);
    } finally {
        _pnlComputeInProgress = false;
        _pnlLastStatusMsg = '';
    }
}

function _pollUntilComplete() {
    return new Promise((resolve, reject) => {
        _stopProgressPolling();
        _pnlPollTimer = setInterval(async () => {
            try {
                const res = await authFetch('/pnl/compute/status');
                if (!res.ok) return;
                const status = await res.json();

                if (status.stage === 'complete') {
                    _stopProgressPolling();
                    resolve();
                    return;
                }
                if (status.stage === 'error') {
                    _stopProgressPolling();
                    reject(new Error(`P&L computation failed: ${status.details || 'Unknown error'}`));
                    return;
                }
                if (status.stage === 'idle') return;

                // Only update banner when message actually changes
                const stage = status.stage.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const msg = `${stage} (${status.progress}%) \u2014 ${status.details || ''}`;
                if (msg !== _pnlLastStatusMsg) {
                    _pnlLastStatusMsg = msg;
                    showStatus(msg);
                }
            } catch (_) { /* ignore poll errors */ }
        }, 1500);
    });
}

function _stopProgressPolling() {
    if (_pnlPollTimer) {
        clearInterval(_pnlPollTimer);
        _pnlPollTimer = null;
    }
}

// --- Summary cards ---

function renderPnlSummary(summary) {
    const unrealizedClass = summary.total_unrealized >= 0 ? 'positive' : 'negative';
    const realizedClass = summary.total_realized >= 0 ? 'positive' : 'negative';
    const overallClass = summary.total_pnl >= 0 ? 'positive' : 'negative';
    const pctSign = summary.pnl_percent >= 0 ? '+' : '';

    return `
        <div class="pnl-summary-row">
            <div class="pnl-card">
                <div class="pnl-card-label">Total Invested</div>
                <div class="pnl-card-value">${formatUSDBlur(summary.total_invested)}</div>
            </div>
            <div class="pnl-card">
                <div class="pnl-card-label">Current Value</div>
                <div class="pnl-card-value">${formatUSDBlur(summary.current_value)}</div>
            </div>
            <div class="pnl-card">
                <div class="pnl-card-label">Unrealized P&amp;L</div>
                <div class="pnl-card-value ${unrealizedClass}">${formatUSDBlur(summary.total_unrealized)}</div>
            </div>
            <div class="pnl-card">
                <div class="pnl-card-label">Realized P&amp;L</div>
                <div class="pnl-card-value ${realizedClass}">${formatUSDBlur(summary.total_realized)}</div>
            </div>
            <div class="pnl-card hero">
                <div class="pnl-card-label">Overall Return</div>
                <div class="pnl-card-value ${overallClass}">
                    ${formatUSDBlur(summary.total_pnl)}
                    <span style="font-size:14px; margin-left:6px;">${pctSign}${summary.pnl_percent.toFixed(2)}%</span>
                </div>
            </div>
        </div>
    `;
}

// --- Gainers / Losers ---

function renderGainersLosers(summary) {
    const gainers = summary.top_gainers || [];
    const losers = summary.top_losers || [];

    if (gainers.length === 0 && losers.length === 0) return '';

    function renderMoverList(items, isGain) {
        if (items.length === 0) return '<div style="color:#666; font-size:13px;">None</div>';
        return items.map(item => {
            const cls = isGain ? 'gain' : 'loss';
            const sign = isGain ? '+' : '';
            const usd = formatUSD(Math.abs(item.unrealized_gain));
            const pct = item.unrealized_pct.toFixed(1);
            return `<div class="pnl-mover-item">
                <span class="symbol">${_escHtml(item.token_symbol)}</span>
                <span class="${cls}">${sign}$${usd.replace('$','')} (${sign}${pct}%)</span>
            </div>`;
        }).join('');
    }

    return `
        <div class="pnl-movers">
            <div class="pnl-movers-panel">
                <h3>Top Gainers</h3>
                ${renderMoverList(gainers, true)}
            </div>
            <div class="pnl-movers-panel">
                <h3>Top Losers</h3>
                ${renderMoverList(losers, false)}
            </div>
        </div>
    `;
}

// --- Sub-view switching ---

function switchPnlSubView(view) {
    _pnlCurrentSubView = view;

    // Update sub-tab active states
    document.querySelectorAll('#pnlSubtabs .pnl-subtab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.subview === view);
    });

    const target = document.getElementById('pnlSubViewContent');
    if (!target) return;

    if (view === 'positions') {
        renderPositionsTable(target);
    } else if (view === 'realized') {
        if (!_pnlRealizedLoaded) {
            loadRealizedHistory(target);
        } else {
            renderRealizedTable(target);
        }
    } else if (view === 'time') {
        if (!_pnlTimeLoaded) {
            loadTimeView(target, 12);
        } else {
            renderTimeView(target);
        }
    }
}

// --- Positions table ---

function renderPositionsTable(container) {
    if (!container) container = document.getElementById('pnlSubViewContent');
    if (!container) return;

    if (_pnlUnrealized.length === 0) {
        setSafeHTML(container, `
            <div class="pnl-empty-state">
                <p>No open positions with cost basis data.</p>
                <button class="btn btn-primary btn-small" data-action="compute">Compute from Exchanges</button>
                <button class="btn btn-secondary btn-small" data-action="add-entry">+ Add Entry</button>
            </div>
        `);
        _attachPnlHeaderListeners(container);
        return;
    }

    // Sort
    const sorted = [..._pnlUnrealized].sort((a, b) => {
        let va = a[_pnlSortCol], vb = b[_pnlSortCol];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return _pnlSortAsc ? -1 : 1;
        if (va > vb) return _pnlSortAsc ? 1 : -1;
        return 0;
    });

    const cols = [
        { key: 'token_symbol', label: 'Symbol' },
        { key: 'total_quantity', label: 'Qty', align: 'right' },
        { key: 'avg_cost_basis', label: 'Avg Cost', align: 'right' },
        { key: 'current_price', label: 'Price', align: 'right' },
        { key: 'total_invested', label: 'Invested', align: 'right' },
        { key: 'current_value', label: 'Value', align: 'right' },
        { key: 'unrealized_gain', label: 'P&L ($)', align: 'right' },
        { key: 'unrealized_pct', label: 'P&L (%)', align: 'right' },
    ];

    let html = '<table class="pnl-table"><thead><tr>';
    for (const col of cols) {
        const activeClass = _pnlSortCol === col.key ? ' sort-active' : '';
        const arrow = _pnlSortCol === col.key ? (_pnlSortAsc ? ' &#9650;' : ' &#9660;') : '';
        const align = col.align === 'right' ? ' class="text-right' + activeClass + '"' : ' class="' + activeClass + '"';
        html += `<th${align} data-sort="${col.key}">${col.label}${arrow}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (const item of sorted) {
        const gainClass = item.unrealized_gain >= 0 ? 'positive' : 'negative';
        const sign = item.unrealized_gain >= 0 ? '+' : '';
        html += `<tr class="expandable" data-symbol="${_escHtml(item.token_symbol)}">
            <td><strong>${_escHtml(item.token_symbol)}</strong></td>
            <td class="text-right">${formatCryptoBlur(item.total_quantity, '')}</td>
            <td class="text-right">${formatUSDBlur(item.avg_cost_basis)}</td>
            <td class="text-right">${formatUSDBlur(item.current_price)}</td>
            <td class="text-right">${formatUSDBlur(item.total_invested)}</td>
            <td class="text-right">${formatUSDBlur(item.current_value)}</td>
            <td class="text-right pnl-card-value ${gainClass}" style="font-size:13px">${formatUSDBlur(item.unrealized_gain)}</td>
            <td class="text-right pnl-card-value ${gainClass}" style="font-size:13px">${sign}${item.unrealized_pct.toFixed(2)}%</td>
        </tr>`;

        // Lot expansion row (hidden by default)
        html += `<tr class="pnl-lot-row" data-lot-symbol="${_escHtml(item.token_symbol)}" style="display:none;">
            <td colspan="8" style="padding:0;">
                <div class="pnl-lots-container" id="lots-${_escHtml(item.token_symbol)}">
                    <p style="color:#888; font-size:12px;">Loading lots...</p>
                </div>
            </td>
        </tr>`;
    }

    html += '</tbody></table>';
    setSafeHTML(container, html);

    // Attach sort listeners
    container.querySelectorAll('.pnl-table th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            sortPositions(th.dataset.sort);
        });
    });

    // Attach row expansion listeners
    container.querySelectorAll('.pnl-table tr.expandable').forEach(tr => {
        tr.addEventListener('click', () => {
            const symbol = tr.dataset.symbol;
            if (_pnlExpandedSymbol === symbol) {
                collapseAssetRow();
            } else {
                expandAssetRow(symbol);
            }
        });
    });
}

function sortPositions(col) {
    if (_pnlSortCol === col) {
        _pnlSortAsc = !_pnlSortAsc;
    } else {
        _pnlSortCol = col;
        _pnlSortAsc = col === 'token_symbol'; // alpha ascending default, numbers descending
    }
    renderPositionsTable();
}

// --- Lot expansion ---

async function expandAssetRow(symbol) {
    collapseAssetRow(); // collapse any currently open

    _pnlExpandedSymbol = symbol;
    const lotRow = document.querySelector(`.pnl-lot-row[data-lot-symbol="${symbol}"]`);
    if (lotRow) lotRow.style.display = '';

    const lotsContainer = document.getElementById(`lots-${symbol}`);
    if (!lotsContainer) return;

    setSafeHTML(lotsContainer, '<p style="color:#888; font-size:12px;">Loading lots...</p>');

    try {
        const res = await authFetch(`/pnl/lots/${encodeURIComponent(symbol)}`);
        if (!res.ok) throw new Error('Failed');
        const lots = await res.json();

        if (lots.length === 0) {
            setSafeHTML(lotsContainer, '<p style="color:#888; font-size:12px;">No open lots for this asset.</p>');
            return;
        }

        let html = `<table>
            <thead><tr>
                <th>Date</th><th>Type</th><th>Source</th>
                <th>Quantity</th><th>Remaining</th><th>Cost/Unit</th><th>Total Cost</th>
            </tr></thead><tbody>`;

        for (const lot of lots) {
            const date = lot.acquisition_date ? lot.acquisition_date.substring(0, 10) : '-';
            html += `<tr>
                <td>${_escHtml(date)}</td>
                <td>${_escHtml(lot.acquisition_type || '-')}</td>
                <td>${_escHtml(lot.acquisition_source || '-')}</td>
                <td>${formatCryptoBlur(lot.quantity, '')}</td>
                <td>${formatCryptoBlur(lot.remaining_quantity, '')}</td>
                <td>${formatUSDBlur(lot.cost_per_unit_usd)}</td>
                <td>${formatUSDBlur(lot.remaining_quantity * lot.cost_per_unit_usd)}</td>
            </tr>`;
        }

        html += '</tbody></table>';
        setSafeHTML(lotsContainer, html);
    } catch (err) {
        setSafeHTML(lotsContainer, '<p style="color:#ff4757; font-size:12px;">Failed to load lots.</p>');
    }
}

function collapseAssetRow() {
    if (_pnlExpandedSymbol) {
        const lotRow = document.querySelector(`.pnl-lot-row[data-lot-symbol="${_pnlExpandedSymbol}"]`);
        if (lotRow) lotRow.style.display = 'none';
        _pnlExpandedSymbol = null;
    }
}

// --- Realized History ---

async function loadRealizedHistory(container) {
    if (!container) container = document.getElementById('pnlSubViewContent');
    if (!container) return;

    setSafeHTML(container, '<p class="loading-state">Loading realized gains...</p>');

    try {
        const res = await authFetch('/pnl/realized');
        if (!res.ok) throw new Error('Failed');
        _pnlRealized = await res.json();
        _pnlRealizedLoaded = true;
        renderRealizedTable(container);
    } catch (err) {
        setSafeHTML(container, '<p class="pnl-empty-state">Failed to load realized gains.</p>');
    }
}

function renderRealizedTable(container) {
    if (!container) container = document.getElementById('pnlSubViewContent');
    if (!container) return;

    if (_pnlRealized.length === 0) {
        setSafeHTML(container, '<div class="pnl-empty-state"><p>No realized gains recorded yet.</p></div>');
        return;
    }

    // Build token filter options
    const tokens = [...new Set(_pnlRealized.map(r => r.token_symbol))].sort();

    let html = `
        <div class="pnl-filters">
            <select id="pnlRealizedTokenFilter">
                <option value="">All Tokens</option>
                ${tokens.map(t => `<option value="${_escHtml(t)}">${_escHtml(t)}</option>`).join('')}
            </select>
            <input type="date" id="pnlRealizedStartDate" title="Start date">
            <input type="date" id="pnlRealizedEndDate" title="End date">
            <button class="btn btn-secondary btn-small" id="pnlRealizedFilterBtn">Filter</button>
        </div>
    `;

    html += '<div id="pnlRealizedTableWrap">';
    html += _buildRealizedTableHtml(_pnlRealized);
    html += '</div>';

    setSafeHTML(container, html);

    // Attach filter listeners
    const filterBtn = container.querySelector('#pnlRealizedFilterBtn');
    if (filterBtn) {
        filterBtn.addEventListener('click', () => applyRealizedFilters());
    }

    const tokenFilter = container.querySelector('#pnlRealizedTokenFilter');
    if (tokenFilter) {
        tokenFilter.addEventListener('change', () => applyRealizedFilters());
    }
}

function _buildRealizedTableHtml(data) {
    if (data.length === 0) {
        return '<div class="pnl-empty-state"><p>No matching realized gains.</p></div>';
    }

    let html = `<table class="pnl-table">
        <thead><tr>
            <th>Date</th><th>Symbol</th><th>Type</th>
            <th class="text-right">Qty</th><th class="text-right">Proceeds</th>
            <th class="text-right">Cost Basis</th><th class="text-right">P&amp;L</th>
            <th>Holding</th>
        </tr></thead><tbody>`;

    for (const r of data) {
        const date = r.disposal_date ? r.disposal_date.substring(0, 10) : '-';
        const gainClass = r.gain_loss_usd >= 0 ? 'positive' : 'negative';
        html += `<tr>
            <td>${_escHtml(date)}</td>
            <td><strong>${_escHtml(r.token_symbol)}</strong></td>
            <td>${_escHtml(r.disposal_type || '-')}</td>
            <td class="text-right">${formatCryptoBlur(r.quantity, '')}</td>
            <td class="text-right">${formatUSDBlur(r.proceeds_usd)}</td>
            <td class="text-right">${formatUSDBlur(r.cost_basis_usd)}</td>
            <td class="text-right pnl-card-value ${gainClass}" style="font-size:13px">${formatUSDBlur(r.gain_loss_usd)}</td>
            <td>${_escHtml(r.holding_period || '-')}</td>
        </tr>`;
    }

    html += '</tbody></table>';
    return html;
}

async function applyRealizedFilters() {
    const tokenFilter = document.getElementById('pnlRealizedTokenFilter');
    const startDate = document.getElementById('pnlRealizedStartDate');
    const endDate = document.getElementById('pnlRealizedEndDate');
    const wrap = document.getElementById('pnlRealizedTableWrap');
    if (!wrap) return;

    const token = tokenFilter ? tokenFilter.value : '';
    const start = startDate ? startDate.value : '';
    const end = endDate ? endDate.value : '';

    // If date filters are set, re-fetch from API
    if (start || end) {
        setSafeHTML(wrap, '<p class="loading-state">Filtering...</p>');
        try {
            let url = '/pnl/realized?';
            if (token) url += `token=${encodeURIComponent(token)}&`;
            if (start) url += `start_date=${encodeURIComponent(start)}&`;
            if (end) url += `end_date=${encodeURIComponent(end)}&`;
            const res = await authFetch(url);
            if (!res.ok) throw new Error('Failed');
            const filtered = await res.json();
            setSafeHTML(wrap, _buildRealizedTableHtml(filtered));
        } catch (err) {
            setSafeHTML(wrap, '<p style="color:#ff4757;">Failed to filter realized gains.</p>');
        }
    } else {
        // Client-side token filter only
        const filtered = token
            ? _pnlRealized.filter(r => r.token_symbol === token)
            : _pnlRealized;
        setSafeHTML(wrap, _buildRealizedTableHtml(filtered));
    }
}

// --- Time View (Chart) ---

async function loadTimeView(container, months) {
    if (!container) container = document.getElementById('pnlSubViewContent');
    if (!container) return;

    setSafeHTML(container, '<p class="loading-state">Loading chart data...</p>');

    try {
        const res = await authFetch(`/pnl/realized/monthly?months=${months}`);
        if (!res.ok) throw new Error('Failed');
        _pnlMonthly = await res.json();
        _pnlTimeLoaded = true;
        renderTimeView(container, months);
    } catch (err) {
        setSafeHTML(container, '<p class="pnl-empty-state">Failed to load chart data.</p>');
    }
}

function renderTimeView(container, activePeriod) {
    if (!container) container = document.getElementById('pnlSubViewContent');
    if (!container) return;

    if (_pnlMonthly.length === 0) {
        setSafeHTML(container, '<div class="pnl-empty-state"><p>No realized gains to chart.</p></div>');
        return;
    }

    activePeriod = activePeriod || 12;

    const periods = [
        { label: '3M', months: 3 },
        { label: '6M', months: 6 },
        { label: '1Y', months: 12 },
        { label: '2Y', months: 24 },
        { label: 'All', months: 60 },
    ];

    let html = '<div class="pnl-period-btns" id="pnlPeriodBtns">';
    for (const p of periods) {
        const active = p.months === activePeriod ? ' active' : '';
        html += `<button class="pnl-period-btn${active}" data-months="${p.months}">${p.label}</button>`;
    }
    html += '</div>';

    html += '<div class="pnl-chart-container"><canvas id="pnlMonthlyChart"></canvas></div>';

    const totalRealized = _pnlMonthly.reduce((sum, m) => sum + m.realized, 0);
    const totalClass = totalRealized >= 0 ? 'positive' : 'negative';
    html += `<div class="pnl-chart-summary">Period realized: <span class="pnl-card-value ${totalClass}" style="font-size:13px">${formatUSD(totalRealized)}</span></div>`;

    setSafeHTML(container, html);

    // Attach period button listeners
    container.querySelectorAll('#pnlPeriodBtns .pnl-period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            updateTimePeriod(parseInt(btn.dataset.months, 10));
        });
    });

    // Render chart
    renderTimeChart(_pnlMonthly);
}

function renderTimeChart(data) {
    // Destroy old chart
    if (_pnlChart) {
        _pnlChart.destroy();
        _pnlChart = null;
    }

    const canvas = document.getElementById('pnlMonthlyChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = data.map(d => d.month);
    const values = data.map(d => d.realized);
    const colors = values.map(v => v >= 0 ? '#00d26a' : '#ff4757');
    const borderColors = values.map(v => v >= 0 ? '#00b359' : '#e6324a');

    _pnlChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Realized P&L',
                data: values,
                backgroundColor: colors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return 'Realized: ' + formatUSD(ctx.parsed.y);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#888', font: { size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#888',
                        font: { size: 11 },
                        callback: function(value) { return formatUSD(value); }
                    }
                }
            }
        }
    });
}

async function updateTimePeriod(months) {
    _pnlTimeLoaded = false;
    const container = document.getElementById('pnlSubViewContent');
    await loadTimeView(container, months);
}

// --- Manual Lot Modal ---

function openManualLotModal() {
    const modal = document.getElementById('manualLotModal');
    if (modal) modal.classList.add('active');

    // Reset form
    const form = document.getElementById('manualLotForm');
    if (form) form.reset();

    // Set default source
    const sourceInput = document.getElementById('lotSource');
    if (sourceInput) sourceInput.value = 'manual';
}

function closeManualLotModal() {
    const modal = document.getElementById('manualLotModal');
    if (modal) modal.classList.remove('active');
}

async function submitManualLot(e) {
    e.preventDefault();

    const symbol = document.getElementById('lotTokenSymbol').value.trim().toUpperCase();
    const quantity = parseFloat(document.getElementById('lotQuantity').value);
    const costPerUnit = parseFloat(document.getElementById('lotCostPerUnit').value);
    const acqDate = document.getElementById('lotAcquisitionDate').value || null;
    const source = document.getElementById('lotSource').value.trim() || 'manual';

    if (!symbol || isNaN(quantity) || quantity <= 0 || isNaN(costPerUnit) || costPerUnit < 0) {
        showStatus('Please fill in all required fields correctly', true);
        return;
    }

    try {
        const res = await authFetch('/pnl/lots/manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token_symbol: symbol,
                quantity: quantity,
                cost_per_unit: costPerUnit,
                acquisition_date: acqDate,
                source: source
            })
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to add entry');
        }

        closeManualLotModal();
        showStatus(`Added cost basis entry for ${symbol}`);

        // Refresh P&L data
        _pnlRealizedLoaded = false;
        _pnlTimeLoaded = false;
        window._pnlLoaded = false;
        await loadPnlTab();
    } catch (err) {
        showStatus(err.message || 'Failed to add manual entry', true);
    }
}

// --- Init modal listeners ---
document.addEventListener('DOMContentLoaded', () => {
    // Cancel button for manual lot modal
    const cancelBtn = document.getElementById('btnCancelLot');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeManualLotModal);
    }

    // Form submit
    const form = document.getElementById('manualLotForm');
    if (form) {
        form.addEventListener('submit', submitManualLot);
    }

    // Close modal on overlay click
    const modal = document.getElementById('manualLotModal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeManualLotModal();
        });
    }
});

// --- Utility ---

function _escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}
