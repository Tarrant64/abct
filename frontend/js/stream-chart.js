// ===========================
// Portfolio Streamgraph
// ===========================
// Centered wiggle-baseline streamgraph showing chain value history over time.
// Uses d3-shape (stackOffsetWiggle, curveBasis, area) + d3-array (stack, etc.)
// Mirrors sankey-chart.js conventions: custom SVG, ResizeObserver, theme helpers, tooltip.

class PortfolioStreamgraph {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        this.svg = null;
        this.tooltip = null;
        this.crosshair = null;
        this.width = 0;
        this.height = 0;
        this.data = null;       // raw API response
        this.stackData = null;  // prepared stack output
        this.chains = [];       // ordered chain keys
        this.activeRange = '1y';
        this.lockedChain = null; // click-locked highlight
        this.hoveredChain = null;

        this.padding = { top: 20, right: 30, bottom: 32, left: 60 };

        this._createSVG();
        this._createTooltip();
        this._setupResizeObserver();
    }

    // ===========================
    // Setup
    // ===========================

    _createSVG() {
        this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svg.setAttribute('class', 'stream-svg');
        this.svg.setAttribute('width', '100%');
        this.svg.setAttribute('height', '100%');
        this.container.appendChild(this.svg);
    }

    _createTooltip() {
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'stream-tooltip';
        this.tooltip.style.display = 'none';
        this.container.appendChild(this.tooltip);
    }

    _setupResizeObserver() {
        this._resizeObserver = new ResizeObserver(() => {
            if (this.stackData) this.render();
        });
        this._resizeObserver.observe(this.container);
    }

    // ===========================
    // Public API
    // ===========================

    async loadData(range) {
        this.activeRange = range || '3m';

        // Update range button active states
        this.container.closest('#portfolioStreamSection')?.querySelectorAll('.stream-range-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.range === this.activeRange);
        });

        // Check chartDataCache first (shared with by-chain line chart)
        let result = null;
        if (typeof chartDataCache !== 'undefined') {
            result = chartDataCache.get(this.activeRange, 'by_chain');
        }

        if (!result) {
            try {
                const resp = await authFetch(`${API_BASE}/portfolio/chart/unified?by_chain=true&range=${this.activeRange}`);
                if (!resp.ok) throw new Error(`API ${resp.status}`);
                result = await resp.json();
                if (result.data && result.data.length > 0 && typeof chartDataCache !== 'undefined') {
                    chartDataCache.set(this.activeRange, 'by_chain', result);
                }
            } catch (e) {
                console.warn('[Streamgraph] Failed to load data:', e);
                this._showEmpty('Failed to load data');
                return;
            }
        }

        if (!result || !result.data || result.data.length < 2) {
            this._showEmpty('Not enough history data (need 2+ days)');
            return;
        }

        this.data = result;
        this._prepareStackData();
        this.render();
        this.container.closest('#portfolioStreamSection')?.classList.remove('hidden');
    }

    render() {
        if (!this.container || !this.svg || !this.stackData) return;

        const rect = this.container.getBoundingClientRect();
        this.width = rect.width;
        this.height = rect.height || 420;

        while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
        this.svg.setAttribute('viewBox', `0 0 ${this.width} ${this.height}`);

        const plotW = this.width - this.padding.left - this.padding.right;
        const plotH = this.height - this.padding.top - this.padding.bottom;
        if (plotW < 50 || plotH < 50) return;

        this._computeScales(plotW, plotH);
        this._drawStreams(plotW, plotH);
        this._drawTimeAxis(plotW, plotH);
        this._drawLabels(plotW, plotH);
        this._drawCrosshairLine(plotH);
    }

    updateTheme() {
        if (this.stackData) this.render();
    }

    destroy() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this.tooltip?.parentNode) this.tooltip.parentNode.removeChild(this.tooltip);
        if (this.svg?.parentNode) this.svg.parentNode.removeChild(this.svg);
        this.svg = null;
        this.tooltip = null;
    }

    // ===========================
    // Data Pipeline
    // ===========================

    _prepareStackData() {
        const raw = this.data.data;
        const chainList = this.data.chains || [];

        // Compute peak total to filter trivial chains
        let maxTotal = 0;
        for (const d of raw) {
            let total = 0;
            for (const c of chainList) total += (d.chains?.[c] || 0);
            if (total > maxTotal) maxTotal = total;
        }
        const threshold = maxTotal * 0.001; // chains with peak < 0.1% are "Other"

        // Classify chains
        const mainChains = [];
        const otherChains = [];
        for (const c of chainList) {
            let peak = 0;
            for (const d of raw) {
                const v = d.chains?.[c] || 0;
                if (v > peak) peak = v;
            }
            if (peak >= threshold) {
                mainChains.push(c);
            } else {
                otherChains.push(c);
            }
        }

        // Sort by total value descending so biggest chains are in the center (insideOut handles this)
        mainChains.sort((a, b) => {
            const sumA = raw.reduce((s, d) => s + (d.chains?.[a] || 0), 0);
            const sumB = raw.reduce((s, d) => s + (d.chains?.[b] || 0), 0);
            return sumB - sumA;
        });

        // Build tabular data: [{date, chain1: val, chain2: val, ...}]
        const hasOther = otherChains.length > 0;
        this.chains = hasOther ? [...mainChains, '_other'] : [...mainChains];

        this._tabularData = raw.map(d => {
            const row = { date: d.date };
            for (const c of mainChains) {
                row[c] = Math.max(0, d.chains?.[c] || 0);
            }
            if (hasOther) {
                let otherVal = 0;
                for (const c of otherChains) otherVal += Math.max(0, d.chains?.[c] || 0);
                row._other = otherVal;
            }
            return row;
        });

        // D3 stack with wiggle offset + insideOut ordering
        const stack = d3.stack()
            .keys(this.chains)
            .offset(d3.stackOffsetWiggle)
            .order(d3.stackOrderInsideOut);

        this.stackData = stack(this._tabularData);
    }

    // ===========================
    // Scales
    // ===========================

    _computeScales(plotW, plotH) {
        const n = this._tabularData.length;
        this._xScale = (i) => this.padding.left + (i / (n - 1)) * plotW;

        // Find y extent across all stacked series
        let yMin = Infinity, yMax = -Infinity;
        for (const series of this.stackData) {
            for (const [y0, y1] of series) {
                if (y0 < yMin) yMin = y0;
                if (y1 > yMax) yMax = y1;
            }
        }
        const yRange = yMax - yMin || 1;
        this._yScale = (v) => this.padding.top + plotH - ((v - yMin) / yRange) * plotH;
    }

    // ===========================
    // Drawing
    // ===========================

    _drawStreams(plotW, plotH) {
        const g = this._svgEl('g', { class: 'stream-paths' });

        // D3 area generator
        const areaGen = d3.area()
            .x((d, i) => this._xScale(i))
            .y0(d => this._yScale(d[0]))
            .y1(d => this._yScale(d[1]))
            .curve(d3.curveBasis);

        for (let si = 0; si < this.stackData.length; si++) {
            const series = this.stackData[si];
            const chain = series.key;
            const color = this._getStreamColor(chain);
            const pathD = areaGen(series);

            const isActive = this.lockedChain === chain || this.hoveredChain === chain;
            const isDimmed = (this.lockedChain || this.hoveredChain) && !isActive;

            const path = this._svgEl('path', {
                d: pathD,
                class: 'stream-path',
                fill: color,
                'fill-opacity': isDimmed ? '0.15' : '0.85',
                stroke: isActive ? this._getAccentColor() : 'none',
                'stroke-width': isActive ? '1.5' : '0',
                'data-chain': chain,
            });

            path.addEventListener('mouseenter', (e) => this._onStreamHover(e, chain));
            path.addEventListener('mousemove', (e) => this._onStreamMove(e, chain));
            path.addEventListener('mouseleave', () => this._onStreamLeave());
            path.addEventListener('click', () => this._onStreamClick(chain));

            g.appendChild(path);
        }

        this.svg.appendChild(g);
    }

    _drawLabels(plotW, plotH) {
        const g = this._svgEl('g', { class: 'stream-labels' });
        const minLabelHeight = 30;

        for (let si = 0; si < this.stackData.length; si++) {
            const series = this.stackData[si];
            const chain = series.key;

            // Find widest point of this stream
            let maxHeight = 0;
            let maxIdx = 0;
            for (let i = 0; i < series.length; i++) {
                const h = Math.abs(this._yScale(series[i][0]) - this._yScale(series[i][1]));
                if (h > maxHeight) {
                    maxHeight = h;
                    maxIdx = i;
                }
            }

            if (maxHeight < minLabelHeight) continue;

            let x = this._xScale(maxIdx);
            const yMid = (this._yScale(series[maxIdx][0]) + this._yScale(series[maxIdx][1])) / 2;
            const label = this._chainLabel(chain);

            // Estimate text width and clamp to prevent edge clipping
            const fontSize = maxHeight > 60 ? 13 : 11;
            const estWidth = label.length * fontSize * 0.6;
            let anchor = 'middle';
            const minX = this.padding.left + estWidth / 2 + 4;
            const maxX = this.width - this.padding.right - estWidth / 2 - 4;
            if (x < minX) { x = this.padding.left + 4; anchor = 'start'; }
            else if (x > maxX) { x = this.width - this.padding.right - 4; anchor = 'end'; }

            const text = this._svgEl('text', {
                x: x,
                y: yMid,
                'text-anchor': anchor,
                'dominant-baseline': 'central',
                class: 'stream-label',
                fill: this._getLabelColor(chain),
                'font-size': fontSize,
            });
            text.textContent = label;
            g.appendChild(text);
        }

        this.svg.appendChild(g);
    }

    _drawTimeAxis(plotW, plotH) {
        const g = this._svgEl('g', { class: 'stream-time-axis' });
        const n = this._tabularData.length;
        const axisY = this.height - 6;
        const textColor = this._getSecondaryTextColor();

        // Pick ~6-8 tick positions
        const targetTicks = Math.min(8, n);
        const step = Math.max(1, Math.floor(n / targetTicks));

        for (let i = 0; i < n; i += step) {
            const x = this._xScale(i);
            const dateStr = this._tabularData[i].date;
            const label = this._formatDateLabel(dateStr);

            const text = this._svgEl('text', {
                x: x,
                y: axisY,
                'text-anchor': 'middle',
                class: 'stream-axis-label',
                fill: textColor,
                'font-size': '10',
            });
            text.textContent = label;
            g.appendChild(text);
        }

        // Always show last date
        if (n > 1 && (n - 1) % step !== 0) {
            const x = this._xScale(n - 1);
            const label = this._formatDateLabel(this._tabularData[n - 1].date);
            const text = this._svgEl('text', {
                x: x,
                y: axisY,
                'text-anchor': 'end',
                class: 'stream-axis-label',
                fill: textColor,
                'font-size': '10',
            });
            text.textContent = label;
            g.appendChild(text);
        }

        this.svg.appendChild(g);
    }

    _drawCrosshairLine(plotH) {
        // Vertical crosshair line (hidden by default, shown on hover)
        this.crosshair = this._svgEl('line', {
            x1: 0, y1: this.padding.top,
            x2: 0, y2: this.padding.top + plotH,
            class: 'stream-crosshair',
            stroke: this._getSecondaryTextColor(),
            'stroke-width': '1',
            'stroke-dasharray': '4,3',
            opacity: '0',
        });
        this.svg.appendChild(this.crosshair);
    }

    // ===========================
    // Interactions
    // ===========================

    _onStreamHover(e, chain) {
        if (this.lockedChain) return; // locked state takes priority
        this.hoveredChain = chain;
        this._updateStreamOpacities();
        this._showTooltip(e, chain);
        this._showCrosshair(e);
    }

    _onStreamMove(e, chain) {
        const activeChain = this.lockedChain || this.hoveredChain;
        if (activeChain) {
            this._showTooltip(e, activeChain);
            this._showCrosshair(e);
        }
    }

    _onStreamLeave() {
        if (this.lockedChain) return;
        this.hoveredChain = null;
        this._updateStreamOpacities();
        this.tooltip.style.display = 'none';
        if (this.crosshair) this.crosshair.setAttribute('opacity', '0');
    }

    _onStreamClick(chain) {
        if (this.lockedChain === chain) {
            this.lockedChain = null;
            this.hoveredChain = null;
        } else {
            this.lockedChain = chain;
        }
        this._updateStreamOpacities();
        if (!this.lockedChain) {
            this.tooltip.style.display = 'none';
            if (this.crosshair) this.crosshair.setAttribute('opacity', '0');
        }
    }

    _updateStreamOpacities() {
        const active = this.lockedChain || this.hoveredChain;
        this.svg.querySelectorAll('.stream-path').forEach(path => {
            const c = path.getAttribute('data-chain');
            if (!active) {
                path.setAttribute('fill-opacity', '0.85');
                path.setAttribute('stroke', 'none');
                path.setAttribute('stroke-width', '0');
            } else if (c === active) {
                path.setAttribute('fill-opacity', '0.9');
                path.setAttribute('stroke', this._getAccentColor());
                path.setAttribute('stroke-width', '1.5');
            } else {
                path.setAttribute('fill-opacity', '0.15');
                path.setAttribute('stroke', 'none');
                path.setAttribute('stroke-width', '0');
            }
        });
    }

    _showTooltip(e, chain) {
        // Find nearest data index from mouse X
        const containerRect = this.container.getBoundingClientRect();
        const mouseX = e.clientX - containerRect.left;
        const n = this._tabularData.length;
        const plotW = this.width - this.padding.left - this.padding.right;

        let idx = Math.round(((mouseX - this.padding.left) / plotW) * (n - 1));
        idx = Math.max(0, Math.min(n - 1, idx));

        const row = this._tabularData[idx];
        const value = row[chain] || 0;

        // Compute total at this date
        let total = 0;
        for (const c of this.chains) total += (row[c] || 0);

        const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
        const dateLabel = this._formatDateFull(row.date);
        const chainLabel = this._chainLabel(chain);

        this.tooltip.innerHTML =
            `<strong>${this._escapeHTML(chainLabel)}</strong><br>` +
            `${this._formatUSD(value)} (${pct}%)<br>` +
            `<span style="opacity:0.6">${dateLabel}</span>`;
        this.tooltip.style.display = 'block';

        // Position tooltip
        let x = e.clientX - containerRect.left + 14;
        let y = e.clientY - containerRect.top - 10;
        const tw = this.tooltip.offsetWidth || 160;
        if (x + tw > containerRect.width) x = x - tw - 28;
        if (y < 0) y = 10;
        this.tooltip.style.left = x + 'px';
        this.tooltip.style.top = y + 'px';
    }

    _showCrosshair(e) {
        if (!this.crosshair) return;
        const containerRect = this.container.getBoundingClientRect();
        const mouseX = e.clientX - containerRect.left;
        this.crosshair.setAttribute('x1', mouseX);
        this.crosshair.setAttribute('x2', mouseX);
        this.crosshair.setAttribute('opacity', '0.4');
    }

    _showEmpty(msg) {
        const section = this.container.closest('#portfolioStreamSection');
        if (section) section.classList.remove('hidden');
        while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
        const rect = this.container.getBoundingClientRect();
        this.svg.setAttribute('viewBox', `0 0 ${rect.width || 600} ${rect.height || 420}`);
        const text = this._svgEl('text', {
            x: (rect.width || 600) / 2,
            y: (rect.height || 420) / 2,
            'text-anchor': 'middle',
            'dominant-baseline': 'central',
            fill: this._getSecondaryTextColor(),
            'font-size': '14',
        });
        text.textContent = msg;
        this.svg.appendChild(text);
    }

    // ===========================
    // Theme & Color Helpers
    // ===========================

    _getTheme() {
        return document.documentElement.getAttribute('data-theme') || 'dark-mode';
    }

    _getAccentColor() {
        const theme = this._getTheme();
        if (theme === 'light') return '#00b894';
        if (theme === 'cypherpunk1') return '#00d4ff';
        if (theme === 'ocean-depths') return '#00d2ff';
        if (theme === 'sunset-horizon') return '#ff6b6b';
        return '#00d26a';
    }

    _getSecondaryTextColor() {
        return this._getTheme() === 'light' ? '#6b7280' : '#a0a0a0';
    }

    _getStreamColor(chain) {
        if (chain === '_other') return '#666666';
        if (chain === 'exchanges') return '#f0b429';  // gold
        if (chain === 'nfts') return '#a855f7';       // purple
        if (chain === 'other') return '#666666';
        // Use the global CHAIN_COLORS if available, otherwise Sankey configs
        if (typeof CHAIN_COLORS !== 'undefined' && CHAIN_COLORS[chain]) {
            return CHAIN_COLORS[chain];
        }
        if (typeof SANKEY_CHAIN_CONFIGS !== 'undefined') {
            const cfg = SANKEY_CHAIN_CONFIGS.find(c => c.key === chain);
            if (cfg) return cfg.color;
        }
        // Deterministic fallback
        let hash = 0;
        for (let i = 0; i < chain.length; i++) hash = chain.charCodeAt(i) + ((hash << 5) - hash);
        return '#' + (Math.abs(hash) % 0xFFFFFF).toString(16).padStart(6, '0');
    }

    _getLabelColor(chain) {
        const color = this._getStreamColor(chain);
        const [r, g, b] = this._hexToRgb(color);
        const brightness = r * 0.299 + g * 0.587 + b * 0.114;
        // For dark streams, use white label; for bright streams, use dark label
        return brightness > 150 ? '#1a1a2e' : '#ffffff';
    }

    _hexToRgb(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        return [
            parseInt(hex.slice(0, 2), 16),
            parseInt(hex.slice(2, 4), 16),
            parseInt(hex.slice(4, 6), 16)
        ];
    }

    // ===========================
    // Formatting Utilities
    // ===========================

    _chainLabel(chain) {
        if (chain === '_other') return 'Other';
        if (chain === 'exchanges') return 'Exchanges';
        if (chain === 'nfts') return 'NFTs';
        if (chain === 'other') return 'Other';
        // Try Sankey configs for proper labels
        if (typeof SANKEY_CHAIN_CONFIGS !== 'undefined') {
            const cfg = SANKEY_CHAIN_CONFIGS.find(c => c.key === chain);
            if (cfg) return cfg.label;
        }
        return chain.charAt(0).toUpperCase() + chain.slice(1);
    }

    _formatUSD(value) {
        if (value >= 1000000) return '$' + (value / 1000000).toFixed(1) + 'M';
        if (value >= 1000) return '$' + (value / 1000).toFixed(1) + 'K';
        return '$' + value.toFixed(2);
    }

    _formatDateLabel(dateStr) {
        // Short label for axis ticks
        if (dateStr.includes('T')) {
            const date = new Date(dateStr);
            return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        const date = new Date(dateStr + 'T12:00:00');
        const range = this.activeRange;
        if (range === '1w' || range === '1m') {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
        if (range === '3m') {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
        if (range === '6m') {
            return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
        }
        // 1y, all — month + year
        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    }

    _formatDateFull(dateStr) {
        if (dateStr.includes('T')) {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }) +
                   ' ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        const date = new Date(dateStr + 'T12:00:00');
        return date.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' });
    }

    _escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    _svgEl(tag, attrs = {}) {
        const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
        return el;
    }
}
