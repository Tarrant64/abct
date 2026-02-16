/**
 * Wallet Intelligence Tab
 *
 * Counterparty analysis, CEX detection, activity heatmaps,
 * and flow direction visualizations.
 */
(function() {
    'use strict';

    let _initialized = false;
    let _flowDoughnutChart = null;
    let _chainFlowChart = null;
    let _currentDays = 365;
    let _currentChain = '';
    let _allCounterparties = [];
    let _cpPage = 1;
    let _cpPageSize = 25;
    let _allLargeTx = [];
    let _ltPage = 1;
    let _ltPageSize = 25;

    // Color palette
    const FLOW_COLORS = {
        cexDeposit:   '#ef4444',
        cexWithdraw:  '#22c55e',
        selfTransfer: '#3b82f6',
        extSend:      '#f97316',
        extReceive:   '#a855f7',
    };

    const CHAIN_COLORS = {
        ethereum: '#627eea',
        cardano:  '#0033ad',
        bitcoin:  '#f7931a',
        solana:   '#9945ff',
        polygon:  '#8247e5',
        base:     '#0052ff',
    };

    function getThemeOptions() {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
        const isDark = theme !== 'light';
        return {
            isDark,
            gridColor:     isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
            tickColor:     isDark ? '#94a3b8' : '#6b7280',
            tooltipBg:     isDark ? '#1e293b' : '#ffffff',
            tooltipBorder: isDark ? '#334155' : '#e5e7eb',
            textColor:     isDark ? '#e0e0e0' : '#1a1a2e',
            heatmapLow:    isDark ? 'rgba(102, 126, 234, 0.15)' : 'rgba(102, 126, 234, 0.1)',
            heatmapHigh:   isDark ? 'rgba(102, 126, 234, 1)' : 'rgba(102, 126, 234, 0.9)',
            cellBg:        isDark ? '#1a1a2e' : '#f3f4f6',
        };
    }

    // ---- Public init ----

    window.initIntelligenceTab = function() {
        if (_initialized) return;
        _initialized = true;
        loadAllIntelligenceData();
    };

    window.changeIntelligencePeriod = function(days) {
        _currentDays = days;
        // Update active button
        document.querySelectorAll('.intelligence-period-btns .period-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        if (event && event.target) event.target.classList.add('active');
        loadAllIntelligenceData();
    };

    window.changeIntelligenceChain = function(chain) {
        _currentChain = chain;
        loadAllIntelligenceData();
    };

    window.updateIntelligenceTheme = function() {
        if (!_initialized) return;
        // Re-render charts with new theme
        loadAllIntelligenceData();
    };

    // ---- Data Loading ----

    async function loadAllIntelligenceData() {
        const params = new URLSearchParams();
        params.set('days', _currentDays);
        if (_currentChain) params.set('blockchain', _currentChain);
        const qs = params.toString();

        try {
            const [flowResp, counterResp, heatResp] = await Promise.all([
                authFetch(`/intelligence/flow-summary?${qs}`),
                authFetch(`/intelligence/counterparties?${qs}&limit=200`),
                authFetch(`/intelligence/activity-heatmap?${qs}`),
            ]);

            // Safely parse JSON, returning fallback on error
            async function safeJson(resp, fallback) {
                try {
                    const ct = resp.headers.get('content-type') || '';
                    if (!resp.ok || !ct.includes('application/json')) {
                        console.error(`Intelligence endpoint returned ${resp.status} (${ct.split(';')[0]}): ${resp.url}`);
                        return fallback;
                    }
                    return await resp.json();
                } catch (e) {
                    console.error('Failed to parse intelligence response:', e);
                    return fallback;
                }
            }

            const flowData = await safeJson(flowResp, { success: false });
            const counterData = await safeJson(counterResp, { success: false, counterparties: [] });
            const heatData = await safeJson(heatResp, { success: false, heatmap: [] });

            // Check for empty state
            const hasData = flowData.success && (flowData.total_sent > 0 || flowData.total_received > 0);
            const emptyEl = document.getElementById('intelEmptyState');
            if (!hasData && counterData.counterparties && counterData.counterparties.length === 0) {
                if (emptyEl) emptyEl.style.display = 'block';
                // Hide other sections
                document.querySelectorAll('#intelligenceTab .intelligence-summary-row, #intelligenceTab .intelligence-charts-row, #intelligenceTab .intelligence-heatmap-section, #intelligenceTab .intelligence-table-section').forEach(el => el.style.display = 'none');
                return;
            } else {
                if (emptyEl) emptyEl.style.display = 'none';
                document.querySelectorAll('#intelligenceTab .intelligence-summary-row, #intelligenceTab .intelligence-charts-row, #intelligenceTab .intelligence-heatmap-section, #intelligenceTab .intelligence-table-section').forEach(el => el.style.display = '');
            }

            if (flowData.success) {
                renderSummaryCards(flowData);
                renderFlowDoughnut(flowData);
                renderChainFlowBars(flowData);
            }
            if (counterData.success) {
                renderCounterpartiesTable(counterData.counterparties || []);
            }
            if (heatData.success) {
                renderActivityHeatmap(heatData.heatmap || []);
            }

            // Load large transactions with its own filters
            loadLargeTransactions();
        } catch (err) {
            console.error('Intelligence tab load error:', err);
        }
    }

    // ---- Summary Cards ----

    function renderSummaryCards(data) {
        const cpEl = document.getElementById('intelCounterpartyCount');
        const cexEl = document.getElementById('intelCexCount');
        const cexSub = document.getElementById('intelCexSub');
        const selfEl = document.getElementById('intelSelfCount');
        const netEl = document.getElementById('intelNetFlow');
        const netSub = document.getElementById('intelNetFlowSub');

        if (cpEl) cpEl.textContent = (data.unique_counterparties || 0).toLocaleString();
        const totalCex = (data.cex_deposits || 0) + (data.cex_withdrawals || 0);
        if (cexEl) cexEl.textContent = totalCex.toLocaleString();
        const exchangeTrades = data.exchange_trades || 0;
        if (cexSub) {
            let sub = `${data.cex_deposits || 0} deposits / ${data.cex_withdrawals || 0} withdrawals`;
            if (exchangeTrades > 0) sub += ` (${exchangeTrades} exchange trades)`;
            cexSub.textContent = sub;
        }
        if (selfEl) selfEl.textContent = (data.self_transfers || 0).toLocaleString();

        if (netEl) {
            const net = data.net_flow || 0;
            netEl.textContent = formatUsd(Math.abs(net));
            netEl.style.color = net >= 0 ? '#22c55e' : '#ef4444';
        }
        if (netSub) {
            netSub.innerHTML = `<span style="color:#ef4444">Sent ${formatUsd(data.total_sent || 0)}</span> &middot; <span style="color:#22c55e">Received ${formatUsd(data.total_received || 0)}</span>`;
        }
    }

    // ---- Flow Doughnut ----

    function renderFlowDoughnut(data) {
        const canvas = document.getElementById('intelFlowDoughnut');
        if (!canvas) return;

        if (_flowDoughnutChart) {
            _flowDoughnutChart.destroy();
            _flowDoughnutChart = null;
        }

        const opts = getThemeOptions();

        // Calculate segment values from flow data
        const cexDep = data.cex_deposits || 0;
        const cexWith = data.cex_withdrawals || 0;
        const selfTx = data.self_transfers || 0;

        // Estimate external sends/receives by subtracting CEX and self from total tx counts
        const chains = data.chains || {};
        let totalTxCount = 0;
        for (const c of Object.values(chains)) {
            totalTxCount += c.tx_count || 0;
        }
        const externalSend = Math.max(0, Math.round(totalTxCount / 2) - cexDep - selfTx);
        const externalRecv = Math.max(0, totalTxCount - Math.round(totalTxCount / 2) - cexWith);

        const labels = ['CEX Deposits', 'CEX Withdrawals', 'Self-Transfers', 'External Sends', 'External Receives'];
        const values = [cexDep, cexWith, selfTx, externalSend, externalRecv];
        const colors = [FLOW_COLORS.cexDeposit, FLOW_COLORS.cexWithdraw, FLOW_COLORS.selfTransfer, FLOW_COLORS.extSend, FLOW_COLORS.extReceive];

        _flowDoughnutChart = new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 0,
                    hoverOffset: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: opts.textColor,
                            padding: 12,
                            usePointStyle: true,
                            pointStyleWidth: 10,
                            font: { size: 12 },
                        }
                    },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        titleColor: opts.textColor,
                        bodyColor: opts.textColor,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        callbacks: {
                            label: function(ctx) {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                return ` ${ctx.label}: ${ctx.parsed} tx (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    // ---- Chain Flow Bars ----

    function renderChainFlowBars(data) {
        const canvas = document.getElementById('intelChainFlowBars');
        if (!canvas) return;

        if (_chainFlowChart) {
            _chainFlowChart.destroy();
            _chainFlowChart = null;
        }

        const opts = getThemeOptions();
        const chains = data.chains || {};
        const chainNames = Object.keys(chains);

        if (chainNames.length === 0) return;

        const labels = chainNames.map(c => c.charAt(0).toUpperCase() + c.slice(1));
        const sentData = chainNames.map(c => -(chains[c].sent || 0));
        const recvData = chainNames.map(c => chains[c].received || 0);

        _chainFlowChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Sent',
                        data: sentData,
                        backgroundColor: '#ef4444',
                        borderRadius: 4,
                    },
                    {
                        label: 'Received',
                        data: recvData,
                        backgroundColor: '#22c55e',
                        borderRadius: 4,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        grid: { color: opts.gridColor },
                        ticks: {
                            color: opts.tickColor,
                            callback: function(val) {
                                return formatCompact(Math.abs(val));
                            }
                        }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: opts.tickColor }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: opts.textColor, usePointStyle: true, pointStyleWidth: 10 }
                    },
                    tooltip: {
                        backgroundColor: opts.tooltipBg,
                        titleColor: opts.textColor,
                        bodyColor: opts.textColor,
                        borderColor: opts.tooltipBorder,
                        borderWidth: 1,
                        callbacks: {
                            label: function(ctx) {
                                return ` ${ctx.dataset.label}: ${formatUsd(Math.abs(ctx.parsed.x))}`;
                            }
                        }
                    }
                }
            }
        });
    }

    // ---- Activity Heatmap (SVG) ----

    function renderActivityHeatmap(heatmap) {
        const container = document.getElementById('intelHeatmapContainer');
        if (!container) return;

        const opts = getThemeOptions();
        const cellSize = 28;
        const cellGap = 3;
        const labelWidth = 40;
        const labelHeight = 24;
        const cols = 24;
        const rows = 7;
        const width = labelWidth + cols * (cellSize + cellGap);
        const height = labelHeight + rows * (cellSize + cellGap);

        // Build lookup
        const lookup = {};
        let maxCount = 1;
        for (const entry of heatmap) {
            const key = `${entry.day}-${entry.hour}`;
            lookup[key] = entry.count;
            if (entry.count > maxCount) maxCount = entry.count;
        }

        const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" style="display:block;max-width:100%;">`;

        // Hour labels (top) — 12-hour format
        for (let h = 0; h < cols; h++) {
            if (h % 3 === 0) {
                const x = labelWidth + h * (cellSize + cellGap) + cellSize / 2;
                const label = formatHour12(h);
                svg += `<text x="${x}" y="14" text-anchor="middle" fill="${opts.tickColor}" font-size="11" class="heatmap-axis-label">${label}</text>`;
            }
        }

        // Day rows
        for (let d = 0; d < rows; d++) {
            const y = labelHeight + d * (cellSize + cellGap);
            // Day label
            svg += `<text x="0" y="${y + cellSize / 2 + 4}" fill="${opts.tickColor}" font-size="11" class="heatmap-axis-label">${dayLabels[d]}</text>`;

            for (let h = 0; h < cols; h++) {
                const x = labelWidth + h * (cellSize + cellGap);
                const key = `${d}-${h}`;
                const count = lookup[key] || 0;
                const intensity = count / maxCount;
                const fill = count === 0 ? opts.cellBg : interpolateColor(opts.heatmapLow, opts.heatmapHigh, intensity);

                svg += `<rect x="${x}" y="${y}" width="${cellSize}" height="${cellSize}" rx="4" ry="4" fill="${fill}" class="heatmap-cell" data-day="${d}" data-hour="${h}" data-count="${count}" onmouseenter="showHeatmapTooltip(event, ${d}, ${h}, ${count})" onmouseleave="hideHeatmapTooltip()"/>`;
            }
        }

        // Legend
        const legendY = height - 2;
        svg += `<text x="${labelWidth}" y="${legendY}" fill="${opts.tickColor}" font-size="10">Less</text>`;
        for (let i = 0; i < 5; i++) {
            const lx = labelWidth + 30 + i * (12 + 2);
            const fill = i === 0 ? opts.cellBg : interpolateColor(opts.heatmapLow, opts.heatmapHigh, i / 4);
            svg += `<rect x="${lx}" y="${legendY - 10}" width="12" height="12" rx="2" fill="${fill}"/>`;
        }
        svg += `<text x="${labelWidth + 30 + 5 * 14 + 4}" y="${legendY}" fill="${opts.tickColor}" font-size="10">More</text>`;

        svg += '</svg>';
        container.innerHTML = svg;
    }

    window.showHeatmapTooltip = function(evt, day, hour, count) {
        const tooltip = document.getElementById('intelHeatmapTooltip');
        if (!tooltip) return;
        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        tooltip.textContent = `${dayNames[day]} ${formatHour12(hour)} UTC — ${count} transaction${count !== 1 ? 's' : ''}`;
        tooltip.style.display = 'block';

        const rect = evt.target.getBoundingClientRect();
        const containerRect = document.getElementById('intelHeatmapContainer').getBoundingClientRect();
        tooltip.style.left = (rect.left - containerRect.left + rect.width / 2) + 'px';
        tooltip.style.top = (rect.top - containerRect.top - 30) + 'px';
    };

    window.hideHeatmapTooltip = function() {
        const tooltip = document.getElementById('intelHeatmapTooltip');
        if (tooltip) tooltip.style.display = 'none';
    };

    // ---- Counterparties Table ----

    function renderCounterpartiesTable(counterparties) {
        _allCounterparties = counterparties;
        _cpPage = 1;
        renderCounterpartiesPage();
    }

    function renderCounterpartiesPage() {
        const tbody = document.getElementById('intelCounterpartiesBody');
        if (!tbody) return;

        if (!_allCounterparties.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888;">No counterparty data found</td></tr>';
            renderCpPagination();
            return;
        }

        const start = (_cpPage - 1) * _cpPageSize;
        const page = _allCounterparties.slice(start, start + _cpPageSize);

        let html = '';
        for (const cp of page) {
            const addr = cp.address || '';
            const truncated = addr.length > 16 ? addr.slice(0, 8) + '...' + addr.slice(-6) : addr;
            const badgeClass = cp.label_type === 'cex' ? 'cex' : cp.label_type === 'self' ? 'self' : 'unknown';
            const chain = (cp.blockchain || '').charAt(0).toUpperCase() + (cp.blockchain || '').slice(1);
            const sent = cp.total_sent || 0;
            const recv = cp.total_received || 0;
            const firstSeen = cp.first_seen ? formatDate(cp.first_seen) : '--';
            const lastSeen = cp.last_seen ? formatDate(cp.last_seen) : '--';

            html += `<tr>
                <td><span class="counterparty-address" title="${escapeHtml(addr)}">${escapeHtml(truncated)}</span>
                    <button class="copy-addr-btn" onclick="copyAddress('${escapeHtml(addr)}')" title="Copy address">&#128203;</button></td>
                <td><span class="counterparty-badge ${badgeClass}">${escapeHtml(cp.label || 'Unknown')}</span></td>
                <td>${escapeHtml(chain)}</td>
                <td>${cp.tx_count || 0}</td>
                <td class="privacy-sensitive" style="color:#ef4444">${sent > 0 ? formatUsd(sent) : '--'}</td>
                <td class="privacy-sensitive" style="color:#22c55e">${recv > 0 ? formatUsd(recv) : '--'}</td>
                <td>${firstSeen}</td>
                <td>${lastSeen}</td>
            </tr>`;
        }
        tbody.innerHTML = html;
        renderCpPagination();
    }

    function renderCpPagination() {
        const container = document.getElementById('intelCpPagination');
        if (!container) return;

        const total = _allCounterparties.length;
        const totalPages = Math.max(1, Math.ceil(total / _cpPageSize));
        const start = (_cpPage - 1) * _cpPageSize + 1;
        const end = Math.min(_cpPage * _cpPageSize, total);

        if (total === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `
            <div class="cp-pagination-controls">
                <span class="cp-pagination-info">${start}-${end} of ${total}</span>
                <button class="cp-page-btn" onclick="changeCpPage(-1)" ${_cpPage <= 1 ? 'disabled' : ''}>&laquo; Prev</button>
                <span class="cp-page-num">Page ${_cpPage} / ${totalPages}</span>
                <button class="cp-page-btn" onclick="changeCpPage(1)" ${_cpPage >= totalPages ? 'disabled' : ''}>Next &raquo;</button>
            </div>
        `;
    }

    window.changeCpPage = function(delta) {
        const totalPages = Math.max(1, Math.ceil(_allCounterparties.length / _cpPageSize));
        const newPage = _cpPage + delta;
        if (newPage < 1 || newPage > totalPages) return;
        _cpPage = newPage;
        renderCounterpartiesPage();
    };

    window.changeCpPageSize = function(size) {
        _cpPageSize = parseInt(size) || 25;
        _cpPage = 1;
        renderCounterpartiesPage();
    };

    // ---- Large Transactions ----

    async function loadLargeTransactions() {
        const minUsd = document.getElementById('largeTxMinUsd');
        const daysEl = document.getElementById('largeTxDays');
        const min = minUsd ? minUsd.value : 100;
        const days = daysEl ? daysEl.value : 0;

        const params = new URLSearchParams();
        params.set('min_usd', min);
        params.set('days', days);
        params.set('limit', '200');
        if (_currentChain) params.set('blockchain', _currentChain);

        try {
            const resp = await authFetch(`/intelligence/large-transactions?${params.toString()}`);
            const ct = resp.headers.get('content-type') || '';
            if (!resp.ok || !ct.includes('application/json')) {
                console.error(`Large tx endpoint returned ${resp.status}: ${resp.url}`);
                return;
            }
            const data = await resp.json();
            if (data.success) {
                _allLargeTx = data.transactions || [];
                _ltPage = 1;
                renderLargeTxPage();
            }
        } catch (err) {
            console.error('Large transactions load error:', err);
        }
    }

    function renderLargeTxPage() {
        const tbody = document.getElementById('intelLargeTxBody');
        if (!tbody) return;

        if (!_allLargeTx.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888;">No large transactions found</td></tr>';
            renderLtPagination();
            return;
        }

        const start = (_ltPage - 1) * _ltPageSize;
        const page = _allLargeTx.slice(start, start + _ltPageSize);

        let html = '';
        for (const tx of page) {
            const chain = (tx.blockchain || '').charAt(0).toUpperCase() + (tx.blockchain || '').slice(1);
            const dirColor = tx.direction === 'sent' ? '#ef4444' : '#22c55e';
            const dirArrow = tx.direction === 'sent' ? '&#8593; Sent' : '&#8595; Received';
            const cpAddr = tx.counterparty || '';
            const cpTrunc = cpAddr.length > 16 ? cpAddr.slice(0, 8) + '...' + cpAddr.slice(-6) : cpAddr;
            const cpLabel = tx.counterparty_label || 'Unknown';
            const txDate = tx.tx_time ? formatDate(tx.tx_time) : '--';
            const hashShort = tx.tx_hash_short || (tx.tx_hash ? tx.tx_hash.slice(0, 10) + '...' : '--');

            html += `<tr>
                <td>${txDate}</td>
                <td>${escapeHtml(chain)}</td>
                <td style="color:${dirColor};font-weight:600">${dirArrow}</td>
                <td>${escapeHtml(tx.token_symbol || '')}</td>
                <td class="privacy-sensitive">${formatAmount(tx.amount, tx.token_symbol)}</td>
                <td class="privacy-sensitive" style="font-weight:600">${formatUsd(tx.usd_value || 0)}</td>
                <td><span class="counterparty-address" title="${escapeHtml(cpAddr)}">${escapeHtml(cpTrunc)}</span>
                    ${cpLabel !== 'Unknown' ? `<span class="counterparty-badge ${cpLabel === 'Self' ? 'self' : 'cex'}" style="margin-left:4px;font-size:10px">${escapeHtml(cpLabel)}</span>` : ''}</td>
                <td><span class="counterparty-address" title="${escapeHtml(tx.tx_hash || '')}">${escapeHtml(hashShort)}</span></td>
            </tr>`;
        }
        tbody.innerHTML = html;
        renderLtPagination();
    }

    function renderLtPagination() {
        const container = document.getElementById('intelLargeTxPagination');
        if (!container) return;

        const total = _allLargeTx.length;
        const totalPages = Math.max(1, Math.ceil(total / _ltPageSize));
        const start = (_ltPage - 1) * _ltPageSize + 1;
        const end = Math.min(_ltPage * _ltPageSize, total);

        if (total === 0) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `
            <div class="cp-pagination-controls">
                <span class="cp-pagination-info">${start}-${end} of ${total}</span>
                <button class="cp-page-btn" onclick="changeLtPage(-1)" ${_ltPage <= 1 ? 'disabled' : ''}>&laquo; Prev</button>
                <span class="cp-page-num">Page ${_ltPage} / ${totalPages}</span>
                <button class="cp-page-btn" onclick="changeLtPage(1)" ${_ltPage >= totalPages ? 'disabled' : ''}>Next &raquo;</button>
            </div>
        `;
    }

    window.changeLtPage = function(delta) {
        const totalPages = Math.max(1, Math.ceil(_allLargeTx.length / _ltPageSize));
        const newPage = _ltPage + delta;
        if (newPage < 1 || newPage > totalPages) return;
        _ltPage = newPage;
        renderLargeTxPage();
    };

    window.changeLargeTxFilter = function() {
        loadLargeTransactions();
    };

    function formatAmount(val, symbol) {
        if (!val) return '0';
        // Format based on value magnitude
        if (val >= 1000) return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
        if (val >= 1) return val.toLocaleString(undefined, { maximumFractionDigits: 4 });
        return val.toLocaleString(undefined, { maximumFractionDigits: 6 });
    }

    window.copyAddress = function(addr) {
        navigator.clipboard.writeText(addr).then(() => {
            // Brief visual feedback
            if (typeof showStatus === 'function') {
                showStatus('Address copied to clipboard', 'success');
            }
        }).catch(() => {});
    };

    // ---- Helpers ----

    function formatUsd(val) {
        if (val >= 1e6) return '$' + (val / 1e6).toFixed(2) + 'M';
        if (val >= 1e3) return '$' + (val / 1e3).toFixed(1) + 'K';
        return '$' + val.toFixed(2);
    }

    function formatCompact(val) {
        if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
        if (val >= 1e3) return (val / 1e3).toFixed(1) + 'K';
        return val.toFixed(0);
    }

    function formatDate(isoStr) {
        if (!isoStr) return '--';
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatHour12(h) {
        if (h === 0) return '12AM';
        if (h < 12) return h + 'AM';
        if (h === 12) return '12PM';
        return (h - 12) + 'PM';
    }

    function interpolateColor(lowRgba, highRgba, t) {
        // Parse rgba strings
        const parseParts = (s) => {
            const m = s.match(/[\d.]+/g);
            return m ? m.map(Number) : [0, 0, 0, 0];
        };
        const low = parseParts(lowRgba);
        const high = parseParts(highRgba);
        const r = Math.round(low[0] + (high[0] - low[0]) * t);
        const g = Math.round(low[1] + (high[1] - low[1]) * t);
        const b = Math.round(low[2] + (high[2] - low[2]) * t);
        const a = (low[3] + (high[3] - low[3]) * t).toFixed(2);
        return `rgba(${r}, ${g}, ${b}, ${a})`;
    }

})();
