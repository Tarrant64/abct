// ===========================
// Portfolio Flow Sankey Diagram
// ===========================
// Custom SVG-based Sankey chart for visualizing portfolio value flow
// Total Portfolio → Chains → Asset Categories (on drill-down)

const SANKEY_CATEGORY_COLORS = {
    'Native':        null, // uses chain color
    'DeFi':          '#00b894',
    'Stablecoins':   '#0984e3',
    'DePIN':         '#6c5ce7',
    'NFTs':          '#e17055',
    'Other Tokens':  '#fdcb6e'
};

const SANKEY_STABLECOINS = new Set([
    'USDC', 'USDT', 'DAI', 'DJED', 'iUSD', 'USDM', 'BUSD', 'FRAX', 'TUSD', 'SHEN',
    'USDD', 'PYUSD', 'LUSD', 'GUSD', 'RAI', 'SUSD', 'CRVUSD', 'GHO', 'DOLA'
]);

const SANKEY_DEPIN_TOKENS = new Set([
    'IAG', 'HNT', 'MOBILE', 'IOT', 'FIL', 'AR', 'RNDR', 'THETA', 'TFUEL', 'ANKR',
    'LPT', 'GRT', 'NOS'
]);

const SANKEY_DEFI_TOKENS = new Set([
    'INDY', 'MIN', 'SUNDAE', 'LQ', 'LENFI', 'WRT', 'STRIKE', 'OPTIM', 'SPF', 'VYFI',
    'AAVE', 'UNI', 'SUSHI', 'COMP', 'MKR', 'CRV', 'SNX', 'YFI', 'BAL', '1INCH',
    'AGIX', 'JPGD', 'LIQD', 'RAY', 'SRM', 'ORCA', 'JUP', 'MNGO', 'CAKE', 'JOE',
    'GMX', 'DYDX', 'PENDLE', 'MORPHO', 'EIGEN'
]);

class PortfolioSankey {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        this.svg = null;
        this.tooltip = null;
        this.totalValue = 0;
        this.chainAllocations = [];
        this.expandedChain = null;
        this.categoryData = null;
        this.width = 0;
        this.height = 0;
        this.animating = false;

        // Layout config
        this.padding = { top: 20, right: 140, bottom: 20, left: 140 };
        this.nodeWidth = 20;
        this.nodeGap = 5;
        this.minNodeHeight = 16;
        this.columnGap = 0; // computed from width

        this._createSVG();
        this._createTooltip();
        this._setupResizeObserver();
    }

    _createSVG() {
        this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svg.setAttribute('class', 'sankey-svg');
        this.svg.setAttribute('width', '100%');
        this.svg.setAttribute('height', '100%');
        this.container.appendChild(this.svg);
    }

    _createTooltip() {
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'sankey-tooltip';
        this.tooltip.style.display = 'none';
        this.container.appendChild(this.tooltip);
    }

    _setupResizeObserver() {
        this._resizeObserver = new ResizeObserver(() => {
            if (!this.animating) this.render();
        });
        this._resizeObserver.observe(this.container);
    }

    setData(totalValue, chainAllocations) {
        this.totalValue = totalValue;
        this.chainAllocations = chainAllocations;
        // Reset drill-down on data change
        this.expandedChain = null;
        this.categoryData = null;
    }

    render() {
        if (!this.container || !this.svg) return;
        if (!this.chainAllocations || this.chainAllocations.length === 0) {
            this.container.closest('#portfolioFlowSection')?.classList.add('hidden');
            return;
        }
        this.container.closest('#portfolioFlowSection')?.classList.remove('hidden');

        const rect = this.container.getBoundingClientRect();
        this.width = rect.width;
        this.height = Math.max(300, rect.height);

        // Responsive padding — tighten on narrow screens
        if (this.width < 500) {
            this.padding.left = 70;
            this.padding.right = 70;
        } else if (this.width < 768) {
            this.padding.left = 100;
            this.padding.right = 100;
        } else {
            this.padding.left = 140;
            this.padding.right = 140;
        }

        // Clear
        while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
        this.svg.setAttribute('viewBox', `0 0 ${this.width} ${this.height}`);

        const columns = this._buildColumns();
        const layout = this._computeLayout(columns);
        this._drawLinks(layout);
        this._drawNodes(layout);
    }

    // Build column data: [totalCol, chainsCol, (categoriesCol)]
    _buildColumns() {
        // Group small chains into "Other"
        const threshold = this.totalValue * 0.02;
        const mainChains = [];
        let otherValue = 0;
        let otherChains = [];

        for (const alloc of this.chainAllocations) {
            if (alloc.usd < threshold && this.chainAllocations.length > 10) {
                otherValue += alloc.usd;
                otherChains.push(alloc.label);
            } else {
                mainChains.push(alloc);
            }
        }

        // Column 0: Total portfolio
        const col0 = [{
            id: 'total',
            label: 'Total Portfolio',
            value: this.totalValue,
            color: this._getAccentColor(),
            type: 'total'
        }];

        // Column 1: Chains
        const col1 = mainChains.map(a => ({
            id: `chain-${a.chain}`,
            chain: a.chain,
            label: a.label,
            value: a.usd,
            color: a.color,
            type: 'chain'
        }));

        if (otherValue > 0) {
            col1.push({
                id: 'chain-other',
                chain: 'other',
                label: `Other (${otherChains.length})`,
                value: otherValue,
                color: '#666',
                type: 'chain'
            });
        }

        // Links: Total → each chain
        const links01 = col1.map(node => ({
            source: 'total',
            target: node.id,
            value: node.value,
            color: node.color
        }));

        const columns = [
            { nodes: col0, x: 0 },
            { nodes: col1, x: 0 }
        ];
        let links = links01;

        // Column 2: Categories (if drill-down active)
        if (this.expandedChain && this.categoryData) {
            const col2 = [];
            const links12 = [];
            const chainNodeId = `chain-${this.expandedChain}`;

            for (const [category, value] of Object.entries(this.categoryData)) {
                if (value <= 0) continue;
                const chainNode = col1.find(n => n.id === chainNodeId);
                const catColor = SANKEY_CATEGORY_COLORS[category] || (chainNode ? chainNode.color : '#888');
                const nodeId = `cat-${category}`;
                col2.push({
                    id: nodeId,
                    label: category,
                    value: value,
                    color: category === 'Native' ? (chainNode ? chainNode.color : '#888') : catColor,
                    type: 'category'
                });
                links12.push({
                    source: chainNodeId,
                    target: nodeId,
                    value: value,
                    color: category === 'Native' ? (chainNode ? chainNode.color : '#888') : catColor
                });
            }

            if (col2.length > 0) {
                columns.push({ nodes: col2, x: 0 });
                links = links.concat(links12);
            }
        }

        return { columns, links };
    }

    _computeLayout({ columns, links }) {
        const numCols = columns.length;
        const usableW = this.width - this.padding.left - this.padding.right - this.nodeWidth * numCols;
        this.columnGap = numCols > 1 ? usableW / (numCols - 1) : 0;

        const usableH = this.height - this.padding.top - this.padding.bottom;

        // Position each column
        const nodeMap = {};
        for (let ci = 0; ci < numCols; ci++) {
            const col = columns[ci];
            const colTotal = col.nodes.reduce((s, n) => s + n.value, 0);
            const totalGaps = (col.nodes.length - 1) * this.nodeGap;
            const availH = usableH - totalGaps;

            let y = this.padding.top;
            const x = this.padding.left + ci * (this.nodeWidth + this.columnGap);

            for (const node of col.nodes) {
                const proportion = colTotal > 0 ? node.value / colTotal : 0;
                let h = Math.max(this.minNodeHeight, proportion * availH);
                node.x = x;
                node.y = y;
                node.w = this.nodeWidth;
                node.h = h;
                nodeMap[node.id] = node;
                y += h + this.nodeGap;
            }

            // Adjust if overflow: scale down
            const totalH = y - this.nodeGap - this.padding.top;
            if (totalH > usableH) {
                const scale = usableH / totalH;
                let yy = this.padding.top;
                for (const node of col.nodes) {
                    node.y = yy;
                    node.h = Math.max(this.minNodeHeight, node.h * scale);
                    yy += node.h + this.nodeGap;
                }
            }
        }

        // Compute link positions using node source/target port tracking
        // Track how much of each node's height has been allocated to links
        const sourcePortY = {};
        const targetPortY = {};

        const resolvedLinks = links.map(link => {
            const src = nodeMap[link.source];
            const tgt = nodeMap[link.target];
            if (!src || !tgt) return null;

            // Source: allocate band proportional to link value
            if (!sourcePortY[link.source]) sourcePortY[link.source] = src.y;
            const srcBand = src.h * (link.value / (src.value || 1));
            const sy = sourcePortY[link.source];
            sourcePortY[link.source] += srcBand;

            // Target: allocate band proportional to link value
            if (!targetPortY[link.target]) targetPortY[link.target] = tgt.y;
            const tgtBand = tgt.h * (link.value / (tgt.value || 1));
            const ty = targetPortY[link.target];
            targetPortY[link.target] += tgtBand;

            return {
                ...link,
                x0: src.x + src.w,
                y0: sy,
                h0: srcBand,
                x1: tgt.x,
                y1: ty,
                h1: tgtBand
            };
        }).filter(Boolean);

        return { columns, links: resolvedLinks, nodeMap };
    }

    _drawLinks(layout) {
        const g = this._svgEl('g', { class: 'sankey-links' });

        for (const link of layout.links) {
            const midX = (link.x0 + link.x1) / 2;
            // Band path using cubic Bezier
            const d = [
                `M ${link.x0},${link.y0}`,
                `C ${midX},${link.y0} ${midX},${link.y1} ${link.x1},${link.y1}`,
                `L ${link.x1},${link.y1 + link.h1}`,
                `C ${midX},${link.y1 + link.h1} ${midX},${link.y0 + link.h0} ${link.x0},${link.y0 + link.h0}`,
                'Z'
            ].join(' ');

            const path = this._svgEl('path', {
                d,
                class: 'sankey-link',
                fill: link.color,
                'fill-opacity': '0.18',
                stroke: 'none',
                'data-source': link.source,
                'data-target': link.target
            });

            path.addEventListener('mouseenter', (e) => this._onLinkHover(e, link, layout));
            path.addEventListener('mouseleave', () => this._onLinkLeave(layout));
            path.addEventListener('mousemove', (e) => this._moveTooltip(e));

            g.appendChild(path);
        }
        this.svg.appendChild(g);
    }

    _drawNodes(layout) {
        const gNodes = this._svgEl('g', { class: 'sankey-nodes' });
        const gLabels = this._svgEl('g', { class: 'sankey-labels' });

        for (const col of layout.columns) {
            for (const node of col.nodes) {
                // Node rect
                const rect = this._svgEl('rect', {
                    x: node.x,
                    y: node.y,
                    width: node.w,
                    height: node.h,
                    rx: 4,
                    ry: 4,
                    fill: node.color,
                    class: 'sankey-node',
                    'data-id': node.id
                });

                // Dim non-expanded chains when drilled down
                if (this.expandedChain && node.type === 'chain' && node.chain !== this.expandedChain) {
                    rect.setAttribute('opacity', '0.35');
                }

                if (node.type === 'chain' && node.chain !== 'other') {
                    rect.style.cursor = 'pointer';
                    rect.addEventListener('click', () => this._onChainClick(node));
                }

                rect.addEventListener('mouseenter', (e) => this._onNodeHover(e, node, layout));
                rect.addEventListener('mouseleave', () => this._onNodeLeave(layout));
                rect.addEventListener('mousemove', (e) => this._moveTooltip(e));

                gNodes.appendChild(rect);

                // Label
                this._drawLabel(gLabels, node, layout.columns.length);
            }
        }

        this.svg.appendChild(gNodes);
        this.svg.appendChild(gLabels);
    }

    _drawLabel(g, node, numCols) {
        const isMobile = this.width < 480;
        const isSmall = this.width < 768;

        // For small screens, skip value labels on tiny nodes
        if (isMobile && node.h < 25) return;

        const fontSize = isSmall ? 10 : 12;
        const valueFontSize = isSmall ? 9 : 11;

        // Position label to the right of node for cols 0-1, left of node for last col
        const isLastCol = node.type === 'category';
        const isFirstCol = node.type === 'total';
        let textX, anchor;

        if (isFirstCol) {
            textX = node.x - 8;
            anchor = 'end';
        } else if (isLastCol) {
            textX = node.x + node.w + 8;
            anchor = 'start';
        } else {
            // Chain column: label to right if 2 cols, left if 3 cols (drill-down)
            if (numCols > 2) {
                textX = node.x - 8;
                anchor = 'end';
            } else {
                textX = node.x + node.w + 8;
                anchor = 'start';
            }
        }

        const textY = node.y + node.h / 2;

        // Name label
        let labelText = node.label;
        if (isSmall && labelText.length > 12) {
            labelText = labelText.substring(0, 10) + '…';
        }

        const nameEl = this._svgEl('text', {
            x: textX,
            y: textY - (node.h > 30 ? 4 : 0),
            'text-anchor': anchor,
            'dominant-baseline': node.h > 30 ? 'auto' : 'central',
            class: 'sankey-label-name',
            'font-size': fontSize,
            fill: this._getTextColor()
        });
        nameEl.textContent = labelText;

        // Dim labels for non-expanded chains
        if (this.expandedChain && node.type === 'chain' && node.chain !== this.expandedChain) {
            nameEl.setAttribute('opacity', '0.35');
        }

        g.appendChild(nameEl);

        // Value label (only if node tall enough)
        if (node.h > 30 && !isMobile) {
            const valEl = this._svgEl('text', {
                x: textX,
                y: textY + fontSize - 2,
                'text-anchor': anchor,
                'dominant-baseline': 'auto',
                class: 'sankey-label-value',
                'font-size': valueFontSize,
                fill: this._getSecondaryTextColor()
            });
            valEl.textContent = this._formatCompactUSD(node.value);

            if (this.expandedChain && node.type === 'chain' && node.chain !== this.expandedChain) {
                valEl.setAttribute('opacity', '0.35');
            }

            g.appendChild(valEl);
        }
    }

    // ===========================
    // Interactions
    // ===========================

    async _onChainClick(node) {
        if (this.animating) return;

        if (this.expandedChain === node.chain) {
            // Collapse
            this.expandedChain = null;
            this.categoryData = null;
            this.render();
            return;
        }

        // Expand: fetch category data
        this.expandedChain = node.chain;
        this.categoryData = null;

        // Show loading state on the node
        const nodeEl = this.svg.querySelector(`[data-id="chain-${node.chain}"]`);
        if (nodeEl) nodeEl.classList.add('sankey-node-loading');

        try {
            const data = await this._fetchCategoryData(node.chain);
            this.categoryData = data;
        } catch (e) {
            console.warn('[Sankey] Failed to fetch category data:', e);
            this.expandedChain = null;
        }

        if (nodeEl) nodeEl.classList.remove('sankey-node-loading');
        this.render();
    }

    async _fetchCategoryData(chain) {
        // Check assetBreakdownCache first (global from app.js)
        if (typeof assetBreakdownCache !== 'undefined') {
            const cached = assetBreakdownCache.get(chain, 'data');
            if (cached && !assetBreakdownCache.isStale(chain, 'data')) {
                return this._categorizeAssets(cached, chain);
            }
        }

        // Fetch from API
        const resp = await authFetch(`${API_BASE}/portfolio/assets/${chain}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // Cache it
        if (typeof assetBreakdownCache !== 'undefined') {
            assetBreakdownCache.set(chain, data, 'data');
        }

        return this._categorizeAssets(data, chain);
    }

    _categorizeAssets(data, chain) {
        const categories = {};
        const nativeSymbol = this._getNativeSymbol(chain);

        // Native coin
        if (data.native_coin && data.native_coin.value_usd > 0) {
            categories['Native'] = (categories['Native'] || 0) + data.native_coin.value_usd;
        }

        // Tokens
        if (data.tokens) {
            for (const token of data.tokens) {
                if (!token.value_usd || token.value_usd <= 0) continue;
                const sym = (token.symbol || '').toUpperCase();

                if (sym === nativeSymbol) {
                    categories['Native'] = (categories['Native'] || 0) + token.value_usd;
                } else if (SANKEY_STABLECOINS.has(sym)) {
                    categories['Stablecoins'] = (categories['Stablecoins'] || 0) + token.value_usd;
                } else if (SANKEY_DEPIN_TOKENS.has(sym)) {
                    categories['DePIN'] = (categories['DePIN'] || 0) + token.value_usd;
                } else if (SANKEY_DEFI_TOKENS.has(sym)) {
                    categories['DeFi'] = (categories['DeFi'] || 0) + token.value_usd;
                } else {
                    categories['Other Tokens'] = (categories['Other Tokens'] || 0) + token.value_usd;
                }
            }
        }

        // NFTs
        if (data.nfts && data.nfts.value_usd > 0) {
            categories['NFTs'] = data.nfts.value_usd;
        }

        return categories;
    }

    _getNativeSymbol(chain) {
        const map = {
            cardano: 'ADA', bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL',
            polygon: 'POL', base: 'ETH', algorand: 'ALGO', bsc: 'BNB',
            arbitrum: 'ETH', avalanche: 'AVAX', tron: 'TRX', xrp: 'XRP',
            hedera: 'HBAR', multiversx: 'EGLD', sui: 'SUI', aptos: 'APT',
            filecoin: 'FIL', litecoin: 'LTC', dogecoin: 'DOGE', zcash: 'ZEC',
            tezos: 'XTZ', stacks: 'STX', vechain: 'VET', cosmos: 'ATOM',
            near: 'NEAR', icp: 'ICP'
        };
        return map[chain] || '';
    }

    _onNodeHover(e, node, layout) {
        // Highlight connected links
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => {
            const src = el.getAttribute('data-source');
            const tgt = el.getAttribute('data-target');
            if (src === node.id || tgt === node.id) {
                el.setAttribute('fill-opacity', '0.4');
            } else {
                el.setAttribute('fill-opacity', '0.08');
            }
        });

        // Tooltip
        const pct = this.totalValue > 0 ? ((node.value / this.totalValue) * 100).toFixed(1) : '0';
        this.tooltip.innerHTML = `<strong>${this._escapeHTML(node.label)}</strong><br>${this._formatCompactUSD(node.value)} (${pct}%)`;
        this.tooltip.style.display = 'block';
        this._moveTooltip(e);
    }

    _onNodeLeave(layout) {
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => el.setAttribute('fill-opacity', '0.18'));
        this.tooltip.style.display = 'none';
    }

    _onLinkHover(e, link, layout) {
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => {
            if (el.getAttribute('data-source') === link.source && el.getAttribute('data-target') === link.target) {
                el.setAttribute('fill-opacity', '0.4');
            } else {
                el.setAttribute('fill-opacity', '0.08');
            }
        });

        const pct = this.totalValue > 0 ? ((link.value / this.totalValue) * 100).toFixed(1) : '0';
        const srcNode = layout.nodeMap[link.source];
        const tgtNode = layout.nodeMap[link.target];
        this.tooltip.innerHTML = `<strong>${this._escapeHTML(srcNode?.label || '')} → ${this._escapeHTML(tgtNode?.label || '')}</strong><br>${this._formatCompactUSD(link.value)} (${pct}%)`;
        this.tooltip.style.display = 'block';
        this._moveTooltip(e);
    }

    _onLinkLeave(layout) {
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => el.setAttribute('fill-opacity', '0.18'));
        this.tooltip.style.display = 'none';
    }

    _moveTooltip(e) {
        const containerRect = this.container.getBoundingClientRect();
        let x = e.clientX - containerRect.left + 12;
        let y = e.clientY - containerRect.top - 10;

        // Keep tooltip within container
        const tw = this.tooltip.offsetWidth || 150;
        if (x + tw > containerRect.width) x = x - tw - 24;
        if (y < 0) y = 10;

        this.tooltip.style.left = x + 'px';
        this.tooltip.style.top = y + 'px';
    }

    // ===========================
    // Theme helpers
    // ===========================

    updateTheme() {
        this.render();
    }

    _getTheme() {
        return document.documentElement.getAttribute('data-theme') || 'dark-mode';
    }

    _getAccentColor() {
        const theme = this._getTheme();
        if (theme === 'light') return '#00b894';
        if (theme === 'cypherpunk1') return '#0abdc6';
        if (theme === 'ocean-depths') return '#00d2ff';
        if (theme === 'sunset-horizon') return '#ff6b6b';
        return '#00d26a'; // dark-mode default
    }

    _getTextColor() {
        const theme = this._getTheme();
        return theme === 'light' ? '#1a1a2e' : '#eaeaea';
    }

    _getSecondaryTextColor() {
        const theme = this._getTheme();
        return theme === 'light' ? '#6b7280' : '#a0a0a0';
    }

    // ===========================
    // Utility
    // ===========================

    _svgEl(tag, attrs = {}) {
        const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
        for (const [k, v] of Object.entries(attrs)) {
            el.setAttribute(k, v);
        }
        return el;
    }

    _formatCompactUSD(value) {
        if (value >= 1000000) return '$' + (value / 1000000).toFixed(1) + 'M';
        if (value >= 1000) return '$' + (value / 1000).toFixed(1) + 'K';
        return '$' + value.toFixed(2);
    }

    _escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    destroy() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this.tooltip && this.tooltip.parentNode) {
            this.tooltip.parentNode.removeChild(this.tooltip);
        }
        if (this.svg && this.svg.parentNode) {
            this.svg.parentNode.removeChild(this.svg);
        }
        this.svg = null;
        this.tooltip = null;
    }
}
