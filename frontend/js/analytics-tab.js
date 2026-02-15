/**
 * Advanced Analytics Tab
 * Handles: chain metrics, market summary, relative strength, cross-asset comparison, TradFi
 */
(function() {
    'use strict';

    let _initialized = false;
    let _chainMetricsData = null;
    let _marketSummaryData = null;
    let _relativeStrengthChart = null;
    let _feeHistoryChart = null;
    let _selectedChainFilter = 'all';
    let _tradfiData = null;

    // Asset display colors (matches CHAIN_COLORS from transaction-analytics.js)
    const ASSET_COLORS = {
        'BTC': '#ffb74d',
        'ETH': '#8ba4f5',
        'SOL': '#3dffb3',
        'ADA': '#5c9eff',
        'POL': '#a673f0'
    };

    const ASSET_LABELS = {
        'BTC': 'Bitcoin',
        'ETH': 'Ethereum',
        'SOL': 'Solana',
        'ADA': 'Cardano',
        'POL': 'Polygon'
    };

    /**
     * Initialize analytics tab (called on first open, lazy-load)
     */
    window.initAnalyticsTab = function() {
        if (_initialized) return;
        _initialized = true;

        // Load all data in parallel
        loadMarketSummary();
        loadChainMetrics();
        loadRelativeStrength(30);
        loadTradFiSummary();
        loadGasTracker();
        loadTrendingCoins();
    };

    /**
     * Format large numbers: $4.2M, $50.3B, etc.
     */
    function formatLargeNumber(n, prefix) {
        prefix = prefix || '$';
        if (n === null || n === undefined || isNaN(n)) return '--';
        const abs = Math.abs(n);
        let formatted;
        if (abs >= 1e12) formatted = (n / 1e12).toFixed(2) + 'T';
        else if (abs >= 1e9) formatted = (n / 1e9).toFixed(2) + 'B';
        else if (abs >= 1e6) formatted = (n / 1e6).toFixed(2) + 'M';
        else if (abs >= 1e3) formatted = (n / 1e3).toFixed(1) + 'K';
        else formatted = n.toFixed(2);
        return prefix + formatted;
    }

    /**
     * Format percentage change with color indicator
     */
    function formatChange(pct) {
        if (pct === null || pct === undefined || isNaN(pct)) return '';
        const sign = pct >= 0 ? '+' : '';
        const cls = pct >= 0 ? 'positive' : 'negative';
        return `<span class="change-indicator ${cls}">${sign}${pct.toFixed(2)}%</span>`;
    }

    /**
     * Get theme-aware chart options
     */
    function getAnalyticsChartOptions() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
        const isDark = theme !== 'light';
        return {
            gridColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
            tickColor: isDark ? '#94a3b8' : '#6b7280',
            tooltipBg: isDark ? '#1e293b' : '#ffffff',
            tooltipBorder: isDark ? '#334155' : '#e5e7eb',
            textColor: isDark ? '#e0e0e0' : '#1a1a2e'
        };
    }

    // ---- Market Summary (Phase 2) ----

    async function loadMarketSummary() {
        try {
            const resp = await authFetch('/analytics/market-summary');
            const data = await resp.json();
            if (!data.success) return;

            _marketSummaryData = data;

            const mcEl = document.getElementById('summaryMarketCapValue');
            const mcChangeEl = document.getElementById('summaryMarketCapChange');
            const btcDomEl = document.getElementById('summaryBtcDominanceValue');
            const tvlEl = document.getElementById('summaryTotalTvlValue');
            const dexEl = document.getElementById('summaryDexVolumeValue');

            if (mcEl) mcEl.textContent = formatLargeNumber(data.total_market_cap_usd);
            if (mcChangeEl) mcChangeEl.innerHTML = formatChange(data.market_cap_change_24h);
            if (btcDomEl) btcDomEl.textContent = (data.btc_dominance || 0).toFixed(1) + '%';
            if (tvlEl) tvlEl.textContent = formatLargeNumber(data.total_defi_tvl);
            if (dexEl) dexEl.textContent = formatLargeNumber(data.total_dex_volume_24h);

            // Load cross-asset table with market data
            loadCrossAssetTable();
        } catch (e) {
            console.error('Failed to load market summary:', e);
        }
    }

    // ---- Chain Metrics (Phase 1) ----

    async function loadChainMetrics() {
        try {
            const resp = await authFetch('/analytics/chain-metrics');
            const data = await resp.json();
            if (!data.success) return;

            _chainMetricsData = data.chains;
            renderChainFinancialsTable(data.chains);
        } catch (e) {
            console.error('Failed to load chain metrics:', e);
            const body = document.getElementById('chainFinancialsBody');
            if (body) body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;padding:40px;">Failed to load chain metrics</td></tr>';
        }
    }

    function renderChainFinancialsTable(chains) {
        const body = document.getElementById('chainFinancialsBody');
        if (!body) return;

        const filtered = _selectedChainFilter === 'all'
            ? Object.entries(chains)
            : Object.entries(chains).filter(([name]) => name === _selectedChainFilter);

        if (filtered.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;padding:40px;">No data available</td></tr>';
            return;
        }

        // Sort by TVL descending
        filtered.sort((a, b) => (b[1].tvl || 0) - (a[1].tvl || 0));

        body.innerHTML = filtered.map(([name, m]) => {
            const tvlChange = m.tvl_change_1d || 0;
            const changeClass = tvlChange >= 0 ? 'positive' : 'negative';
            const changeSign = tvlChange >= 0 ? '+' : '';

            return `<tr>
                <td><strong>${name}</strong></td>
                <td class="privacy-sensitive">${formatLargeNumber(m.tvl)}</td>
                <td class="privacy-sensitive">${formatLargeNumber(m.fees_24h)}</td>
                <td class="privacy-sensitive">${formatLargeNumber(m.revenue_24h)}</td>
                <td class="privacy-sensitive">${formatLargeNumber(m.dex_volume_24h)}</td>
                <td><span class="change-indicator ${changeClass}">${changeSign}${tvlChange.toFixed(2)}%</span></td>
            </tr>`;
        }).join('');
    }

    /**
     * Filter chain financials table by chain
     */
    window.filterAnalyticsChain = function(chain) {
        _selectedChainFilter = chain;

        // Update active button
        document.querySelectorAll('.chain-filter-btn').forEach(btn => btn.classList.remove('active'));
        if (event && event.target) event.target.classList.add('active');

        if (_chainMetricsData) {
            renderChainFinancialsTable(_chainMetricsData);
        }

        // Show/hide fee history chart
        const feeSection = document.getElementById('feeHistorySection');
        if (chain !== 'all' && feeSection) {
            feeSection.style.display = 'block';
            const title = document.getElementById('feeHistoryTitle');
            if (title) title.textContent = `${chain} Fee History (30 days)`;
            loadFeeHistory(chain);
        } else if (feeSection) {
            feeSection.style.display = 'none';
        }
    };

    async function loadFeeHistory(chain) {
        try {
            const resp = await authFetch(`/analytics/chain-fees-history/${encodeURIComponent(chain)}?days=30`);
            const data = await resp.json();
            if (!data.success || !data.history || data.history.length === 0) return;

            renderFeeHistoryChart(data.history, chain);
        } catch (e) {
            console.error(`Failed to load fee history for ${chain}:`, e);
        }
    }

    function renderFeeHistoryChart(history, chain) {
        const canvas = document.getElementById('feeHistoryChart');
        if (!canvas) return;

        if (_feeHistoryChart) {
            _feeHistoryChart.destroy();
            _feeHistoryChart = null;
        }

        const opts = getAnalyticsChartOptions();
        const labels = history.map(h => {
            const d = new Date(h.date * 1000);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });
        const values = history.map(h => h.fees || 0);

        _feeHistoryChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily Fees ($)',
                    data: values,
                    backgroundColor: 'rgba(102, 126, 234, 0.6)',
                    borderColor: '#667eea',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        titleColor: opts.tickColor,
                        bodyColor: opts.tickColor,
                        callbacks: {
                            label: ctx => formatLargeNumber(ctx.parsed.y) + ' in fees'
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: { color: opts.tickColor, maxTicksLimit: 10 }
                    },
                    y: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: v => formatLargeNumber(v)
                        }
                    }
                }
            }
        });
    }

    // ---- Relative Strength (Phase 2) ----

    window.changeRelativeStrengthPeriod = function(days) {
        // Update active button
        const section = document.getElementById('relativeStrengthSection');
        if (section) {
            section.querySelectorAll('.period-btn').forEach(btn => btn.classList.remove('active'));
            if (event && event.target) event.target.classList.add('active');
        }
        loadRelativeStrength(days);
    };

    async function loadRelativeStrength(days) {
        const container = document.getElementById('relativeStrengthChartContainer');
        const loading = document.getElementById('relativeStrengthLoading');

        if (loading) loading.style.display = 'flex';
        if (container) container.style.display = 'none';

        try {
            const resp = await authFetch(`/analytics/relative-strength?days=${days}`);
            const data = await resp.json();

            if (loading) loading.style.display = 'none';

            if (!data.success || !data.assets || Object.keys(data.assets).length === 0) return;

            if (container) container.style.display = 'block';
            renderRelativeStrengthChart(data.assets);
        } catch (e) {
            console.error('Failed to load relative strength:', e);
            if (loading) loading.style.display = 'none';
        }
    }

    function renderRelativeStrengthChart(assets) {
        const canvas = document.getElementById('relativeStrengthChart');
        if (!canvas) return;

        if (_relativeStrengthChart) {
            _relativeStrengthChart.destroy();
            _relativeStrengthChart = null;
        }

        const opts = getAnalyticsChartOptions();
        const datasets = [];

        for (const [symbol, points] of Object.entries(assets)) {
            const color = ASSET_COLORS[symbol] || '#888';
            datasets.push({
                label: ASSET_LABELS[symbol] || symbol,
                data: points.map(p => p.change_pct),
                borderColor: color,
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.3
            });
        }

        // Use labels from the first asset
        const firstAsset = Object.values(assets)[0] || [];
        const labels = firstAsset.map(p => {
            const d = p.date || '';
            // Try to parse and abbreviate
            if (d.includes('-')) {
                const parts = d.split(' ')[0].split('-');
                return parts[1] + '/' + parts[2];
            }
            return d;
        });

        _relativeStrengthChart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { color: opts.tickColor, usePointStyle: true, pointStyle: 'circle' }
                    },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        titleColor: opts.tickColor,
                        bodyColor: opts.tickColor,
                        callbacks: {
                            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: { color: opts.tickColor, maxTicksLimit: 12, maxRotation: 45 }
                    },
                    y: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%'
                        }
                    }
                }
            }
        });
    }

    // ---- Cross-Asset Comparison Table (Phase 2) ----

    async function loadCrossAssetTable() {
        const body = document.getElementById('crossAssetTableBody');
        if (!body) return;

        try {
            // Fetch relative strength data for 7d and 30d changes
            const [rs7Resp, rs30Resp] = await Promise.all([
                authFetch('/analytics/relative-strength?days=7'),
                authFetch('/analytics/relative-strength?days=30')
            ]);
            const rs7 = await rs7Resp.json();
            const rs30 = await rs30Resp.json();

            const get7dChange = (symbol) => {
                const pts = (rs7.assets || {})[symbol] || [];
                return pts.length > 0 ? pts[pts.length - 1].change_pct : null;
            };
            const get30dChange = (symbol) => {
                const pts = (rs30.assets || {})[symbol] || [];
                return pts.length > 0 ? pts[pts.length - 1].change_pct : null;
            };

            // Get current prices from pricing API
            let prices = {};
            try {
                const priceResp = await authFetch('/prices');
                const priceData = await priceResp.json();
                if (priceData.prices) prices = priceData.prices;
            } catch (e) { /* pricing optional */ }

            // Build rows
            // Note: pricing API uses 'MATIC' key, relative strength uses 'POL'
            const symbols = ['BTC', 'ETH', 'SOL', 'ADA', 'POL'];
            const priceSymbolMap = {
                'BTC': 'BTC', 'ETH': 'ETH', 'SOL': 'SOL',
                'ADA': 'ADA', 'POL': 'MATIC'
            };
            const chainNameMap = {
                'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'SOL': 'Solana',
                'ADA': 'Cardano', 'POL': 'Polygon'
            };

            let rows = symbols.map(symbol => {
                const chainName = chainNameMap[symbol];
                const chainMetrics = (_chainMetricsData || {})[chainName] || {};
                const price = prices[priceSymbolMap[symbol] || symbol] || 0;
                const change7 = get7dChange(symbol);
                const change30 = get30dChange(symbol);

                return `<tr>
                    <td><strong>${chainName}</strong> (${symbol})</td>
                    <td class="privacy-sensitive">${price ? '$' + price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--'}</td>
                    <td>${change7 !== null ? formatChange(change7) : '--'}</td>
                    <td>${change30 !== null ? formatChange(change30) : '--'}</td>
                    <td class="privacy-sensitive">${chainMetrics.tvl ? formatLargeNumber(chainMetrics.tvl) : '--'}</td>
                    <td class="privacy-sensitive">${chainMetrics.fees_24h ? formatLargeNumber(chainMetrics.fees_24h) : '--'}</td>
                    <td class="privacy-sensitive">${chainMetrics.dex_volume_24h ? formatLargeNumber(chainMetrics.dex_volume_24h) : '--'}</td>
                </tr>`;
            });

            // Add TradFi rows if available
            if (_tradfiData && _tradfiData.indices) {
                const tradfiSymbols = ['SPY', 'QQQ', 'DIA', 'IBIT'];
                for (const sym of tradfiSymbols) {
                    const idx = _tradfiData.indices[sym];
                    if (!idx) continue;
                    rows.push(`<tr class="tradfi-row">
                        <td><strong>${idx.name || sym}</strong> (${sym})</td>
                        <td class="privacy-sensitive">${idx.price ? '$' + idx.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--'}</td>
                        <td>${idx.change_7d !== undefined ? formatChange(idx.change_7d) : '--'}</td>
                        <td>${idx.change_30d !== undefined ? formatChange(idx.change_30d) : '--'}</td>
                        <td>--</td>
                        <td>--</td>
                        <td>--</td>
                    </tr>`);
                }
            }

            body.innerHTML = rows.join('');
        } catch (e) {
            console.error('Failed to load cross-asset table:', e);
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">Failed to load comparison data</td></tr>';
        }
    }

    // ---- TradFi (Phase 3) ----

    async function loadTradFiSummary() {
        try {
            const resp = await authFetch('/analytics/tradfi/summary');
            const data = await resp.json();

            if (!data.success || !data.configured) {
                // Show notice to configure
                const notice = document.getElementById('tradfiNotConfigured');
                if (notice) notice.style.display = 'flex';
                return;
            }

            _tradfiData = data;

            // Show TradFi summary cards
            const spyData = (data.indices || {}).SPY;
            if (spyData) {
                const spyCard = document.getElementById('summarySpy');
                const spyValue = document.getElementById('summarySpyValue');
                const spyChange = document.getElementById('summarySpyChange');
                if (spyCard) spyCard.style.display = '';
                if (spyValue) spyValue.textContent = '$' + (spyData.price || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                if (spyChange) spyChange.innerHTML = formatChange(spyData.change_1d);
            }

            // Load BTC/SPY correlation
            try {
                const corrResp = await authFetch('/analytics/tradfi/correlation?days=30');
                const corrData = await corrResp.json();
                if (corrData.success && corrData.correlation !== undefined) {
                    const corrCard = document.getElementById('summaryCorrelation');
                    const corrValue = document.getElementById('summaryCorrelationValue');
                    if (corrCard) corrCard.style.display = '';
                    if (corrValue) corrValue.textContent = corrData.correlation.toFixed(3);
                }
            } catch (e) { /* correlation optional */ }

            // Re-render cross-asset table with TradFi data
            if (_chainMetricsData) {
                loadCrossAssetTable();
            }
        } catch (e) {
            console.error('Failed to load TradFi summary:', e);
        }
    }

    // ---- Gas Tracker (Phase 4) ----

    async function loadGasTracker() {
        const container = document.getElementById('gasTrackerCard');
        if (!container) return;

        try {
            const resp = await authFetch('/analytics/gas-prices?chain=ethereum');
            const data = await resp.json();

            if (!data.success) {
                container.style.display = 'none';
                return;
            }

            container.style.display = '';
            const safeEl = document.getElementById('gasSafe');
            const standardEl = document.getElementById('gasStandard');
            const fastEl = document.getElementById('gasFast');

            if (safeEl) safeEl.textContent = Math.round(data.safe_gas_price) + ' Gwei';
            if (standardEl) standardEl.textContent = Math.round(data.propose_gas_price) + ' Gwei';
            if (fastEl) fastEl.textContent = Math.round(data.fast_gas_price) + ' Gwei';
        } catch (e) {
            console.error('Failed to load gas tracker:', e);
            if (container) container.style.display = 'none';
        }
    }

    // ---- Trending Coins (Phase 4) ----

    async function loadTrendingCoins() {
        const container = document.getElementById('trendingCoinsCard');
        if (!container) return;

        try {
            const resp = await authFetch('/prices/trending');
            const data = await resp.json();

            if (!data.coins || data.coins.length === 0) {
                container.style.display = 'none';
                return;
            }

            container.style.display = '';
            const listEl = document.getElementById('trendingCoinsList');
            if (!listEl) return;

            listEl.innerHTML = data.coins.slice(0, 7).map((coin, i) => {
                const thumb = coin.thumb ? `<img src="${coin.thumb}" alt="" style="width:20px;height:20px;border-radius:50%;margin-right:8px;vertical-align:middle;">` : '';
                const price = coin.price_btc ? `${coin.price_btc.toFixed(8)} BTC` : '';
                return `<div class="trending-coin-item">
                    <span class="trending-rank">#${i + 1}</span>
                    ${thumb}
                    <span class="trending-name">${coin.name || ''}</span>
                    <span class="trending-symbol">${coin.symbol || ''}</span>
                    <span class="trending-price">${price}</span>
                </div>`;
            }).join('');
        } catch (e) {
            console.error('Failed to load trending coins:', e);
            if (container) container.style.display = 'none';
        }
    }
})();
