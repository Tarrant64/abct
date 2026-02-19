/**
 * Crypto Market Tab
 * Handles: top cryptos, stablecoin markets, chains by TVL, RWA protocols, global market overview.
 * Data sourced from DefiLlama (free, no key) + CoinGecko/CMC for global metrics.
 */
(function() {
    'use strict';

    let _initialized = false;
    let _stablecoinChart = null;
    let _stablecoinAreaChart = null;
    var _stableChartMode = 'bar'; // 'bar' or 'area'
    let _chainsTvlChart = null;
    let _chainsTvlAreaChart = null;
    var _chainChartMode = 'bar'; // 'bar' or 'area'
    var _chainsTvlHistoryLoaded = false;

    // ---- Pagination & sorting state ----

    // Top cryptos
    var _allCryptos = [];
    var _cryptoPage = 1;
    var _cryptoPageSize = 10;
    var _cryptoSortCol = 'rank';
    var _cryptoSortDir = 'asc';
    var _cryptoSource = 'cmc'; // 'cmc' or 'coingecko'

    // Stablecoins
    var _allStablecoins = [];
    var _stablePage = 1;
    var _stablePageSize = 10;
    var _stableSortCol = 'mcap';
    var _stableSortDir = 'desc';

    // Chains TVL
    var _allChainsTvl = [];
    var _chainsTvlPage = 1;
    var _chainsTvlPageSize = 10;
    var _chainsTvlSortCol = 'tvl';
    var _chainsTvlSortDir = 'desc';

    // RWA
    var _allRwa = [];
    var _rwaPage = 1;
    var _rwaPageSize = 10;
    var _rwaSortCol = 'tvl';
    var _rwaSortDir = 'desc';

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

    function fmtPrice(n) {
        if (n === null || n === undefined || isNaN(n)) return '--';
        if (n >= 1) return '$' + Number(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        if (n >= 0.01) return '$' + n.toFixed(4);
        return '$' + n.toFixed(6);
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

    // ---- Generic sort & paginate helpers ----

    function sortData(arr, col, dir) {
        return arr.slice().sort(function(a, b) {
            var va = a[col], vb = b[col];
            // String compare for name/symbol/classification
            if (typeof va === 'string' && typeof vb === 'string') {
                return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            va = Number(va) || 0;
            vb = Number(vb) || 0;
            return dir === 'asc' ? va - vb : vb - va;
        });
    }

    function paginateData(arr, page, pageSize) {
        var start = (page - 1) * pageSize;
        return arr.slice(start, start + pageSize);
    }

    function renderPagination(containerId, page, pageSize, totalItems, tableKey) {
        var el = document.getElementById(containerId);
        if (!el) return;

        var totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
        if (totalItems <= pageSize) {
            el.innerHTML = '';
            return;
        }

        el.innerHTML = '<div class="cp-pagination-controls">' +
            '<button class="cp-page-btn" onclick="changeCmPage(\'' + tableKey + '\', -1)"' + (page <= 1 ? ' disabled' : '') + '>&laquo; Prev</button>' +
            '<span class="cp-page-num">Page ' + page + ' of ' + totalPages + '</span>' +
            '<button class="cp-page-btn" onclick="changeCmPage(\'' + tableKey + '\', 1)"' + (page >= totalPages ? ' disabled' : '') + '>Next &raquo;</button>' +
            '</div>';
    }

    function updateSortHeaders(tableId, sortCol, sortDir, colMap) {
        var table = document.getElementById(tableId);
        if (!table) return;
        var headers = table.querySelectorAll('thead th.sortable');
        headers.forEach(function(th) {
            var arrow = th.querySelector('.sort-arrow');
            if (!arrow) return;
            // Find which col this th maps to by checking the onclick
            var onclick = th.getAttribute('onclick') || '';
            var match = onclick.match(/sortCryptoMarket\('[^']+','([^']+)'\)/);
            if (match) {
                var col = match[1];
                th.classList.remove('sort-active');
                if (col === sortCol) {
                    th.classList.add('sort-active');
                    arrow.textContent = sortDir === 'asc' ? '\u25B2' : '\u25BC';
                } else {
                    arrow.textContent = '\u25B2\u25BC';
                }
            }
        });
    }

    // ---- Global sort/page handlers ----

    window.sortCryptoMarket = function(table, col) {
        if (table === 'cryptos') {
            if (_cryptoSortCol === col) {
                _cryptoSortDir = _cryptoSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                _cryptoSortCol = col;
                _cryptoSortDir = (col === 'name' || col === 'rank') ? 'asc' : 'desc';
            }
            _cryptoPage = 1;
            renderTopCryptosTable();
        } else if (table === 'stablecoins') {
            if (_stableSortCol === col) {
                _stableSortDir = _stableSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                _stableSortCol = col;
                _stableSortDir = (col === 'name' || col === 'rank') ? 'asc' : 'desc';
            }
            _stablePage = 1;
            renderStablecoinTable();
        } else if (table === 'chainsTvl') {
            if (_chainsTvlSortCol === col) {
                _chainsTvlSortDir = _chainsTvlSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                _chainsTvlSortCol = col;
                _chainsTvlSortDir = (col === 'name' || col === 'rank') ? 'asc' : 'desc';
            }
            _chainsTvlPage = 1;
            renderChainsTvlTable();
        } else if (table === 'rwa') {
            if (_rwaSortCol === col) {
                _rwaSortDir = _rwaSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                _rwaSortCol = col;
                _rwaSortDir = (col === 'name' || col === 'rank') ? 'asc' : 'desc';
            }
            _rwaPage = 1;
            renderRwaTable();
        }
    };

    window.changeCmPage = function(table, delta) {
        if (table === 'cryptos') {
            var maxPage = Math.ceil(_allCryptos.length / _cryptoPageSize);
            _cryptoPage = Math.max(1, Math.min(_cryptoPage + delta, maxPage));
            renderTopCryptosTable();
        } else if (table === 'stablecoins') {
            var maxPage = Math.ceil(_allStablecoins.length / _stablePageSize);
            _stablePage = Math.max(1, Math.min(_stablePage + delta, maxPage));
            renderStablecoinTable();
        } else if (table === 'chainsTvl') {
            var maxPage = Math.ceil(_allChainsTvl.length / _chainsTvlPageSize);
            _chainsTvlPage = Math.max(1, Math.min(_chainsTvlPage + delta, maxPage));
            renderChainsTvlTable();
        } else if (table === 'rwa') {
            var maxPage = Math.ceil(_allRwa.length / _rwaPageSize);
            _rwaPage = Math.max(1, Math.min(_rwaPage + delta, maxPage));
            renderRwaTable();
        }
    };

    window.changeCmPageSize = function(table, size) {
        size = parseInt(size, 10) || 10;
        if (table === 'cryptos') {
            _cryptoPageSize = size;
            _cryptoPage = 1;
            renderTopCryptosTable();
        } else if (table === 'stablecoins') {
            _stablePageSize = size;
            _stablePage = 1;
            renderStablecoinTable();
        } else if (table === 'chainsTvl') {
            _chainsTvlPageSize = size;
            _chainsTvlPage = 1;
            renderChainsTvlTable();
        } else if (table === 'rwa') {
            _rwaPageSize = size;
            _rwaPage = 1;
            renderRwaTable();
        }
    };

    window.switchCryptoSource = function(source) {
        if (source === _cryptoSource) return;
        _cryptoSource = source;
        _cryptoPage = 1;

        // Update toggle buttons
        document.querySelectorAll('.cm-source-btn').forEach(function(btn) {
            btn.classList.remove('active');
        });
        var activeBtn = document.getElementById('srcBtn' + source.charAt(0).toUpperCase() + source.slice(1));
        if (activeBtn) activeBtn.classList.add('active');

        // Show loading state
        var body = document.getElementById('topCryptosTableBody');
        if (body) body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">Loading...</td></tr>';

        // Re-fetch from selected source
        loadTopCryptos();
    };

    window.switchChainChart = function(mode) {
        if (mode === _chainChartMode) return;
        _chainChartMode = mode;

        // Update toggle buttons
        var barBtn = document.getElementById('chainChartBar');
        var areaBtn = document.getElementById('chainChartArea');
        if (barBtn) barBtn.classList.toggle('active', mode === 'bar');
        if (areaBtn) areaBtn.classList.toggle('active', mode === 'area');

        var barContainer = document.getElementById('chainsTvlChartContainer');
        var areaContainer = document.getElementById('chainsTvlAreaContainer');

        if (mode === 'bar') {
            if (barContainer) barContainer.style.display = 'block';
            if (areaContainer) areaContainer.style.display = 'none';
        } else {
            if (barContainer) barContainer.style.display = 'none';
            if (areaContainer) areaContainer.style.display = 'block';

            // Lazy-load area chart data on first switch
            if (!_chainsTvlHistoryLoaded) {
                _chainsTvlHistoryLoaded = true;
                loadChainsTvlHistory();
            }
        }
    };

    // ---- Lock / Unlock ----

    window.checkCryptoMarketLock = async function() {
        const btn = document.getElementById('cryptoMarketTabBtn');
        if (!btn) return;

        try {
            const resp = await authFetch('/settings/apis');
            const data = await resp.json();

            // Response is { categories: { "pricing": { apis: [...] }, ... } }
            // Flatten all apis from every category
            const allApis = [];
            const categories = data.categories || {};
            for (const cat of Object.values(categories)) {
                if (cat.apis) allApis.push(...cat.apis);
            }

            let hasGlobalSource = false;
            for (const api of allApis) {
                const id = (api.id || '').toLowerCase();
                if ((id === 'coingecko' || id === 'coinmarketcap') && api.enabled && api.configured) {
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
        loadTopCryptos();
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

    // ---- Top Cryptos ----

    async function loadTopCryptos() {
        try {
            var resp = await authFetch('/analytics/market/top-cryptos?limit=50&source=' + _cryptoSource);
            var data = await resp.json();

            if (!data.success || !data.cryptos || data.cryptos.length === 0) {
                var msg = data.error || 'Failed to load top cryptos';
                if (msg.indexOf('not configured') !== -1) {
                    var sourceNames = {cmc: 'CoinMarketCap', coingecko: 'CoinGecko'};
                    var keyName = sourceNames[_cryptoSource];
                    if (keyName) {
                        msg = 'Requires ' + keyName + ' API key. <a href="/settings.html#apis" style="color:#667eea;">Configure in Settings</a>';
                    }
                }
                document.getElementById('topCryptosTableBody').innerHTML =
                    '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">' + msg + '</td></tr>';
                // Clear pagination and heatmap
                var pag = document.getElementById('topCryptosPagination');
                if (pag) pag.innerHTML = '';
                var hm = document.getElementById('cryptoHeatmapContainer');
                if (hm) hm.innerHTML = '<div style="text-align:center;color:#888;padding:60px;">Heatmap requires top crypto data</div>';
                return;
            }

            _allCryptos = data.cryptos;

            renderTopCryptosTable();

            // Render heatmap with top cryptos data
            renderCryptoHeatmap(_allCryptos);
        } catch (e) {
            console.error('Failed to load top cryptos:', e);
        }
    }

    function renderTopCryptosTable() {
        var body = document.getElementById('topCryptosTableBody');
        if (!body) return;

        var sorted = sortData(_allCryptos, _cryptoSortCol, _cryptoSortDir);
        var page = paginateData(sorted, _cryptoPage, _cryptoPageSize);

        if (page.length === 0) {
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">No data</td></tr>';
            return;
        }

        body.innerHTML = page.map(function(c) {
            return '<tr>' +
                '<td>' + (c.rank || '--') + '</td>' +
                '<td><strong>' + (c.name || '') + '</strong> <span style="color:#888;">(' + (c.symbol || '') + ')</span></td>' +
                '<td class="privacy-sensitive">' + fmtPrice(c.price) + '</td>' +
                '<td>' + fmtChange(c.change_24h) + '</td>' +
                '<td>' + fmtChange(c.change_7d) + '</td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(c.market_cap) + '</td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(c.volume_24h) + '</td>' +
                '</tr>';
        }).join('');

        updateSortHeaders('topCryptosTable', _cryptoSortCol, _cryptoSortDir);
        renderPagination('topCryptosPagination', _cryptoPage, _cryptoPageSize, _allCryptos.length, 'cryptos');
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

            _allStablecoins = data.stablecoins || [];

            // Render chart (top 10 from full dataset)
            renderStablecoinChart(_allStablecoins.slice(0, 10));

            // Render paginated table
            renderStablecoinTable();
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

    function renderStablecoinAreaChart(stablecoins) {
        var container = document.getElementById('stablecoinAreaContainer');
        var canvas = document.getElementById('stablecoinAreaChart');
        if (!container || !canvas) return;

        if (_stablecoinAreaChart) {
            _stablecoinAreaChart.destroy();
            _stablecoinAreaChart = null;
        }

        container.style.display = 'block';
        var opts = getChartOpts();

        // Build a treemap-like stacked bar showing proportional market share
        var labels = stablecoins.map(function(s) { return s.symbol || s.name; });
        var values = stablecoins.map(function(s) { return s.mcap; });
        var total = values.reduce(function(sum, v) { return sum + v; }, 0);
        var pcts = values.map(function(v) { return total > 0 ? (v / total * 100) : 0; });

        var colors = [
            'rgba(38, 161, 123, 0.8)', 'rgba(39, 117, 202, 0.8)', 'rgba(240, 185, 11, 0.8)',
            'rgba(0, 211, 149, 0.8)', 'rgba(99, 102, 241, 0.8)', 'rgba(59, 130, 246, 0.8)',
            'rgba(34, 211, 238, 0.8)', 'rgba(167, 139, 250, 0.8)', 'rgba(251, 146, 60, 0.8)',
            'rgba(148, 163, 184, 0.8)'
        ];
        var borderColors = [
            '#26a17b', '#2775ca', '#f0b90b', '#00d395', '#6366f1',
            '#3b82f6', '#22d3ee', '#a78bfa', '#fb923c', '#94a3b8'
        ];

        // Stacked horizontal bar (single row, multiple datasets)
        var datasets = labels.map(function(label, i) {
            return {
                label: label + ' (' + pcts[i].toFixed(1) + '%)',
                data: [pcts[i]],
                backgroundColor: colors[i % colors.length],
                borderColor: borderColors[i % borderColors.length],
                borderWidth: 1,
                barPercentage: 1.0,
                categoryPercentage: 1.0
            };
        });

        _stablecoinAreaChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: ['Market Share'],
                datasets: datasets
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true,
                        max: 100,
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: function(v) { return v + '%'; }
                        }
                    },
                    y: {
                        stacked: true,
                        display: false
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: opts.tickColor,
                            usePointStyle: true,
                            pointStyle: 'rectRounded',
                            padding: 12,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        titleColor: opts.tickColor,
                        bodyColor: opts.tickColor,
                        callbacks: {
                            label: function(ctx) {
                                var idx = ctx.datasetIndex;
                                return labels[idx] + ': ' + fmtCompactUSD(values[idx]) + ' (' + pcts[idx].toFixed(1) + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    window.switchStablecoinChart = function(mode) {
        if (mode === _stableChartMode) return;
        _stableChartMode = mode;

        var barBtn = document.getElementById('stableChartBar');
        var areaBtn = document.getElementById('stableChartArea');
        if (barBtn) barBtn.classList.toggle('active', mode === 'bar');
        if (areaBtn) areaBtn.classList.toggle('active', mode === 'area');

        var barContainer = document.getElementById('stablecoinChartContainer');
        var areaContainer = document.getElementById('stablecoinAreaContainer');

        if (mode === 'bar') {
            if (barContainer) barContainer.style.display = 'block';
            if (areaContainer) areaContainer.style.display = 'none';
        } else {
            if (barContainer) barContainer.style.display = 'none';
            if (areaContainer) areaContainer.style.display = 'block';
            // Render area chart from existing data
            if (_allStablecoins && _allStablecoins.length > 0) {
                renderStablecoinAreaChart(_allStablecoins.slice(0, 10));
            }
        }
    };

    function renderStablecoinTable() {
        var body = document.getElementById('stablecoinTableBody');
        if (!body) return;

        if (!_allStablecoins || _allStablecoins.length === 0) {
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:40px;">No stablecoin data available</td></tr>';
            return;
        }

        var sorted = sortData(_allStablecoins, _stableSortCol, _stableSortDir);
        var page = paginateData(sorted, _stablePage, _stablePageSize);

        // Calculate the global rank offset for the current page
        var rankOffset = (_stablePage - 1) * _stablePageSize;

        body.innerHTML = page.map(function(s, i) {
            var chainStr = (s.chains || []).slice(0, 5).join(', ');
            if ((s.chains || []).length > 5) chainStr += '...';
            var priceStr = s.price !== null && s.price !== undefined ? '$' + Number(s.price).toFixed(4) : '--';

            return '<tr>' +
                '<td>' + (rankOffset + i + 1) + '</td>' +
                '<td><strong>' + (s.name || '') + '</strong> (' + (s.symbol || '') + ')</td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(s.mcap) + '</td>' +
                '<td>' + fmtChange(s.mcap_change_7d) + '</td>' +
                '<td>' + priceStr + '</td>' +
                '<td>' + (s.classification || '--') + '</td>' +
                '<td style="font-size:12px;color:#888;">' + chainStr + '</td>' +
                '</tr>';
        }).join('');

        updateSortHeaders('stablecoinTable', _stableSortCol, _stableSortDir);
        renderPagination('stablecoinPagination', _stablePage, _stablePageSize, _allStablecoins.length, 'stablecoins');
    }

    // ---- Chains by TVL ----

    async function loadChainsTvl() {
        try {
            const resp = await authFetch('/analytics/market/chains-tvl?limit=50');
            const data = await resp.json();

            if (!data.success) {
                document.getElementById('chainsTvlTableBody').innerHTML =
                    '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">Failed to load chain TVL data</td></tr>';
                return;
            }

            _allChainsTvl = data.chains || [];

            // Render chart (top 15 from full dataset)
            renderChainsTvlChart(_allChainsTvl.slice(0, 15));

            // Render paginated table
            renderChainsTvlTable();
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

    function renderChainsTvlTable() {
        var body = document.getElementById('chainsTvlTableBody');
        if (!body) return;

        if (!_allChainsTvl || _allChainsTvl.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">No chain TVL data available</td></tr>';
            return;
        }

        var sorted = sortData(_allChainsTvl, _chainsTvlSortCol, _chainsTvlSortDir);
        var page = paginateData(sorted, _chainsTvlPage, _chainsTvlPageSize);

        var rankOffset = (_chainsTvlPage - 1) * _chainsTvlPageSize;

        body.innerHTML = page.map(function(c, i) {
            return '<tr>' +
                '<td>' + (rankOffset + i + 1) + '</td>' +
                '<td><strong>' + (c.name || '') + '</strong></td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(c.tvl) + '</td>' +
                '<td>' + fmtChange(c.tvl_change_1d) + '</td>' +
                '<td>' + fmtChange(c.tvl_change_7d) + '</td>' +
                '</tr>';
        }).join('');

        updateSortHeaders('chainsTvlTable', _chainsTvlSortCol, _chainsTvlSortDir);
        renderPagination('chainsTvlPagination', _chainsTvlPage, _chainsTvlPageSize, _allChainsTvl.length, 'chainsTvl');
    }

    // ---- Chains TVL Area Chart (historical) ----

    async function loadChainsTvlHistory() {
        var container = document.getElementById('chainsTvlAreaContainer');
        if (!container) return;

        // Show loading
        var canvas = document.getElementById('chainsTvlAreaChart');
        if (canvas) canvas.style.opacity = '0.3';

        try {
            var resp = await authFetch('/analytics/market/chains-tvl-history?limit=10&days=90');
            var data = await resp.json();

            if (!data.success || !data.series || data.series.length === 0) {
                container.innerHTML = '<div style="text-align:center;color:#888;padding:60px;">Failed to load historical TVL data</div>';
                return;
            }

            renderChainsTvlAreaChart(data.chains, data.series);
        } catch (e) {
            console.error('Failed to load chains TVL history:', e);
            container.innerHTML = '<div style="text-align:center;color:#888;padding:60px;">Error loading historical data</div>';
        }
    }

    function renderChainsTvlAreaChart(chainNames, series) {
        var container = document.getElementById('chainsTvlAreaContainer');
        var canvas = document.getElementById('chainsTvlAreaChart');
        if (!container || !canvas) return;

        if (_chainsTvlAreaChart) {
            _chainsTvlAreaChart.destroy();
            _chainsTvlAreaChart = null;
        }

        container.style.display = 'block';
        canvas.style.opacity = '1';
        var opts = getChartOpts();

        // Build labels (dates)
        var labels = series.map(function(s) {
            var d = new Date(s.date * 1000);
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        });

        // Color palette for chains
        var palette = [
            'rgba(99, 102, 241, 0.7)',   // Indigo
            'rgba(59, 130, 246, 0.7)',   // Blue
            'rgba(34, 211, 238, 0.7)',   // Cyan
            'rgba(16, 185, 129, 0.7)',   // Emerald
            'rgba(245, 158, 11, 0.7)',   // Amber
            'rgba(239, 68, 68, 0.7)',    // Red
            'rgba(168, 85, 247, 0.7)',   // Purple
            'rgba(236, 72, 153, 0.7)',   // Pink
            'rgba(20, 184, 166, 0.7)',   // Teal
            'rgba(249, 115, 22, 0.7)',   // Orange
        ];
        var borderPalette = [
            'rgb(99, 102, 241)',
            'rgb(59, 130, 246)',
            'rgb(34, 211, 238)',
            'rgb(16, 185, 129)',
            'rgb(245, 158, 11)',
            'rgb(239, 68, 68)',
            'rgb(168, 85, 247)',
            'rgb(236, 72, 153)',
            'rgb(20, 184, 166)',
            'rgb(249, 115, 22)',
        ];

        // Build datasets (one per chain, stacked)
        var datasets = chainNames.map(function(name, idx) {
            return {
                label: name,
                data: series.map(function(s) { return s[name] || 0; }),
                fill: true,
                backgroundColor: palette[idx % palette.length],
                borderColor: borderPalette[idx % borderPalette.length],
                borderWidth: 1,
                pointRadius: 0,
                pointHitRadius: 10,
                tension: 0.3,
            };
        });

        _chainsTvlAreaChart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: opts.tickColor,
                            usePointStyle: true,
                            pointStyle: 'rectRounded',
                            padding: 12,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        titleColor: opts.tickColor,
                        bodyColor: opts.tickColor,
                        callbacks: {
                            label: function(ctx) {
                                return ctx.dataset.label + ': ' + fmtCompactUSD(ctx.parsed.y);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            maxTicksLimit: 12,
                            font: { size: 10 }
                        }
                    },
                    y: {
                        stacked: true,
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: function(v) { return fmtCompactUSD(v); }
                        }
                    }
                }
            }
        });
    }

    // ---- RWA Protocols ----

    async function loadRwaData() {
        try {
            var resp = await authFetch('/analytics/market/rwa?limit=50');
            var data = await resp.json();

            if (!data.success) {
                document.getElementById('rwaTableBody').innerHTML =
                    '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">Failed to load RWA data</td></tr>';
                return;
            }

            // Update summary card
            var rwaTvlEl = document.getElementById('cmRwaTvl');
            if (rwaTvlEl) rwaTvlEl.textContent = fmtCompactUSD(data.total_rwa_tvl);

            _allRwa = data.protocols || [];
            renderRwaTable();
        } catch (e) {
            console.error('Failed to load RWA data:', e);
        }
    }

    function renderRwaTable() {
        var body = document.getElementById('rwaTableBody');
        if (!body) return;

        if (!_allRwa || _allRwa.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;padding:40px;">No RWA protocol data available</td></tr>';
            return;
        }

        var sorted = sortData(_allRwa, _rwaSortCol, _rwaSortDir);
        var page = paginateData(sorted, _rwaPage, _rwaPageSize);

        var rankOffset = (_rwaPage - 1) * _rwaPageSize;

        body.innerHTML = page.map(function(p, i) {
            var chainStr = (p.chains || []).join(', ');
            var logoHtml = p.logo ? '<img src="' + p.logo + '" alt="" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:8px;">' : '';

            return '<tr>' +
                '<td>' + (rankOffset + i + 1) + '</td>' +
                '<td>' + logoHtml + '<strong>' + (p.name || '') + '</strong></td>' +
                '<td class="privacy-sensitive">' + fmtCompactUSD(p.tvl) + '</td>' +
                '<td>' + fmtChange(p.tvl_change_1d) + '</td>' +
                '<td style="font-size:12px;color:#888;">' + chainStr + '</td>' +
                '</tr>';
        }).join('');

        updateSortHeaders('rwaTable', _rwaSortCol, _rwaSortDir);
        renderPagination('rwaPagination', _rwaPage, _rwaPageSize, _allRwa.length, 'rwa');
    }

    // ---- Market Heatmap ----

    function renderCryptoHeatmap(cryptos) {
        var container = document.getElementById('cryptoHeatmapContainer');
        if (!container) return;

        if (!cryptos || cryptos.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:#888;padding:60px;">No heatmap data available</div>';
            return;
        }

        // Map crypto data to the format expected by global layoutTreemapTiles
        // It expects objects with value_usd for sizing
        var tokens = cryptos.map(function(c) {
            return {
                symbol: c.symbol || '',
                name: c.name || '',
                value_usd: c.market_cap || 0,
                change24h: c.change_24h || 0
            };
        }).filter(function(t) { return t.value_usd > 0; });

        tokens.sort(function(a, b) { return b.value_usd - a.value_usd; });

        var containerWidth = container.clientWidth || 800;
        var totalHeight = 400;

        // Use global squarified treemap layout from app.js
        var tiles = layoutTreemapTiles(tokens, containerWidth, totalHeight);

        var tilesHtml = '';
        for (var i = 0; i < tiles.length; i++) {
            var tile = tiles[i];
            var bgColor = getHeatmapColor(tile.token.change24h);
            var changeStr = (tile.token.change24h >= 0 ? '+' : '') + tile.token.change24h.toFixed(2) + '%';
            var mcapStr = fmtCompactUSD(tile.token.value_usd);

            // Size text based on tile area
            var area = tile.w * tile.h;
            var symbolSize, changeSize, mcapSize;
            if (area > 40000) {
                symbolSize = '1.8rem'; changeSize = '1.2rem'; mcapSize = '1rem';
            } else if (area > 20000) {
                symbolSize = '1.4rem'; changeSize = '1rem'; mcapSize = '0.85rem';
            } else if (area > 8000) {
                symbolSize = '1.1rem'; changeSize = '0.85rem'; mcapSize = '0.75rem';
            } else if (area > 3000) {
                symbolSize = '0.9rem'; changeSize = '0.75rem'; mcapSize = '0.65rem';
            } else if (area > 1000) {
                symbolSize = '0.75rem'; changeSize = '0.6rem'; mcapSize = '0';
            } else {
                symbolSize = '0.65rem'; changeSize = '0'; mcapSize = '0';
            }

            tilesHtml += '<div class="heatmap-tile" style="' +
                'position:absolute;left:' + tile.x + 'px;top:' + tile.y + 'px;' +
                'width:' + tile.w + 'px;height:' + tile.h + 'px;' +
                'background:' + bgColor + ';" ' +
                'title="' + tile.token.name + ' (' + tile.token.symbol + '): ' + mcapStr + ' (' + changeStr + ')">' +
                '<span class="tile-symbol" style="font-size:' + symbolSize + '">' + tile.token.symbol + '</span>' +
                (changeSize !== '0' ? '<span class="tile-change" style="font-size:' + changeSize + '">' + changeStr + '</span>' : '') +
                (mcapSize !== '0' ? '<span class="tile-value" style="font-size:' + mcapSize + '">' + mcapStr + '</span>' : '') +
                '</div>';
        }

        container.innerHTML = '<div style="position:relative;width:' + containerWidth + 'px;height:' + totalHeight + 'px;">' + tilesHtml + '</div>';
    }

})();
