/**
 * Crypto Market Tab
 * Handles: stablecoin markets, chains by TVL, RWA protocols, global market overview.
 * Data sourced from DefiLlama (free, no key) + CoinGecko/CMC for global metrics.
 */
(function() {
    'use strict';

    let _initialized = false;
    let _stablecoinChart = null;
    let _chainsTvlChart = null;

    // ---- Formatting helpers (reuse global if available) ----

    function fmtCompactUSD(n) {
        if (typeof formatCompactUSD === 'function') return formatCompactUSD(n);
        if (n === null || n === undefined || isNaN(n)) return '--';
        const abs = Math.abs(n);
        if (abs >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
        if (abs >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
        if (abs >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
        if (abs >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K';
        return '$' + n.toFixed(2);
    }

    function fmtChange(pct) {
        if (pct === null || pct === undefined || isNaN(pct)) return '--';
        const sign = pct >= 0 ? '+' : '';
        const cls = pct >= 0 ? 'positive' : 'negative';
        return '<span class="change-indicator ' + cls + '">' + sign + pct.toFixed(2) + '%</span>';
    }

    function getChartOpts() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
        const isDark = theme !== 'light';
        return {
            gridColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
            tickColor: isDark ? '#94a3b8' : '#6b7280',
            tooltipBg: isDark ? '#1e293b' : '#ffffff',
            tooltipBorder: isDark ? '#334155' : '#e5e7eb',
        };
    }

    // ---- Lock / Unlock ----

    window.checkCryptoMarketLock = async function() {
        const btn = document.getElementById('cryptoMarketTabBtn');
        if (!btn) return;

        try {
            const resp = await authFetch('/settings/apis');
            const data = await resp.json();
            const apis = data.apis || data.api_keys || [];

            let hasGlobalSource = false;
            for (const api of apis) {
                const name = (api.name || api.service || '').toLowerCase();
                if ((name === 'coingecko' || name === 'coinmarketcap') && api.enabled !== false && api.key) {
                    hasGlobalSource = true;
                    break;
                }
            }

            if (!hasGlobalSource) {
                btn.classList.add('tab-locked');
                btn.setAttribute('data-locked', 'true');
                btn.title = 'Requires CoinGecko or CoinMarketCap API key';
            } else {
                btn.classList.remove('tab-locked');
                btn.removeAttribute('data-locked');
                btn.title = '';
            }
        } catch (e) {
            // If settings check fails, leave unlocked (DefiLlama data still works)
            console.debug('Crypto market lock check failed:', e);
        }
    };

    // ---- Init ----

    window.initCryptoMarketTab = function() {
        if (_initialized) return;
        _initialized = true;

        // Load all sections in parallel
        loadMarketOverview();
        loadStablecoinData();
        loadChainsTvl();
        loadRwaData();
    };

    // ---- Market Overview (reuses /analytics/market-summary) ----

    async function loadMarketOverview() {
        try {
            const resp = await authFetch('/analytics/market-summary');
            const data = await resp.json();

            const mcapEl = document.getElementById('cmTotalMarketCap');
            const mcapChangeEl = document.getElementById('cmMarketCapChange');
            const btcDomEl = document.getElementById('cmBtcDominance');
            const tvlEl = document.getElementById('cmTotalTvl');

            if (data.success) {
                if (mcapEl) mcapEl.textContent = fmtCompactUSD(data.total_market_cap_usd);
                if (mcapChangeEl) mcapChangeEl.innerHTML = fmtChange(data.market_cap_change_24h);
                if (btcDomEl) btcDomEl.textContent = (data.btc_dominance || 0).toFixed(1) + '%';
                if (tvlEl) tvlEl.textContent = fmtCompactUSD(data.total_defi_tvl);

                // Show API notice if no global market data
                if (!data.total_market_cap_usd && !data.btc_dominance) {
                    const notice = document.getElementById('marketApiNotice');
                    if (notice) notice.style.display = 'flex';
                }
            } else {
                // Show notice
                const notice = document.getElementById('marketApiNotice');
                if (notice) notice.style.display = 'flex';
            }
        } catch (e) {
            console.error('Failed to load crypto market overview:', e);
        }
    }

    // ---- Stablecoin Data ----

    async function loadStablecoinData() {
        try {
            const resp = await authFetch('/analytics/market/stablecoins');
            const data = await resp.json();

            if (!data.success) {
                document.getElementById('stablecoinTableBody').innerHTML =
                    '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">Failed to load stablecoin data</td></tr>';
                return;
            }

            // Update summary card
            const mcapEl = document.getElementById('cmStablecoinMcap');
            if (mcapEl) mcapEl.textContent = fmtCompactUSD(data.total_stablecoin_mcap);

            // Render chart (top 10)
            renderStablecoinChart(data.stablecoins.slice(0, 10));

            // Render table
            renderStablecoinTable(data.stablecoins);
        } catch (e) {
            console.error('Failed to load stablecoin data:', e);
        }
    }

    function renderStablecoinChart(stablecoins) {
        const container = document.getElementById('stablecoinChartContainer');
        const canvas = document.getElementById('stablecoinBarChart');
        if (!container || !canvas) return;

        if (_stablecoinChart) {
            _stablecoinChart.destroy();
            _stablecoinChart = null;
        }

        container.style.display = 'block';
        const opts = getChartOpts();

        const labels = stablecoins.map(s => s.symbol || s.name);
        const values = stablecoins.map(s => s.mcap);
        const colors = [
            '#26a17b', '#2775ca', '#f0b90b', '#00d395', '#6366f1',
            '#3b82f6', '#22d3ee', '#a78bfa', '#fb923c', '#94a3b8'
        ];

        _stablecoinChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Market Cap',
                    data: values,
                    backgroundColor: colors.slice(0, stablecoins.length),
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: {
                indexAxis: 'y',
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
                            label: function(ctx) { return fmtCompactUSD(ctx.parsed.x); }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: function(v) { return fmtCompactUSD(v); }
                        }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: opts.tickColor }
                    }
                }
            }
        });
    }

    function renderStablecoinTable(stablecoins) {
        const body = document.getElementById('stablecoinTableBody');
        if (!body) return;

        if (!stablecoins || stablecoins.length === 0) {
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">No stablecoin data available</td></tr>';
            return;
        }

        body.innerHTML = stablecoins.map(function(s, i) {
            var chainStr = (s.chains || []).slice(0, 5).join(', ');
            if ((s.chains || []).length > 5) chainStr += '...';
            var priceStr = s.price !== null && s.price !== undefined ? '$' + Number(s.price).toFixed(4) : '--';

            return '<tr>' +
                '<td>' + (i + 1) + '</td>' +
                '<td><strong>' + (s.name || '') + '</strong> (' + (s.symbol || '') + ')</td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(s.mcap) + '</td>' +
                '<td>' + fmtChange(s.mcap_change_7d) + '</td>' +
                '<td>' + priceStr + '</td>' +
                '<td>' + (s.peg_type || '--') + '</td>' +
                '<td style="font-size:12px;color:#888;">' + chainStr + '</td>' +
                '</tr>';
        }).join('');
    }

    // ---- Chains by TVL ----

    async function loadChainsTvl() {
        try {
            const resp = await authFetch('/analytics/market/chains-tvl?limit=25');
            const data = await resp.json();

            if (!data.success) {
                document.getElementById('chainsTvlTableBody').innerHTML =
                    '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">Failed to load chain TVL data</td></tr>';
                return;
            }

            // Render chart (top 15)
            renderChainsTvlChart(data.chains.slice(0, 15));

            // Render table
            renderChainsTvlTable(data.chains);
        } catch (e) {
            console.error('Failed to load chains TVL:', e);
        }
    }

    function renderChainsTvlChart(chains) {
        var container = document.getElementById('chainsTvlChartContainer');
        var canvas = document.getElementById('chainsTvlBarChart');
        if (!container || !canvas) return;

        if (_chainsTvlChart) {
            _chainsTvlChart.destroy();
            _chainsTvlChart = null;
        }

        container.style.display = 'block';
        var opts = getChartOpts();

        var labels = chains.map(function(c) { return c.name; });
        var values = chains.map(function(c) { return c.tvl; });

        // Generate gradient blues
        var colors = chains.map(function(_, i) {
            var hue = 210 + (i * 8);
            var sat = 70 - (i * 2);
            var light = 50 + (i * 1.5);
            return 'hsl(' + hue + ', ' + Math.max(sat, 40) + '%, ' + Math.min(light, 70) + '%)';
        });

        _chainsTvlChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'TVL',
                    data: values,
                    backgroundColor: colors,
                    borderRadius: 4,
                    barPercentage: 0.7
                }]
            },
            options: {
                indexAxis: 'y',
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
                            label: function(ctx) { return fmtCompactUSD(ctx.parsed.x); }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: function(v) { return fmtCompactUSD(v); }
                        }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: opts.tickColor, font: { size: 11 } }
                    }
                }
            }
        });
    }

    function renderChainsTvlTable(chains) {
        var body = document.getElementById('chainsTvlTableBody');
        if (!body) return;

        if (!chains || chains.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">No chain TVL data available</td></tr>';
            return;
        }

        body.innerHTML = chains.map(function(c, i) {
            return '<tr>' +
                '<td>' + (i + 1) + '</td>' +
                '<td><strong>' + (c.name || '') + '</strong></td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(c.tvl) + '</td>' +
                '<td>' + fmtChange(c.tvl_change_1d) + '</td>' +
                '<td>' + fmtChange(c.tvl_change_7d) + '</td>' +
                '</tr>';
        }).join('');
    }

    // ---- RWA Protocols ----

    async function loadRwaData() {
        try {
            var resp = await authFetch('/analytics/market/rwa?limit=15');
            var data = await resp.json();

            if (!data.success) {
                document.getElementById('rwaTableBody').innerHTML =
                    '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">Failed to load RWA data</td></tr>';
                return;
            }

            // Update summary card
            var rwaTvlEl = document.getElementById('cmRwaTvl');
            if (rwaTvlEl) rwaTvlEl.textContent = fmtCompactUSD(data.total_rwa_tvl);

            // Render table
            renderRwaTable(data.protocols);
        } catch (e) {
            console.error('Failed to load RWA data:', e);
        }
    }

    function renderRwaTable(protocols) {
        var body = document.getElementById('rwaTableBody');
        if (!body) return;

        if (!protocols || protocols.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">No RWA protocol data available</td></tr>';
            return;
        }

        body.innerHTML = protocols.map(function(p, i) {
            var chainStr = (p.chains || []).join(', ');
            var logoHtml = p.logo ? '<img src="' + p.logo + '" alt="" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:8px;">' : '';

            return '<tr>' +
                '<td>' + (i + 1) + '</td>' +
                '<td>' + logoHtml + '<strong>' + (p.name || '') + '</strong></td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(p.tvl) + '</td>' +
                '<td>' + fmtChange(p.tvl_change_1d) + '</td>' +
                '<td style="font-size:12px;color:#888;">' + chainStr + '</td>' +
                '</tr>';
        }).join('');
    }

})();
