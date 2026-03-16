/**
 * ABCT V2 Dashboard — Main Application
 * Professional frontend redesign using same backend APIs as V1.
 *
 * API Endpoints Used:
 *   /portfolio/instant     — Quick portfolio totals
 *   /portfolio/summary     — Full portfolio with chain data
 *   /portfolio/all-holdings — All holdings for the assets table
 *   /prices/all            — All cached prices
 *   /balance-history/data  — Chart data
 *   /transactions/stats    — Transaction stats
 *   /exchanges/all         — Exchange balances
 *   /defi/summary          — DeFi positions
 *   /nfts/all/summary      — NFT totals
 *   /search                — Global search
 *   /auth/verify           — Auth verification
 *   /prices/global         — Global market data
 */

// ============================================================================
// AUTH & FETCH
// ============================================================================

const API_BASE = '';

async function v2Fetch(url, options = {}) {
    const token = localStorage.getItem('abct_token');
    if (token) {
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };
    }
    return fetch(url, options);
}

// ============================================================================
// STATE
// ============================================================================

let v2State = {
    portfolio: null,
    prices: {},
    holdings: [],
    chartData: null,
    sortCol: 'value',
    sortDir: 'desc',
    showZero: false,
    filterText: '',
    privacyMode: false,
    currentChartRange: '1w',
    sidebarCollapsed: localStorage.getItem('v2_sidebar_collapsed') === 'true',
    chartInstance: null,
    sparklines: {},
    totalPortfolioValue: 0,
};

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    // Apply saved theme
    loadSavedTheme();

    // Apply sidebar state
    if (v2State.sidebarCollapsed) {
        const sidebar = document.getElementById('v2Sidebar');
        const layout = document.getElementById('v2Layout');
        if (sidebar) sidebar.classList.add('collapsed');
        if (layout) layout.classList.add('sidebar-collapsed');
    }

    // Privacy mode
    v2State.privacyMode = localStorage.getItem('v2_privacy') === 'true';
    if (v2State.privacyMode) {
        document.body.classList.add('privacy-mode');
    }

    // Set active nav from current path
    setActiveNav();

    // Only load dashboard data on the main dashboard page (index.html)
    // Sub-pages handle their own data loading via inline scripts + v2-shell.js
    const isDashboard = document.getElementById('heroValue') !== null;
    if (isDashboard) {
        await loadDashboard();
    }
});

// ============================================================================
// DATA LOADING
// ============================================================================

async function loadDashboard() {
    try {
        // Fire all requests in parallel
        const [pricesRes, instantRes, historyRes, txStatsRes, exchangeRes, nftRes] = await Promise.allSettled([
            v2Fetch(`${API_BASE}/prices/all`),
            v2Fetch(`${API_BASE}/portfolio/instant`),
            v2Fetch(`${API_BASE}/balance-history/data?range=1w`),
            v2Fetch(`${API_BASE}/transactions/stats?days=7`),
            v2Fetch(`${API_BASE}/exchanges/all`),
            v2Fetch(`${API_BASE}/nfts/all/summary`),
        ]);

        // Process prices
        if (pricesRes.status === 'fulfilled' && pricesRes.value.ok) {
            const data = await pricesRes.value.json();
            v2State.prices = data.prices || data;
        }

        // Process portfolio instant
        if (instantRes.status === 'fulfilled' && instantRes.value.ok) {
            const data = await instantRes.value.json();
            renderPortfolioHero(data);
        }

        // Process chart
        if (historyRes.status === 'fulfilled' && historyRes.value.ok) {
            const data = await historyRes.value.json();
            v2State.chartData = data;
            renderChart(data);
        }

        // Process tx stats
        if (txStatsRes.status === 'fulfilled' && txStatsRes.value.ok) {
            const data = await txStatsRes.value.json();
            renderTxStats(data);
        }

        // Process exchanges
        let exchangeTotal = 0;
        if (exchangeRes.status === 'fulfilled' && exchangeRes.value.ok) {
            const data = await exchangeRes.value.json();
            if (data.exchanges) {
                data.exchanges.forEach(ex => {
                    exchangeTotal += (ex.total_usd || 0);
                });
            }
        }
        setText('statExchanges', formatCurrency(exchangeTotal));

        // Process NFTs
        let nftTotal = 0;
        if (nftRes.status === 'fulfilled' && nftRes.value.ok) {
            const data = await nftRes.value.json();
            if (data.total_value_usd !== undefined) {
                nftTotal = data.total_value_usd;
            } else if (data.chains) {
                Object.values(data.chains).forEach(c => { nftTotal += (c.total_value_usd || 0); });
            }
        }
        setText('statNfts', formatCurrency(nftTotal));

        // Load full holdings for the table (slightly delayed to prioritize above-fold)
        loadHoldings();

    } catch (err) {
        console.error('Dashboard load error:', err);
        showToast('Failed to load dashboard data', 'error');
    }
}

async function loadHoldings() {
    try {
        const response = await v2Fetch(`${API_BASE}/portfolio/all-holdings`);
        if (!response.ok) throw new Error('Failed to load holdings');

        const data = await response.json();
        v2State.holdings = data.holdings || [];
        v2State.totalPortfolioValue = data.total_value_usd || 0;
        renderAssetsTable();
    } catch (err) {
        console.error('Holdings load error:', err);
        // Fallback: try /portfolio/summary
        try {
            const resp = await v2Fetch(`${API_BASE}/portfolio/summary`);
            if (resp.ok) {
                const data = await resp.json();
                extractHoldingsFromSummary(data);
                renderAssetsTable();
            }
        } catch (e) {
            console.error('Fallback holdings also failed:', e);
        }
    }
}

function extractHoldingsFromSummary(data) {
    // Build holdings array from V1 portfolio/summary format
    // The summary has chain names as top-level keys (cardano, bitcoin, etc.)
    const holdings = [];
    const chainSymbols = {
        'cardano': { symbol: 'ADA', name: 'Cardano', balanceKey: 'total_ada' },
        'bitcoin': { symbol: 'BTC', name: 'Bitcoin', balanceKey: 'total_btc' },
        'ethereum': { symbol: 'ETH', name: 'Ethereum', balanceKey: 'total_eth' },
        'solana': { symbol: 'SOL', name: 'Solana', balanceKey: 'total_sol' },
        'polygon': { symbol: 'MATIC', name: 'Polygon', balanceKey: 'total_matic' },
        'base': { symbol: 'ETH', name: 'Base (ETH)', balanceKey: 'total_eth' },
        'algorand': { symbol: 'ALGO', name: 'Algorand', balanceKey: 'total_algo' },
        'bsc': { symbol: 'BNB', name: 'BNB Chain', balanceKey: 'total_bnb' },
        'arbitrum': { symbol: 'ETH', name: 'Arbitrum (ETH)', balanceKey: 'total_eth' },
        'avalanche': { symbol: 'AVAX', name: 'Avalanche', balanceKey: 'total_avax' },
    };

    Object.entries(chainSymbols).forEach(([chain, info]) => {
        const chainData = data[chain];
        if (!chainData) return;
        const balance = chainData[info.balanceKey] || 0;
        if (balance <= 0) return;

        const priceInfo = v2State.prices[info.symbol] || {};
        const price = typeof priceInfo === 'object' ? (priceInfo.usd || 0) : (priceInfo || 0);
        const value = balance * price;
        holdings.push({
            symbol: info.symbol,
            name: info.name,
            blockchain: chain,
            amount: balance,
            price_usd: price,
            value_usd: value,
            price_change_24h: typeof priceInfo === 'object' ? (priceInfo.usd_24h_change || 0) : 0,
            logo_url: null,
        });
    });

    // Sum totals
    let totalValue = holdings.reduce((sum, h) => sum + (h.value_usd || 0), 0);
    v2State.holdings = holdings;
    v2State.totalPortfolioValue = totalValue || data.total_value_usd || 0;
}


// ============================================================================
// RENDERING — HERO
// ============================================================================

function renderPortfolioHero(data) {
    const total = data.total_usd || data.total_value_usd || data.total_portfolio_value || 0;

    // Breakdown from /portfolio/instant: {chain, exchange, tracked_token, custom_token, staking, defi, nft}
    const bd = data.breakdown || {};
    const liquid = (bd.chain || 0) + (bd.exchange || 0) + (bd.tracked_token || 0) + (bd.custom_token || 0);
    const staked = (bd.staking || 0) + (bd.defi || 0);

    // Remove skeleton, show value
    const heroEl = document.getElementById('heroValue');
    setSafeHTML(heroEl, '');
    heroEl.textContent = formatCurrency(total);
    heroEl.classList.add('v2-blur');

    // Stats
    setText('statLiquid', formatCurrency(liquid));
    setText('statStaked', formatCurrency(staked));

    // Change data
    if (data.change_7d_usd !== undefined || data.change_7d_pct !== undefined) {
        const changeEl = document.getElementById('heroChange');
        const changeVal = data.change_7d_usd || 0;
        const changePct = data.change_7d_pct || 0;
        const isPositive = changeVal >= 0;
        changeEl.className = `v2-hero-change ${isPositive ? 'positive' : 'negative'}`;
        setSafeHTML(changeEl, `<span class="change-arrow">${isPositive ? '&#9650;' : '&#9660;'}</span> ${formatCurrency(Math.abs(changeVal))} (${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%)`);
    }

    // Last updated
    setText('heroLastUpdated', `Last updated: ${new Date().toLocaleTimeString()}`);

    // 7d change stat
    if (data.change_7d_usd !== undefined) {
        const statEl = document.getElementById('stat7dChange');
        statEl.textContent = formatCurrency(Math.abs(data.change_7d_usd || 0));
        const pctEl = document.getElementById('stat7dPct');
        const pct = data.change_7d_pct || 0;
        pctEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
        pctEl.className = `v2-stat-sub ${pct >= 0 ? 'positive' : 'negative'}`;
    }
}


// ============================================================================
// RENDERING — CHART
// ============================================================================

function renderChart(data) {
    // Hide skeleton
    const skeleton = document.getElementById('chartSkeleton');
    if (skeleton) skeleton.style.display = 'none';

    const canvas = document.getElementById('portfolioChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Parse data
    let labels = [];
    let values = [];

    if (data.data && Array.isArray(data.data)) {
        data.data.forEach(point => {
            labels.push(point.date || point.timestamp || '');
            values.push(point.total_usd || point.value || point.total || 0);
        });
    } else if (data.history && Array.isArray(data.history)) {
        data.history.forEach(point => {
            labels.push(point.date || point.timestamp || '');
            values.push(point.total_usd || point.value || 0);
        });
    } else if (Array.isArray(data)) {
        data.forEach(point => {
            labels.push(point.date || point.timestamp || '');
            values.push(point.total_usd || point.value || 0);
        });
    }

    if (labels.length === 0) {
        const container = document.getElementById('chartContainer');
        setSafeHTML(container, `
            <div class="v2-empty">
                <div class="v2-empty-icon">&#128200;</div>
                <div class="v2-empty-title">No Chart Data</div>
                <div class="v2-empty-desc">Start collecting historical balance data from the Settings page to see your portfolio chart.</div>
            </div>
        `);
        return;
    }

    // Format labels
    const formattedLabels = labels.map(l => {
        try {
            const d = new Date(l);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } catch { return l; }
    });

    // Determine line color from CSS var
    const style = getComputedStyle(document.documentElement);
    const lineColor = style.getPropertyValue('--v2-chart-line').trim() || '#00d26a';
    const fillColor = style.getPropertyValue('--v2-chart-fill').trim() || 'rgba(0, 210, 106, 0.08)';
    const gridColor = style.getPropertyValue('--v2-chart-grid').trim() || 'rgba(255,255,255,0.04)';
    const textColor = style.getPropertyValue('--v2-chart-text').trim() || '#5a6475';

    // Destroy previous chart
    if (v2State.chartInstance) {
        v2State.chartInstance.destroy();
    }

    v2State.chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: formattedLabels,
            datasets: [{
                data: values,
                borderColor: lineColor,
                backgroundColor: fillColor,
                fill: true,
                tension: 0.35,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: lineColor,
                pointHoverBorderColor: '#fff',
                pointHoverBorderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    titleFont: { size: 12 },
                    bodyFont: { size: 13, weight: '600' },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: (context) => formatCurrency(context.parsed.y),
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: gridColor, drawBorder: false },
                    ticks: { color: textColor, font: { size: 11 }, maxTicksLimit: 8 },
                    border: { display: false },
                },
                y: {
                    grid: { color: gridColor, drawBorder: false },
                    ticks: {
                        color: textColor,
                        font: { size: 11 },
                        callback: (val) => formatCompact(val),
                    },
                    border: { display: false },
                    beginAtZero: false,
                }
            },
            elements: {
                line: { capBezierPoints: true }
            }
        }
    });
}

async function loadChart(range) {
    v2State.currentChartRange = range;

    // Update active button
    document.querySelectorAll('.v2-range-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.range === range);
    });

    // Show skeleton
    const skeleton = document.getElementById('chartSkeleton');
    if (skeleton) skeleton.style.display = 'block';

    try {
        const response = await v2Fetch(`${API_BASE}/balance-history/data?range=${range}`);
        if (response.ok) {
            const data = await response.json();
            v2State.chartData = data;
            renderChart(data);
        }
    } catch (err) {
        console.error('Chart load error:', err);
    }
}


// ============================================================================
// RENDERING — TX STATS
// ============================================================================

function renderTxStats(data) {
    const count = data.total_transactions || data.total_count || data.count || 0;
    setText('statTx7d', count.toLocaleString());
}


// ============================================================================
// RENDERING — ASSETS TABLE
// ============================================================================

function renderAssetsTable() {
    const tbody = document.getElementById('assetsTableBody');
    if (!tbody) return;

    let holdings = [...v2State.holdings];

    // Filter zero balances
    if (!v2State.showZero) {
        holdings = holdings.filter(h => (h.value_usd || 0) > 0.01);
    }

    // Filter by text
    if (v2State.filterText) {
        const q = v2State.filterText.toLowerCase();
        holdings = holdings.filter(h =>
            (h.name || '').toLowerCase().includes(q) ||
            (h.symbol || '').toLowerCase().includes(q) ||
            (h.blockchain || '').toLowerCase().includes(q)
        );
    }

    // Sort
    holdings.sort((a, b) => {
        let va, vb;
        switch (v2State.sortCol) {
            case 'name':
                va = (a.name || a.symbol || '').toLowerCase();
                vb = (b.name || b.symbol || '').toLowerCase();
                return v2State.sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            case 'price':
                va = a.price_usd || 0;
                vb = b.price_usd || 0;
                break;
            case 'holdings':
                va = a.amount || 0;
                vb = b.amount || 0;
                break;
            case 'value':
                va = a.value_usd || 0;
                vb = b.value_usd || 0;
                break;
            case 'change':
                va = a.price_change_24h || a.change_24h || 0;
                vb = b.price_change_24h || b.change_24h || 0;
                break;
            case 'allocation':
                va = v2State.totalPortfolioValue > 0 ? (a.value_usd || 0) / v2State.totalPortfolioValue : 0;
                vb = v2State.totalPortfolioValue > 0 ? (b.value_usd || 0) / v2State.totalPortfolioValue : 0;
                break;
            default:
                va = a.value_usd || 0;
                vb = b.value_usd || 0;
        }
        if (typeof va === 'string') return 0;
        return v2State.sortDir === 'asc' ? va - vb : vb - va;
    });

    if (holdings.length === 0) {
        setSafeHTML(tbody, `
            <tr>
                <td colspan="7">
                    <div class="v2-empty" style="padding:32px;">
                        <div class="v2-empty-title">No assets found</div>
                        <div class="v2-empty-desc">Add wallets or exchange connections to see your portfolio here.</div>
                    </div>
                </td>
            </tr>
        `);
        return;
    }

    let html = '';
    holdings.forEach((h, idx) => {
        const value = h.value_usd || 0;
        const price = h.price_usd || 0;
        const amount = h.amount || 0;
        const change = h.price_change_24h || h.change_24h || 0;
        const alloc = v2State.totalPortfolioValue > 0 ? (value / v2State.totalPortfolioValue * 100) : 0;
        const changeClass = change >= 0 ? 'v2-value-positive' : 'v2-value-negative';
        const symbol = h.symbol || '???';
        const name = h.name || symbol;
        const chain = h.blockchain || '';

        // Logo
        let logoHtml = '';
        if (h.logo_url) {
            logoHtml = `<img src="${escapeAttr(h.logo_url)}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span class="fallback" style="display:none">${escapeHtml(symbol.substring(0, 3))}</span>`;
        } else {
            logoHtml = `<span class="fallback">${escapeHtml(symbol.substring(0, 3))}</span>`;
        }

        html += `
            <tr data-symbol="${escapeAttr(symbol)}" data-chain="${escapeAttr(chain)}" style="cursor:pointer">
                <td>
                    <div class="v2-asset-name">
                        <div class="v2-asset-icon">${logoHtml}</div>
                        <div class="v2-asset-info">
                            <div class="name">${escapeHtml(name)}</div>
                            <div class="ticker">${escapeHtml(symbol)}${chain ? ' <span class="v2-chain-badge">' + escapeHtml(chain) + '</span>' : ''}</div>
                        </div>
                    </div>
                </td>
                <td class="right">${formatPrice(price)}</td>
                <td class="right"><div class="v2-sparkline" id="spark_${idx}"><canvas></canvas></div></td>
                <td class="right">
                    <div class="v2-amount v2-blur">${formatAmount(amount)}</div>
                    <div class="v2-amount-sub">${escapeHtml(symbol)}</div>
                </td>
                <td class="right"><span class="v2-amount v2-blur">${formatCurrency(value)}</span></td>
                <td class="right"><span class="${changeClass}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</span></td>
                <td class="right">${alloc.toFixed(1)}%</td>
            </tr>
        `;
    });

    setSafeHTML(tbody, html);

    // Attach click handlers after rendering (DOMPurify strips onclick on <tr> elements)
    tbody.querySelectorAll('tr[data-symbol]').forEach(row => {
        row.addEventListener('click', () => {
            openAssetDetail(row.dataset.symbol, row.dataset.chain || '');
        });
    });

    // Render sparklines after table is in DOM
    requestAnimationFrame(() => {
        holdings.forEach((h, idx) => {
            renderSparkline(idx, h.price_change_24h || h.change_24h || 0);
        });
    });
}

function renderSparkline(idx, change) {
    const container = document.getElementById(`spark_${idx}`);
    if (!container) return;
    const canvas = container.querySelector('canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    canvas.width = 80;
    canvas.height = 32;

    // Generate pseudo-sparkline from change direction
    const points = 20;
    const data = [];
    let y = 16;
    for (let i = 0; i < points; i++) {
        y += (Math.random() - 0.45 + (change > 0 ? 0.1 : -0.1)) * 3;
        y = Math.max(4, Math.min(28, y));
        data.push(y);
    }
    // Ensure end reflects direction
    if (change > 0) data[points - 1] = Math.min(8, data[points - 1]);
    else if (change < 0) data[points - 1] = Math.max(24, data[points - 1]);

    const style = getComputedStyle(document.documentElement);
    const color = change >= 0
        ? (style.getPropertyValue('--v2-accent').trim() || '#00d26a')
        : (style.getPropertyValue('--v2-red').trim() || '#ff5252');

    ctx.clearRect(0, 0, 80, 32);
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';

    const step = 80 / (points - 1);
    data.forEach((val, i) => {
        if (i === 0) ctx.moveTo(0, val);
        else ctx.lineTo(i * step, val);
    });
    ctx.stroke();
}


// ============================================================================
// SORTING
// ============================================================================

function sortAssets(col) {
    if (v2State.sortCol === col) {
        v2State.sortDir = v2State.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        v2State.sortCol = col;
        v2State.sortDir = 'desc';
    }

    // Update header UI
    document.querySelectorAll('.v2-table th').forEach(th => {
        th.classList.toggle('sorted', th.dataset.col === col);
        const icon = th.querySelector('.sort-icon');
        if (icon && th.dataset.col === col) {
            setSafeHTML(icon, v2State.sortDir === 'asc' ? '&#9650;' : '&#9660;');
        }
    });

    renderAssetsTable();
}

function filterAssets() {
    v2State.filterText = document.getElementById('assetFilter').value;
    renderAssetsTable();
}

function toggleZeroBalances() {
    v2State.showZero = document.getElementById('showZeroToggle').checked;
    renderAssetsTable();
}


// ============================================================================
// ASSET DETAIL MODAL
// ============================================================================

async function openAssetDetail(symbol, blockchain) {
    const overlay = document.getElementById('assetModalOverlay');
    const modal = document.getElementById('assetModal');
    const title = document.getElementById('assetModalTitle');
    const body = document.getElementById('assetModalBody');

    title.textContent = symbol;
    setSafeHTML(body, '<div style="text-align:center;padding:40px;"><div class="v2-skeleton v2-skeleton-chart" style="height:200px;"></div></div>');

    overlay.classList.add('open');
    modal.classList.add('open');

    try {
        const response = await v2Fetch(`${API_BASE}/portfolio/asset-detail?symbol=${encodeURIComponent(symbol)}&blockchain=${encodeURIComponent(blockchain || '')}`);
        if (response.ok) {
            const data = await response.json();
            renderAssetModal(data, symbol, blockchain);
        } else {
            setSafeHTML(body, '<div class="v2-empty"><div class="v2-empty-title">Could not load asset details</div></div>');
        }
    } catch (err) {
        setSafeHTML(body, '<div class="v2-empty"><div class="v2-empty-title">Error loading details</div></div>');
    }
}

function renderAssetModal(data, symbol, blockchain) {
    const body = document.getElementById('assetModalBody');
    const title = document.getElementById('assetModalTitle');

    const name = data.name || symbol;
    title.textContent = `${name} (${symbol})`;

    const price = data.price_usd || data.price || 0;
    const change24h = data.change_24h_pct || data.change_24h || 0;
    const marketCap = data.market_cap || 0;
    const volume24h = data.volume_24h || 0;
    const holding = data.total_amount || data.amount || 0;
    const value = data.total_value_usd || data.value_usd || (holding * price);
    const changeClass = change24h >= 0 ? 'v2-value-positive' : 'v2-value-negative';

    setSafeHTML(body, `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">
            <div class="v2-stat-card">
                <div class="v2-stat-label">Price</div>
                <div class="v2-stat-value">${formatPrice(price)}</div>
                <div class="v2-stat-sub ${change24h >= 0 ? 'positive' : 'negative'}">${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}% (24h)</div>
            </div>
            <div class="v2-stat-card">
                <div class="v2-stat-label">Your Holdings</div>
                <div class="v2-stat-value v2-blur">${formatCurrency(value)}</div>
                <div class="v2-stat-sub">${formatAmount(holding)} ${symbol}</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;">
            <div class="v2-stat-card">
                <div class="v2-stat-label">Market Cap</div>
                <div class="v2-stat-value">${marketCap > 0 ? formatCompact(marketCap) : '--'}</div>
            </div>
            <div class="v2-stat-card">
                <div class="v2-stat-label">24h Volume</div>
                <div class="v2-stat-value">${volume24h > 0 ? formatCompact(volume24h) : '--'}</div>
            </div>
        </div>
        ${blockchain ? `<div style="font-size:12px;color:var(--v2-text-muted);margin-top:8px;">Chain: <span class="v2-chain-badge">${escapeHtml(blockchain)}</span></div>` : ''}
    `);
}

function closeAssetModal() {
    document.getElementById('assetModalOverlay').classList.remove('open');
    document.getElementById('assetModal').classList.remove('open');
}


// ============================================================================
// SIDEBAR
// ============================================================================

function toggleSidebar() {
    const sidebar = document.getElementById('v2Sidebar');
    const layout = document.getElementById('v2Layout');
    sidebar.classList.toggle('collapsed');
    layout.classList.toggle('sidebar-collapsed');
    v2State.sidebarCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('v2_sidebar_collapsed', v2State.sidebarCollapsed);

    // Redraw chart after sidebar animation
    setTimeout(() => {
        if (v2State.chartInstance) {
            v2State.chartInstance.resize();
        }
    }, 350);
}

function setActiveNav() {
    const path = window.location.pathname;
    document.querySelectorAll('.v2-nav-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href === path || (path === '/next' && href === '/next/') || (path === '/next/' && href === '/next/')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}


// ============================================================================
// THEME
// ============================================================================

function loadSavedTheme() {
    const theme = localStorage.getItem('theme') || 'dark-mode';
    document.documentElement.setAttribute('data-theme', theme);
    const select = document.getElementById('v2ThemeSelect');
    if (select) select.value = theme;
}

function changeTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    // Redraw chart with new colors
    if (v2State.chartData) {
        setTimeout(() => renderChart(v2State.chartData), 100);
    }

    // Re-render sparklines
    if (v2State.holdings.length > 0) {
        setTimeout(() => {
            v2State.holdings.forEach((h, idx) => {
                renderSparkline(idx, h.price_change_24h || h.change_24h || 0);
            });
        }, 150);
    }
}


// ============================================================================
// USER MENU
// ============================================================================

function toggleUserMenu() {
    const dropdown = document.getElementById('userDropdown');
    dropdown.classList.toggle('open');
}

// Close user menu on click outside
document.addEventListener('click', (e) => {
    const menu = document.querySelector('.v2-user-menu');
    const dropdown = document.getElementById('userDropdown');
    if (menu && dropdown && !menu.contains(e.target)) {
        dropdown.classList.remove('open');
    }
});


// ============================================================================
// PRIVACY MODE
// ============================================================================

function togglePrivacy() {
    v2State.privacyMode = !v2State.privacyMode;
    localStorage.setItem('v2_privacy', v2State.privacyMode);
    document.body.classList.toggle('privacy-mode', v2State.privacyMode);
    showToast(v2State.privacyMode ? 'Privacy mode enabled' : 'Privacy mode disabled', 'success');
}


// ============================================================================
// SYNC ALL
// ============================================================================

async function syncAll() {
    const btn = document.getElementById('syncAllBtn');
    btn.classList.add('syncing');
    btn.disabled = true;
    showToast('Syncing all data...', 'success');

    try {
        await Promise.allSettled([
            v2Fetch(`${API_BASE}/portfolio/summary?refresh=true`),
            v2Fetch(`${API_BASE}/exchanges/all?refresh=true`),
            v2Fetch(`${API_BASE}/defi/summary?refresh=true`),
        ]);

        // Reload dashboard
        await loadDashboard();
        showToast('Sync complete', 'success');
    } catch (err) {
        showToast('Sync failed', 'error');
    } finally {
        btn.classList.remove('syncing');
        btn.disabled = false;
    }
}


// ============================================================================
// SEARCH
// ============================================================================

async function handleSearch(event) {
    if (event.key !== 'Enter') return;
    const query = document.getElementById('globalSearch').value.trim();
    if (!query) return;

    try {
        const response = await v2Fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
        if (response.ok) {
            const data = await response.json();
            // TODO: Show search results dropdown
            console.log('Search results:', data);
        }
    } catch (err) {
        console.error('Search error:', err);
    }
}


// ============================================================================
// NAVIGATION HELPER
// ============================================================================

function navigateTo(page) {
    const routes = {
        'dashboard': '/next/',
        'assets': '/next/assets',
        'nfts': '/next/nfts',
        'defi': '/next/defi',
        'exchanges': '/next/exchanges',
        'analytics': '/next/analytics',
        'transactions': '/next/transactions',
        'pnl': '/next/pnl',
        'security': '/next/security',
        'wallets': '/next/wallets',
        'settings': '/next/settings',
        'help': '/next/help',
    };
    const url = routes[page] || '/next/';
    window.location.href = url;
}


// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `v2-toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}


// ============================================================================
// LOGOUT
// ============================================================================

function logout() {
    localStorage.removeItem('abct_token');
    window.location.href = '/login.html';
}


// ============================================================================
// FORMATTERS
// ============================================================================

function formatCurrency(value) {
    if (value === null || value === undefined || isNaN(value)) return '$0.00';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);
}

function formatPrice(value) {
    if (!value || value === 0) return '$0.00';
    if (value < 0.01) return '$' + value.toFixed(6);
    if (value < 1) return '$' + value.toFixed(4);
    return formatCurrency(value);
}

function formatAmount(value) {
    if (!value || value === 0) return '0';
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e4) return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (value >= 1) return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return value.toFixed(6);
}

function formatCompact(value) {
    if (!value) return '$0';
    if (value >= 1e12) return '$' + (value / 1e12).toFixed(1) + 'T';
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(1) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(1) + 'M';
    if (value >= 1e3) return '$' + (value / 1e3).toFixed(1) + 'K';
    return formatCurrency(value);
}


// ============================================================================
// SAFETY UTILITIES
// ============================================================================

function setSafeHTML(element, html) {
    if (!element) return;
    if (typeof DOMPurify !== 'undefined') {
        // All V2 HTML is developer-authored with user data escaped via escapeHtml/escapeAttr.
        // DOMPurify is belt-and-suspenders protection.
        const purifyConfig = {
            ADD_ATTR: ['onclick', 'onchange', 'onerror'],
            ADD_TAGS: ['canvas'],
        };

        // Table elements (<tr>, <td>, <th>) are invalid outside a <table> context.
        // DOMPurify parses HTML using the browser's parser, which strips orphaned
        // table elements in a <div>/<body> context. To preserve them, we wrap in a
        // <table> for sanitization, then extract the sanitized content.
        const tagName = element.tagName ? element.tagName.toLowerCase() : '';
        const isTableContext = ['tbody', 'thead', 'tfoot', 'table', 'tr'].includes(tagName);

        if (isTableContext && /<\s*t[rdh]/i.test(html)) {
            // Wrap in table context so the browser parser preserves <tr>/<td>/<th>
            const wrapper = tagName === 'tr' ? '<table><tbody><tr>' : '<table><tbody>';
            const wrapperEnd = tagName === 'tr' ? '</tr></tbody></table>' : '</tbody></table>';
            const wrapped = wrapper + html + wrapperEnd;
            const sanitized = DOMPurify.sanitize(wrapped, {
                ...purifyConfig,
                WHOLE_DOCUMENT: false,
                RETURN_DOM: true,
            });
            // Extract the content from the wrapper — get the matching inner element
            const inner = tagName === 'tr'
                ? sanitized.querySelector('tr')
                : sanitized.querySelector('tbody');
            if (inner) {
                element.innerHTML = inner.innerHTML;
            } else {
                // Fallback: set directly (content is developer-authored)
                element.innerHTML = html;
            }
        } else {
            element.innerHTML = DOMPurify.sanitize(html, purifyConfig);
        }
    } else {
        // DOMPurify not yet loaded — use innerHTML directly since all V2 HTML is developer-authored
        element.innerHTML = html;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    if (!text) return '';
    return text.replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
        // Remove any skeleton children
        const skeletons = el.querySelectorAll('.v2-skeleton');
        skeletons.forEach(s => s.remove());
    }
}
