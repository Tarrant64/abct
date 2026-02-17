/**
 * Crypto Market Tab
 * Handles: top cryptos, stablecoin markets, chains by TVL, RWA protocols, global market overview.
 * Data sourced from DefiLlama (free, no key) + CoinGecko/CMC for global metrics.
 */
(function() {
    'use strict';

    let _initialized = false;
    let _stablecoinChart = null;
    let _chainsTvlChart = null;

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
                // Clear pagination
                var pag = document.getElementById('topCryptosPagination');
                if (pag) pag.innerHTML = '';
                return;
            }

            _allCryptos = data.cryptos;

            renderTopCryptosTable();
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
