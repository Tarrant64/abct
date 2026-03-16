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
        initCollectHistory();
    }

    // Initialize global search on all pages
    initGlobalSearch();
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
        renderPortfolioDonut();
        renderTopHoldings();
    } catch (err) {
        console.error('Holdings load error:', err);
        // Fallback: try /portfolio/summary
        try {
            const resp = await v2Fetch(`${API_BASE}/portfolio/summary`);
            if (resp.ok) {
                const data = await resp.json();
                extractHoldingsFromSummary(data);
                renderAssetsTable();
                renderPortfolioDonut();
                renderTopHoldings();
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
                            <div class="ticker">${escapeHtml(symbol)}${chain ? ' <span class="v2-chain-badge chain-' + escapeAttr(chain.toLowerCase()) + '">' + escapeHtml(chain) + '</span>' : ''}</div>
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

// Asset detail modal state
let _v2AssetChartInstance = null;
let _v2AssetTimeframe = '7D';
let _v2AssetCurrentSymbol = null;
let _v2AssetCurrentCgId = null;

async function openAssetDetail(symbol, blockchain) {
    const overlay = document.getElementById('assetModalOverlay');
    const modal = document.getElementById('assetModal');
    const title = document.getElementById('assetModalTitle');
    const body = document.getElementById('assetModalBody');

    _v2AssetCurrentSymbol = symbol;
    _v2AssetCurrentCgId = null;
    _v2AssetTimeframe = '7D';

    title.textContent = symbol;
    setSafeHTML(body, '<div style="text-align:center;padding:40px;"><div class="v2-skeleton v2-skeleton-chart" style="height:200px;"></div></div>');

    overlay.classList.add('open');
    modal.classList.add('open');

    // Find holding data from v2State for instant display
    const holding = v2State.holdings.find(h =>
        (h.symbol || '').toUpperCase() === symbol.toUpperCase() &&
        (!blockchain || (h.blockchain || '').toLowerCase() === blockchain.toLowerCase())
    );

    try {
        // Fetch asset detail and chart data in parallel
        const [detailResp, chartResp] = await Promise.allSettled([
            v2Fetch(`${API_BASE}/portfolio/asset-detail?symbol=${encodeURIComponent(symbol)}`),
            v2Fetch(`${API_BASE}/portfolio/charts/asset?symbol=${encodeURIComponent(symbol)}&timeframe=7D`),
        ]);

        let detailData = null;
        let chartData = null;

        if (detailResp.status === 'fulfilled' && detailResp.value.ok) {
            detailData = await detailResp.value.json();
            if (detailData.coingecko_id) _v2AssetCurrentCgId = detailData.coingecko_id;
        }
        if (chartResp.status === 'fulfilled' && chartResp.value.ok) {
            chartData = await chartResp.value.json();
            if (chartData.coingecko_id) _v2AssetCurrentCgId = chartData.coingecko_id;
        }

        renderAssetModal(detailData, chartData, symbol, blockchain, holding);
    } catch (err) {
        setSafeHTML(body, '<div class="v2-empty"><div class="v2-empty-title">Error loading details</div></div>');
    }
}

function renderAssetModal(data, chartData, symbol, blockchain, holding) {
    const body = document.getElementById('assetModalBody');
    const title = document.getElementById('assetModalTitle');

    const d = data || {};
    const name = d.name || symbol;
    const rank = d.market_cap_rank ? `#${d.market_cap_rank}` : '';
    title.textContent = `${name} (${symbol})${rank ? '  ' + rank : ''}`;

    const price = parseFloat(d.current_price) || parseFloat(d.price_usd) || 0;
    const change24h = parseFloat(d.price_change_24h) || 0;
    const change1h = parseFloat(d.price_change_1h) || 0;
    const change7d = parseFloat(d.price_change_7d) || 0;
    const change30d = parseFloat(d.price_change_30d) || 0;
    const marketCap = parseFloat(d.market_cap) || 0;
    const volume24h = parseFloat(d.total_volume) || 0;
    const high24h = parseFloat(d.high_24h) || 0;
    const low24h = parseFloat(d.low_24h) || 0;

    // Holdings from local state
    const holdAmt = holding ? parseFloat(holding.amount) || 0 : 0;
    const holdValue = holding ? parseFloat(holding.value_usd) || (holdAmt * price) : 0;

    // Supply
    const circSupply = parseFloat(d.circulating_supply) || 0;
    const totalSupply = parseFloat(d.total_supply) || 0;
    const maxSupply = parseFloat(d.max_supply) || 0;
    const supplyPct = (maxSupply || totalSupply) > 0 ? Math.min((circSupply / (maxSupply || totalSupply)) * 100, 100) : 0;

    // ATH/ATL
    const ath = parseFloat(d.ath) || 0;
    const athDate = d.ath_date ? new Date(d.ath_date).toLocaleDateString() : '';
    const athChangePct = parseFloat(d.ath_change_pct) || 0;
    const atl = parseFloat(d.atl) || 0;
    const atlDate = d.atl_date ? new Date(d.atl_date).toLocaleDateString() : '';
    const atlChangePct = parseFloat(d.atl_change_pct) || 0;

    // Description
    const description = d.description || '';

    // Image
    const imgHtml = d.image ? `<img src="${escapeAttr(d.image)}" alt="" style="width:48px;height:48px;border-radius:50%;margin-right:12px;" onerror="this.style.display='none'">` : '';

    function changePill(label, val) {
        const v = parseFloat(val) || 0;
        const cls = v > 0 ? 'v2-value-positive' : v < 0 ? 'v2-value-negative' : '';
        return `<div class="v2-change-pill ${cls}" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;background:${v > 0 ? 'rgba(0,210,106,0.12)' : v < 0 ? 'rgba(255,82,82,0.12)' : 'rgba(255,255,255,0.05)'};margin-right:6px;">
            <span style="font-size:10px;color:var(--v2-text-muted)">${escapeHtml(label)}</span>
            <span>${v > 0 ? '+' : ''}${v.toFixed(2)}%</span>
        </div>`;
    }

    let html = '';

    // Header row with image, price, and change pills
    html += `<div style="display:flex;align-items:center;margin-bottom:16px;">
        ${imgHtml}
        <div>
            <div style="font-size:24px;font-weight:700;color:var(--v2-text-heading)">${formatPrice(price)}</div>
            <div class="v2-stat-sub ${change24h >= 0 ? 'positive' : 'negative'}" style="font-size:13px">${change24h >= 0 ? '+' : ''}${change24h.toFixed(2)}% (24h)</div>
        </div>
    </div>`;

    // Price change pills
    html += `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:16px;">
        ${changePill('1h', change1h)}
        ${changePill('24h', change24h)}
        ${changePill('7d', change7d)}
        ${changePill('30d', change30d)}
    </div>`;

    // Chart with timeframe buttons
    html += `<div style="margin-bottom:16px;">
        <div style="display:flex;justify-content:flex-end;gap:4px;margin-bottom:8px;" id="assetChartTimeframes">
            <button class="v2-range-btn" data-tf="1D">1D</button>
            <button class="v2-range-btn active" data-tf="7D">7D</button>
            <button class="v2-range-btn" data-tf="1M">1M</button>
            <button class="v2-range-btn" data-tf="3M">3M</button>
            <button class="v2-range-btn" data-tf="1Y">1Y</button>
        </div>
        <div style="height:200px;position:relative;background:var(--v2-bg-card);border-radius:var(--v2-radius-md);overflow:hidden;">
            <canvas id="assetDetailChart"></canvas>
        </div>
    </div>`;

    // Holdings row
    if (holdAmt > 0) {
        html += `<div class="v2-stat-card" style="margin-bottom:16px;">
            <div class="v2-stat-label">Your Holdings</div>
            <div style="display:flex;justify-content:space-between;align-items:baseline;">
                <div class="v2-stat-value v2-blur" style="font-size:18px">${formatCurrency(holdValue)}</div>
                <div class="v2-stat-sub v2-blur">${formatAmount(holdAmt)} ${escapeHtml(symbol)}</div>
            </div>
        </div>`;
    }

    // Market data grid
    html += `<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
        <div class="v2-stat-card" style="padding:10px;">
            <div class="v2-stat-label" style="font-size:10px;">Market Cap</div>
            <div style="font-size:13px;font-weight:600;color:var(--v2-text-heading)">${marketCap > 0 ? formatCompact(marketCap) : '--'}</div>
        </div>
        <div class="v2-stat-card" style="padding:10px;">
            <div class="v2-stat-label" style="font-size:10px;">24h Volume</div>
            <div style="font-size:13px;font-weight:600;color:var(--v2-text-heading)">${volume24h > 0 ? formatCompact(volume24h) : '--'}</div>
        </div>
        <div class="v2-stat-card" style="padding:10px;">
            <div class="v2-stat-label" style="font-size:10px;">24h High</div>
            <div style="font-size:13px;font-weight:600;color:var(--v2-text-heading)">${high24h > 0 ? formatPrice(high24h) : '--'}</div>
        </div>
        <div class="v2-stat-card" style="padding:10px;">
            <div class="v2-stat-label" style="font-size:10px;">24h Low</div>
            <div style="font-size:13px;font-weight:600;color:var(--v2-text-heading)">${low24h > 0 ? formatPrice(low24h) : '--'}</div>
        </div>
    </div>`;

    // Supply bar
    if (circSupply > 0 || totalSupply > 0) {
        html += `<div class="v2-stat-card" style="padding:12px;margin-bottom:16px;">
            <div class="v2-stat-label" style="margin-bottom:8px;">Supply</div>
            <div style="height:8px;background:var(--v2-bg-input);border-radius:4px;overflow:hidden;margin-bottom:8px;">
                <div style="height:100%;width:${supplyPct.toFixed(1)}%;background:var(--v2-accent);border-radius:4px;transition:width 0.3s;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--v2-text-muted);">
                <span>Circulating: ${formatCompact(circSupply).replace('$', '')}</span>
                <span>${(maxSupply || totalSupply) > 0 ? 'Max: ' + formatCompact(maxSupply || totalSupply).replace('$', '') : 'Max: unlimited'}</span>
            </div>
        </div>`;
    }

    // ATH / ATL
    if (ath > 0 || atl > 0) {
        html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">`;
        if (ath > 0) {
            html += `<div class="v2-stat-card" style="padding:10px;">
                <div class="v2-stat-label" style="font-size:10px;">All-Time High</div>
                <div style="font-size:14px;font-weight:700;color:var(--v2-text-heading)">${formatPrice(ath)}</div>
                <div style="font-size:11px;color:var(--v2-text-muted)">${athDate}</div>
                <div class="v2-value-negative" style="font-size:11px;font-weight:600;">${athChangePct.toFixed(1)}% from ATH</div>
            </div>`;
        }
        if (atl > 0) {
            html += `<div class="v2-stat-card" style="padding:10px;">
                <div class="v2-stat-label" style="font-size:10px;">All-Time Low</div>
                <div style="font-size:14px;font-weight:700;color:var(--v2-text-heading)">${formatPrice(atl)}</div>
                <div style="font-size:11px;color:var(--v2-text-muted)">${atlDate}</div>
                <div class="v2-value-positive" style="font-size:11px;font-weight:600;">+${atlChangePct.toFixed(1)}% from ATL</div>
            </div>`;
        }
        html += `</div>`;
    }

    // Chain badge
    if (blockchain) {
        html += `<div style="font-size:12px;color:var(--v2-text-muted);margin-bottom:12px;">Chain: <span class="v2-chain-badge chain-${escapeAttr(blockchain.toLowerCase())}">${escapeHtml(blockchain)}</span></div>`;
    }

    // Description
    if (description) {
        html += `<div class="v2-stat-card" style="padding:12px;">
            <div class="v2-stat-label" style="margin-bottom:6px;">About</div>
            <div style="font-size:12px;line-height:1.6;color:var(--v2-text-secondary);max-height:80px;overflow:hidden;">${escapeHtml(description)}</div>
        </div>`;
    }

    setSafeHTML(body, html);

    // Attach timeframe button handlers
    const tfContainer = document.getElementById('assetChartTimeframes');
    if (tfContainer) {
        tfContainer.querySelectorAll('.v2-range-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                _v2AssetTimeframe = btn.dataset.tf;
                tfContainer.querySelectorAll('.v2-range-btn').forEach(b => b.classList.toggle('active', b.dataset.tf === _v2AssetTimeframe));
                loadAssetModalChart(symbol, _v2AssetTimeframe);
            });
        });
    }

    // Render chart
    if (chartData && chartData.data && chartData.data.length > 0) {
        renderAssetModalChart(chartData.data);
    } else {
        // Try rendering with empty state
        const canvas = document.getElementById('assetDetailChart');
        if (canvas) {
            const parent = canvas.parentElement;
            setSafeHTML(parent, '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--v2-text-muted);font-size:12px;">No chart data available</div>');
        }
    }
}

function renderAssetModalChart(dataPoints) {
    const canvas = document.getElementById('assetDetailChart');
    if (!canvas || typeof Chart === 'undefined') return;

    // Destroy previous instance
    if (_v2AssetChartInstance) {
        _v2AssetChartInstance.destroy();
        _v2AssetChartInstance = null;
    }

    const labels = dataPoints.map(p => {
        try {
            // TradingView format: {time: unix_seconds, value: price}
            const ts = p.time || p.date || p.timestamp;
            const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } catch { return ''; }
    });
    const values = dataPoints.map(p => parseFloat(p.value) || parseFloat(p.price) || 0);

    const style = getComputedStyle(document.documentElement);
    const lineColor = style.getPropertyValue('--v2-chart-line').trim() || '#00d26a';
    const fillColor = style.getPropertyValue('--v2-chart-fill').trim() || 'rgba(0, 210, 106, 0.08)';
    const gridColor = style.getPropertyValue('--v2-chart-grid').trim() || 'rgba(255,255,255,0.04)';
    const textColor = style.getPropertyValue('--v2-chart-text').trim() || '#5a6475';

    const ctx = canvas.getContext('2d');
    _v2AssetChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: values,
                borderColor: lineColor,
                backgroundColor: fillColor,
                fill: true,
                tension: 0.35,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: lineColor,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.85)',
                    bodyFont: { size: 13, weight: '600' },
                    padding: 10,
                    cornerRadius: 6,
                    displayColors: false,
                    callbacks: { label: (ctx) => formatPrice(ctx.parsed.y) }
                }
            },
            scales: {
                x: { grid: { color: gridColor, drawBorder: false }, ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 6 }, border: { display: false } },
                y: { grid: { color: gridColor, drawBorder: false }, ticks: { color: textColor, font: { size: 10 }, callback: (val) => formatCompact(val) }, border: { display: false }, beginAtZero: false }
            }
        }
    });
}

async function loadAssetModalChart(symbol, timeframe) {
    const canvas = document.getElementById('assetDetailChart');
    if (!canvas) return;

    const params = new URLSearchParams({ symbol, timeframe });
    if (_v2AssetCurrentCgId) params.set('coingecko_id', _v2AssetCurrentCgId);

    try {
        const response = await v2Fetch(`${API_BASE}/portfolio/charts/asset?${params}`);
        if (response.ok) {
            const data = await response.json();
            if (data.data && data.data.length > 0) {
                renderAssetModalChart(data.data);
            }
        }
    } catch (e) {
        console.warn('[AssetDetail] Chart data fetch failed:', e);
    }
}

function closeAssetModal() {
    document.getElementById('assetModalOverlay').classList.remove('open');
    document.getElementById('assetModal').classList.remove('open');
    if (_v2AssetChartInstance) {
        _v2AssetChartInstance.destroy();
        _v2AssetChartInstance = null;
    }
    _v2AssetCurrentSymbol = null;
    _v2AssetCurrentCgId = null;
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
// SEARCH — Global Search with Dropdown
// ============================================================================

let _searchDebounce = null;

function initGlobalSearch() {
    const input = document.getElementById('globalSearch');
    const resultsEl = document.getElementById('searchResults');
    if (!input || !resultsEl) return;

    input.addEventListener('input', () => {
        const q = input.value.trim();
        if (q.length < 2) {
            resultsEl.style.display = 'none';
            return;
        }
        clearTimeout(_searchDebounce);
        _searchDebounce = setTimeout(() => runGlobalSearch(q), 300);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            resultsEl.style.display = 'none';
            input.blur();
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.v2-search')) {
            resultsEl.style.display = 'none';
        }
    });

    // Cmd/Ctrl+K shortcut
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            input.focus();
        }
    });
}

async function runGlobalSearch(query) {
    const resultsEl = document.getElementById('searchResults');
    if (!resultsEl) return;

    resultsEl.style.display = 'block';
    setSafeHTML(resultsEl, '<div style="padding:16px;text-align:center;color:var(--v2-text-muted);font-size:12px;">Searching...</div>');

    // Search pages locally
    const pageIndex = [
        { name: 'Dashboard', url: '/next/', keywords: ['home', 'portfolio', 'overview'] },
        { name: 'Assets', url: '/next/assets', keywords: ['tokens', 'holdings', 'wallets'] },
        { name: 'NFTs', url: '/next/nfts', keywords: ['collectibles', 'nft'] },
        { name: 'DeFi & Staking', url: '/next/defi', keywords: ['defi', 'staking', 'governance'] },
        { name: 'Exchanges', url: '/next/exchanges', keywords: ['exchange', 'cex'] },
        { name: 'Analytics', url: '/next/analytics', keywords: ['charts', 'market', 'analysis'] },
        { name: 'Transactions', url: '/next/transactions', keywords: ['history', 'tx', 'transfer'] },
        { name: 'P&L', url: '/next/pnl', keywords: ['profit', 'loss', 'pnl'] },
        { name: 'Security', url: '/next/security', keywords: ['privacy', 'spam', 'approvals'] },
        { name: 'Wallets', url: '/next/wallets', keywords: ['wallet', 'address'] },
        { name: 'Settings', url: '/next/settings', keywords: ['config', 'api', 'keys'] },
    ];
    const q = query.toLowerCase();
    const pageResults = pageIndex.filter(p => p.name.toLowerCase().includes(q) || p.keywords.some(k => k.includes(q))).slice(0, 3);

    // Backend search
    let tokens = [], walletResults = [], defiResults = [], stakingResults = [], exchangeResults = [];
    try {
        const resp = await v2Fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
        if (resp.ok) {
            const data = await resp.json();
            tokens = data.tokens || [];
            walletResults = data.wallets || [];
            defiResults = data.defi || [];
            stakingResults = data.staking || [];
            exchangeResults = data.exchanges || [];
        }
    } catch (e) {
        console.warn('[Search] Backend error:', e);
    }

    let html = '';

    function resultItem(href, name, sub) {
        return `<a class="v2-search-result-item" data-href="${escapeAttr(href)}" style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;text-decoration:none;color:var(--v2-text-primary);border-bottom:1px solid var(--v2-border);cursor:pointer;transition:background 0.15s;">
            <div>
                <div style="font-size:13px;font-weight:500;">${escapeHtml(name)}</div>
                <div style="font-size:11px;color:var(--v2-text-muted)">${escapeHtml(sub)}</div>
            </div>
            <span style="font-size:16px;color:var(--v2-text-muted)">&rsaquo;</span>
        </a>`;
    }

    function categoryLabel(text) {
        return `<div style="padding:8px 14px;font-size:10px;font-weight:600;text-transform:uppercase;color:var(--v2-text-muted);letter-spacing:0.05em;">${escapeHtml(text)}</div>`;
    }

    if (tokens.length > 0) {
        html += categoryLabel('Tokens');
        tokens.forEach(t => {
            const val = parseFloat(t.total_value_usd) > 0 ? formatCurrency(t.total_value_usd) : '';
            const sub = (t.blockchain || '') + (val ? ' \u00b7 ' + val : '');
            html += resultItem('/next/assets', t.ticker || t.name || '', sub);
        });
    }

    if (defiResults.length > 0) {
        html += categoryLabel('DeFi / Governance');
        defiResults.forEach(d => {
            const sub = (d.protocol || '') + (d.type ? ' \u00b7 ' + d.type : '');
            html += resultItem('/next/defi', d.token || d.name || '', sub);
        });
    }

    if (stakingResults.length > 0) {
        html += categoryLabel('Staking');
        stakingResults.forEach(s => {
            html += resultItem('/next/defi', s.token || s.name || '', s.protocol || '');
        });
    }

    if (exchangeResults.length > 0) {
        html += categoryLabel('Exchanges');
        exchangeResults.forEach(ex => {
            const val = parseFloat(ex.usd_value) > 0 ? formatCurrency(ex.usd_value) : '';
            html += resultItem('/next/exchanges', ex.currency || '', (ex.exchange || '') + (val ? ' \u00b7 ' + val : ''));
        });
    }

    if (walletResults.length > 0) {
        html += categoryLabel('Wallets');
        walletResults.forEach(w => {
            const addr = (w.address || '').length > 20 ? w.address.slice(0, 10) + '...' + w.address.slice(-8) : w.address;
            html += resultItem('/next/wallets', w.label || addr, (w.blockchain || '') + ' \u00b7 ' + addr);
        });
    }

    if (pageResults.length > 0) {
        html += categoryLabel('Pages');
        pageResults.forEach(p => {
            html += resultItem(p.url, p.name, p.url);
        });
    }

    if (!html) {
        html = '<div style="padding:20px;text-align:center;color:var(--v2-text-muted);font-size:12px;">No results found</div>';
    }

    setSafeHTML(resultsEl, html);

    // Attach click handlers (DOMPurify strips onclick)
    resultsEl.querySelectorAll('.v2-search-result-item').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const href = el.getAttribute('data-href');
            resultsEl.style.display = 'none';
            if (href) window.location.href = href;
        });
        // Hover effect
        el.addEventListener('mouseenter', () => { el.style.background = 'var(--v2-bg-table-row-hover)'; });
        el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
    });
}


// ============================================================================
// PORTFOLIO DONUT CHART
// ============================================================================

let _portfolioDonutChart = null;
let _donutSelectedIndex = -1;

const CHAIN_COLORS = {
    cardano: '#0033ad', bitcoin: '#f7931a', ethereum: '#627eea', solana: '#9945ff',
    polygon: '#8247e5', base: '#0052ff', algorand: '#00d2c2', bsc: '#f3ba2f',
    arbitrum: '#28a0f0', avalanche: '#e84142', tron: '#ff0013', xrp: '#23292f',
    dogecoin: '#c2a633', litecoin: '#345d9d', cosmos: '#2e3148', near: '#00c08b',
    ton: '#0098EA', polkadot: '#E6007A', stellar: '#14B6E7', fantom: '#1969FF',
};

function renderPortfolioDonut() {
    const canvas = document.getElementById('portfolioDonut');
    if (!canvas || typeof Chart === 'undefined' || !v2State.holdings.length) return;

    // Aggregate by blockchain
    const chainTotals = {};
    v2State.holdings.forEach(h => {
        const chain = (h.blockchain || 'other').toLowerCase();
        const value = parseFloat(h.value_usd) || 0;
        if (value > 0) {
            chainTotals[chain] = (chainTotals[chain] || 0) + value;
        }
    });

    const entries = Object.entries(chainTotals).sort((a, b) => b[1] - a[1]);
    if (entries.length === 0) {
        const container = document.getElementById('donutContainer');
        if (container) setSafeHTML(container, '<div class="v2-empty" style="padding:32px"><div class="v2-empty-title">No allocation data</div></div>');
        return;
    }

    const labels = entries.map(([chain]) => chain.charAt(0).toUpperCase() + chain.slice(1));
    const data = entries.map(([_, v]) => v);
    const colors = entries.map(([chain]) => CHAIN_COLORS[chain] || '#666');
    const total = data.reduce((s, v) => s + v, 0);

    // Set default center text
    const displayTotal = v2State.totalPortfolioValue > 0 ? v2State.totalPortfolioValue : total;
    const centerLabel = document.getElementById('donutCenterLabel');
    const centerValue = document.getElementById('donutCenterValue');
    const centerSub = document.getElementById('donutCenterSub');
    if (centerLabel) centerLabel.textContent = 'Total';
    if (centerValue) centerValue.textContent = formatCurrency(displayTotal);
    if (centerSub) centerSub.textContent = '';

    if (_portfolioDonutChart) {
        // Update existing
        _portfolioDonutChart.data.labels = labels;
        _portfolioDonutChart.data.datasets[0].data = data;
        _portfolioDonutChart.data.datasets[0].backgroundColor = colors;
        _portfolioDonutChart.update('none');
        return;
    }

    _portfolioDonutChart = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data, backgroundColor: colors, borderWidth: 0, borderRadius: 2, spacing: 2 }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '68%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const val = ctx.raw || 0;
                            const pct = total > 0 ? ((val / displayTotal) * 100).toFixed(1) : '0';
                            return `${ctx.label}: ${formatCurrency(val)} (${pct}%)`;
                        },
                        title: () => ''
                    },
                    backgroundColor: 'rgba(0,0,0,0.85)',
                    bodyColor: '#fff',
                    bodyFont: { size: 12, weight: '600' },
                    padding: 10,
                    cornerRadius: 6,
                    displayColors: true,
                    boxWidth: 10,
                    boxHeight: 10,
                }
            },
            animation: { duration: 400, easing: 'easeOutQuart' },
            onClick: (evt, elements) => {
                if (!elements.length) {
                    _donutSelectedIndex = -1;
                    _resetDonutHighlight(entries, colors);
                    if (centerLabel) centerLabel.textContent = 'Total';
                    if (centerValue) centerValue.textContent = formatCurrency(displayTotal);
                    if (centerSub) centerSub.textContent = '';
                    return;
                }
                const idx = elements[0].index;
                if (_donutSelectedIndex === idx) {
                    _donutSelectedIndex = -1;
                    _resetDonutHighlight(entries, colors);
                    if (centerLabel) centerLabel.textContent = 'Total';
                    if (centerValue) centerValue.textContent = formatCurrency(displayTotal);
                    if (centerSub) centerSub.textContent = '';
                } else {
                    _donutSelectedIndex = idx;
                    _highlightDonutSegment(idx, entries, colors);
                    const [chain, val] = entries[idx];
                    const pct = displayTotal > 0 ? ((val / displayTotal) * 100).toFixed(1) + '%' : '';
                    if (centerLabel) centerLabel.textContent = chain.charAt(0).toUpperCase() + chain.slice(1);
                    if (centerValue) centerValue.textContent = formatCurrency(val);
                    if (centerSub) centerSub.textContent = pct;
                }
            },
            onHover: (evt, elements) => { canvas.style.cursor = elements.length ? 'pointer' : 'default'; }
        }
    });
}

function _highlightDonutSegment(activeIdx, entries, colors) {
    if (!_portfolioDonutChart) return;
    const ds = _portfolioDonutChart.data.datasets[0];
    ds.backgroundColor = colors.map((c, i) => i === activeIdx ? c : c + '40');
    ds.borderWidth = colors.map((_, i) => i === activeIdx ? 3 : 0);
    ds.borderColor = colors.map((_, i) => i === activeIdx ? '#ffffff' : 'transparent');
    _portfolioDonutChart.update('none');
}

function _resetDonutHighlight(entries, colors) {
    if (!_portfolioDonutChart) return;
    const ds = _portfolioDonutChart.data.datasets[0];
    ds.backgroundColor = colors;
    ds.borderWidth = 0;
    ds.borderColor = 'transparent';
    _portfolioDonutChart.update('none');
}


// ============================================================================
// TOP 3 HOLDINGS
// ============================================================================

function renderTopHoldings() {
    const container = document.getElementById('topHoldingsContainer');
    if (!container || !v2State.holdings.length) return;

    // Sort by value descending, take top 3
    const sorted = [...v2State.holdings]
        .filter(h => (parseFloat(h.value_usd) || 0) > 0)
        .sort((a, b) => (parseFloat(b.value_usd) || 0) - (parseFloat(a.value_usd) || 0))
        .slice(0, 5);

    if (!sorted.length) {
        setSafeHTML(container, '<div style="padding:20px;text-align:center;color:var(--v2-text-muted);font-size:12px;">No holdings data</div>');
        return;
    }

    const totalValue = v2State.totalPortfolioValue || sorted.reduce((s, h) => s + (parseFloat(h.value_usd) || 0), 0);

    let html = '';
    sorted.forEach((h, idx) => {
        const symbol = h.symbol || '???';
        const name = h.name || symbol;
        const value = parseFloat(h.value_usd) || 0;
        const amount = parseFloat(h.amount) || 0;
        const change = parseFloat(h.price_change_24h) || parseFloat(h.change_24h) || 0;
        const alloc = totalValue > 0 ? ((value / totalValue) * 100) : 0;
        const chain = (h.blockchain || '').toLowerCase();
        const changeClass = change >= 0 ? 'v2-value-positive' : 'v2-value-negative';
        const logoHtml = h.logo_url
            ? `<img src="${escapeAttr(h.logo_url)}" alt="" style="width:32px;height:32px;border-radius:50%;" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
            : '';
        const fallback = `<div style="width:32px;height:32px;border-radius:50%;background:var(--v2-bg-input);display:${h.logo_url ? 'none' : 'flex'};align-items:center;justify-content:center;font-size:12px;font-weight:600;color:var(--v2-text-muted);">${escapeHtml(symbol.substring(0, 3))}</div>`;

        html += `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;${idx < sorted.length - 1 ? 'border-bottom:1px solid var(--v2-border);' : ''}cursor:pointer;" data-symbol="${escapeAttr(symbol)}" data-chain="${escapeAttr(chain)}" class="top-holding-row">
            <div style="flex-shrink:0;">${logoHtml}${fallback}</div>
            <div style="flex:1;min-width:0;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div style="font-size:14px;font-weight:600;color:var(--v2-text-heading);">${escapeHtml(name)}</div>
                    <div class="v2-blur" style="font-size:14px;font-weight:600;color:var(--v2-text-heading);">${formatCurrency(value)}</div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
                    <div style="font-size:11px;color:var(--v2-text-muted);">
                        <span class="v2-blur">${formatAmount(amount)} ${escapeHtml(symbol)}</span>
                        ${chain ? ' <span class="v2-chain-badge chain-' + escapeAttr(chain) + '" style="font-size:9px;padding:1px 6px;">' + escapeHtml(chain) + '</span>' : ''}
                    </div>
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span class="${changeClass}" style="font-size:11px;font-weight:600;">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</span>
                        <span style="font-size:10px;color:var(--v2-text-muted);">${alloc.toFixed(1)}%</span>
                    </div>
                </div>
            </div>
        </div>`;
    });

    setSafeHTML(container, html);

    // Attach click handlers
    container.querySelectorAll('.top-holding-row').forEach(row => {
        row.addEventListener('click', () => {
            openAssetDetail(row.dataset.symbol, row.dataset.chain || '');
        });
    });
}


// ============================================================================
// BALANCE HISTORY COLLECTION
// ============================================================================

let _collectPolling = null;

function initCollectHistory() {
    const btn = document.getElementById('collectHistoryBtn');
    if (!btn) return;

    btn.addEventListener('click', startCollectHistory);

    // Check if there's an active collection
    checkCollectStatus();
}

async function startCollectHistory() {
    const btn = document.getElementById('collectHistoryBtn');
    const statusEl = document.getElementById('collectStatus');
    if (!btn) return;

    btn.disabled = true;
    btn.classList.add('syncing');
    if (statusEl) {
        statusEl.style.display = 'inline';
        statusEl.textContent = 'Starting collection...';
    }
    showToast('Starting balance history collection...', 'success');

    try {
        const resp = await v2Fetch(`${API_BASE}/balance-history/collect`, { method: 'POST' });
        if (resp.ok) {
            const data = await resp.json();
            if (data.status === 'started' || data.status === 'completed') {
                // Start polling for progress
                _collectPolling = setInterval(checkCollectStatus, 3000);
            }
        } else {
            showToast('Failed to start collection', 'error');
            btn.disabled = false;
            btn.classList.remove('syncing');
            if (statusEl) statusEl.style.display = 'none';
        }
    } catch (e) {
        showToast('Collection error', 'error');
        btn.disabled = false;
        btn.classList.remove('syncing');
        if (statusEl) statusEl.style.display = 'none';
    }
}

async function checkCollectStatus() {
    const btn = document.getElementById('collectHistoryBtn');
    const statusEl = document.getElementById('collectStatus');

    try {
        const resp = await v2Fetch(`${API_BASE}/balance-history/collect/status`);
        if (!resp.ok) return;
        const data = await resp.json();

        if (data.status === 'running' || data.status === 'planning') {
            if (btn) { btn.disabled = true; btn.classList.add('syncing'); }
            if (statusEl) {
                statusEl.style.display = 'inline';
                const pct = parseFloat(data.progress) || 0;
                statusEl.textContent = `${data.step || 'Processing...'} ${pct > 0 ? '(' + pct.toFixed(0) + '%)' : ''}`;
            }
            // Keep polling
            if (!_collectPolling) {
                _collectPolling = setInterval(checkCollectStatus, 3000);
            }
        } else {
            // Completed, failed, or idle
            if (_collectPolling) {
                clearInterval(_collectPolling);
                _collectPolling = null;
            }
            if (btn) { btn.disabled = false; btn.classList.remove('syncing'); }
            if (statusEl) {
                if (data.status === 'completed') {
                    statusEl.textContent = 'Collection complete!';
                    showToast('Balance history collection complete', 'success');
                    // Reload chart with fresh data
                    loadChart(v2State.currentChartRange);
                    setTimeout(() => { statusEl.style.display = 'none'; }, 5000);
                } else if (data.status === 'failed') {
                    statusEl.textContent = 'Collection failed';
                    showToast('Collection failed: ' + (data.error_message || 'Unknown error'), 'error');
                    setTimeout(() => { statusEl.style.display = 'none'; }, 5000);
                } else {
                    statusEl.style.display = 'none';
                }
            }
        }
    } catch (e) {
        // Silently ignore status check errors
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
    if (value === null || value === undefined) return '$0.00';
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num)) return '$0.00';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(num);
}

function formatPrice(value) {
    if (value === null || value === undefined) return '$0.00';
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num) || num === 0) return '$0.00';
    if (num < 0.01) return '$' + num.toFixed(6);
    if (num < 1) return '$' + num.toFixed(4);
    return formatCurrency(num);
}

function formatAmount(value) {
    // Ensure numeric — API may return strings, objects, or null
    if (value === null || value === undefined) return '0';
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num) || num === 0) return '0';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e4) return num.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (num >= 1) return num.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return num.toFixed(6);
}

function formatCompact(value) {
    if (value === null || value === undefined) return '$0';
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num) || num === 0) return '$0';
    if (num >= 1e12) return '$' + (num / 1e12).toFixed(1) + 'T';
    if (num >= 1e9) return '$' + (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return '$' + (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return '$' + (num / 1e3).toFixed(1) + 'K';
    return formatCurrency(num);
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
