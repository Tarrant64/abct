// ===========================
// Portfolio Flow Sankey Diagram
// ===========================
// Custom SVG-based 3-column Sankey: Total Portfolio → Chains → Wallets
// Click a chain to highlight its wallet flows

const SANKEY_CHAIN_CONFIGS = [
    { key: 'cardano',    label: 'Cardano',    color: '#0033ad', priceKey: 'ADA',   useStakeGroups: true },
    { key: 'bitcoin',    label: 'Bitcoin',    color: '#f7931a', priceKey: 'BTC'   },
    { key: 'ethereum',   label: 'Ethereum',   color: '#627eea', priceKey: 'ETH'   },
    { key: 'solana',     label: 'Solana',     color: '#9945ff', priceKey: 'SOL'   },
    { key: 'polygon',    label: 'Polygon',    color: '#8247e5', priceKey: 'MATIC' },
    { key: 'base',       label: 'Base',       color: '#0052ff', priceKey: 'ETH'   },
    { key: 'algorand',   label: 'Algorand',   color: '#00d2c2', priceKey: 'ALGO'  },
    { key: 'bsc',        label: 'BNB Chain',  color: '#f3ba2f', priceKey: 'BNB'   },
    { key: 'arbitrum',   label: 'Arbitrum',   color: '#28a0f0', priceKey: 'ETH'   },
    { key: 'avalanche',  label: 'Avalanche',  color: '#e84142', priceKey: 'AVAX'  },
    { key: 'tron',       label: 'Tron',       color: '#ff0013', priceKey: 'TRX'   },
    { key: 'xrp',        label: 'XRP Ledger', color: '#23292f', priceKey: 'XRP'   },
    { key: 'hedera',     label: 'Hedera',     color: '#3d3d3d', priceKey: 'HBAR'  },
    { key: 'multiversx', label: 'MultiversX', color: '#23f7dd', priceKey: 'EGLD'  },
    { key: 'sui',        label: 'Sui',        color: '#4da2ff', priceKey: 'SUI'   },
    { key: 'aptos',      label: 'Aptos',      color: '#2ed8a3', priceKey: 'APT'   },
    { key: 'filecoin',   label: 'Filecoin',   color: '#0090ff', priceKey: 'FIL'   },
    { key: 'litecoin',   label: 'Litecoin',   color: '#345d9d', priceKey: 'LTC'   },
    { key: 'dogecoin',   label: 'Dogecoin',   color: '#c2a633', priceKey: 'DOGE'  },
    { key: 'zcash',      label: 'Zcash',      color: '#ecb244', priceKey: 'ZEC'   },
    { key: 'tezos',      label: 'Tezos',      color: '#2c7df7', priceKey: 'XTZ'   },
    { key: 'stacks',     label: 'Stacks',     color: '#5546ff', priceKey: 'STX'   },
    { key: 'vechain',    label: 'VeChain',    color: '#15bdff', priceKey: 'VET'   },
    { key: 'cosmos',     label: 'Cosmos',     color: '#2e3148', priceKey: 'ATOM'  },
    { key: 'near',       label: 'NEAR',       color: '#00c08b', priceKey: 'NEAR'  },
    { key: 'icp',        label: 'ICP',        color: '#29abe2', priceKey: 'ICP'   },
];

class PortfolioSankey {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;

        this.svg = null;
        this.tooltip = null;
        this.totalValue = 0;
        this.chainAllocations = [];
        this.walletsByChain = {}; // { chainKey: [{label, usd, address}] }
        this.highlightedChain = null;
        this.width = 0;
        this.height = 0;

        // Layout config
        this.padding = { top: 24, right: 140, bottom: 24, left: 140 };
        this.nodeWidth = 22;
        this.nodeGap = 6;
        this.minNodeHeight = 18;

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
        this._resizeObserver = new ResizeObserver(() => this.render());
        this._resizeObserver.observe(this.container);
    }

    /**
     * Set data for the 3-column Sankey.
     * @param {number} totalValue - Total portfolio USD value
     * @param {Array} chainAllocations - From getChainAllocations()
     * @param {object} portfolioData - lastPortfolioData (optional, for wallet data)
     * @param {object} priceData - global prices object (optional, for wallet USD calc)
     */
    setData(totalValue, chainAllocations, portfolioData, priceData) {
        this.totalValue = totalValue;
        this.chainAllocations = chainAllocations;
        this.highlightedChain = null;

        // Extract wallet-level data from portfolio summary
        this.walletsByChain = {};
        if (portfolioData && priceData) {
            this._extractWallets(portfolioData, priceData);
        }
    }

    _extractWallets(portfolioData, prices) {
        for (const cfg of SANKEY_CHAIN_CONFIGS) {
            const chainData = portfolioData[cfg.key];
            if (!chainData) continue;

            const price = prices[cfg.priceKey] || 0;
            const wallets = [];

            if (cfg.useStakeGroups) {
                // Cardano: use stake groups as wallet entries
                const groups = chainData.stake_groups || [];
                for (const group of groups) {
                    const usd = (group.total_ada || 0) * price + (group.native_assets_value_usd || 0);
                    if (usd > 0) {
                        wallets.push({
                            label: group.label || group.stake_address_short || 'Cardano Wallet',
                            usd,
                            address: group.stake_address || ''
                        });
                    }
                }
            } else {
                const chainWallets = chainData.wallets || [];
                for (const w of chainWallets) {
                    const usd = (w.balance || 0) * price + (w.native_assets_value_usd || 0);
                    if (usd > 0) {
                        wallets.push({
                            label: w.label || w.address_short || (cfg.label + ' Wallet'),
                            usd,
                            address: w.address || ''
                        });
                    }
                }
            }

            if (wallets.length > 0) {
                // Sort wallets within chain by value desc
                wallets.sort((a, b) => b.usd - a.usd);
                this.walletsByChain[cfg.key] = wallets;
            }
        }
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

        // Determine if we have wallet data (3 columns) or just chain data (2 columns)
        const totalWallets = Object.values(this.walletsByChain).reduce((s, w) => s + w.length, 0);
        this.hasWalletColumn = totalWallets >= 2;

        // Dynamic height: scale with the tallest column's node count
        const chainCount = this.chainAllocations.length;
        const baseHeight = rect.height || 480;
        let targetHeight = baseHeight;

        if (this.hasWalletColumn) {
            const walletHeightNeed = totalWallets * 30 + 60;
            const chainHeightNeed = chainCount * 40 + 60;
            targetHeight = Math.max(baseHeight, Math.max(walletHeightNeed, chainHeightNeed));
            targetHeight = Math.min(targetHeight, 900);
        }

        this.height = Math.max(300, targetHeight);
        this.container.style.height = this.height + 'px';

        // Responsive padding
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

        const data = this._buildColumns();
        const layout = this._computeLayout(data);
        this._drawLinks(layout);
        this._drawNodes(layout);
    }

    // ===========================
    // Data / Layout
    // ===========================

    _buildColumns() {
        // Group small chains into "Other" if many chains
        const threshold = this.totalValue * 0.015;
        const mainChains = [];
        let otherValue = 0;
        let otherChains = [];

        for (const alloc of this.chainAllocations) {
            if (alloc.usd < threshold && this.chainAllocations.length > 10) {
                otherValue += alloc.usd;
                otherChains.push(alloc);
            } else {
                mainChains.push(alloc);
            }
        }

        // Column 0: Total Portfolio
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

        // Links: Total → Chains
        const links = col1.map(node => ({
            source: 'total',
            target: node.id,
            value: node.value,
            color: node.color
        }));

        const columns = [
            { nodes: col0 },
            { nodes: col1 }
        ];

        // Column 2: Wallets (if wallet data available)
        if (this.hasWalletColumn) {
            const col2 = [];
            let walletIdx = 0;

            // Build wallet nodes in chain order (matching col1 order)
            for (const chainNode of col1) {
                const chainKey = chainNode.chain;
                const wallets = this.walletsByChain[chainKey] || [];

                for (const w of wallets) {
                    const walletId = `wallet-${chainKey}-${walletIdx++}`;
                    col2.push({
                        id: walletId,
                        label: w.label,
                        value: w.usd,
                        color: chainNode.color,
                        type: 'wallet',
                        chain: chainKey,
                        address: w.address
                    });

                    links.push({
                        source: chainNode.id,
                        target: walletId,
                        value: w.usd,
                        color: chainNode.color
                    });
                }
            }

            if (col2.length > 0) {
                columns.push({ nodes: col2 });
            }
        }

        return { columns, links };
    }

    _computeLayout({ columns, links }) {
        const numCols = columns.length;
        const usableW = this.width - this.padding.left - this.padding.right - this.nodeWidth * numCols;
        const columnGap = numCols > 1 ? usableW / (numCols - 1) : 0;

        const usableH = this.height - this.padding.top - this.padding.bottom;

        // Position each column
        const nodeMap = {};
        for (let ci = 0; ci < numCols; ci++) {
            const col = columns[ci];
            const colTotal = col.nodes.reduce((s, n) => s + n.value, 0);
            const totalGaps = (col.nodes.length - 1) * this.nodeGap;
            const availH = usableH - totalGaps;

            let y = this.padding.top;
            const x = this.padding.left + ci * (this.nodeWidth + columnGap);

            for (const node of col.nodes) {
                const proportion = colTotal > 0 ? node.value / colTotal : 0;
                node.h = Math.max(this.minNodeHeight, proportion * availH);
                node.x = x;
                node.y = y;
                node.w = this.nodeWidth;
                nodeMap[node.id] = node;
                y += node.h + this.nodeGap;
            }

            // Scale down if overflow
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

        // Resolve link positions using port tracking
        const sourcePortY = {};
        const targetPortY = {};

        const resolvedLinks = links.map(link => {
            const src = nodeMap[link.source];
            const tgt = nodeMap[link.target];
            if (!src || !tgt) return null;

            if (!sourcePortY[link.source]) sourcePortY[link.source] = src.y;
            const srcBand = src.h * (link.value / (src.value || 1));
            const sy = sourcePortY[link.source];
            sourcePortY[link.source] += srcBand;

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

    // ===========================
    // Drawing
    // ===========================

    _drawLinks(layout) {
        const g = this._svgEl('g', { class: 'sankey-links' });

        for (const link of layout.links) {
            const midX = (link.x0 + link.x1) / 2;
            const d = [
                `M ${link.x0},${link.y0}`,
                `C ${midX},${link.y0} ${midX},${link.y1} ${link.x1},${link.y1}`,
                `L ${link.x1},${link.y1 + link.h1}`,
                `C ${midX},${link.y1 + link.h1} ${midX},${link.y0 + link.h0} ${link.x0},${link.y0 + link.h0}`,
                'Z'
            ].join(' ');

            // Determine if this link should be dimmed (chain highlight active)
            let opacity = '0.18';
            if (this.highlightedChain) {
                const isChainLink = link.source === `chain-${this.highlightedChain}` ||
                                    link.target === `chain-${this.highlightedChain}`;
                // For Total→Chain links, highlight the selected chain
                const isTotalToHighlighted = link.source === 'total' && link.target === `chain-${this.highlightedChain}`;
                opacity = (isChainLink || isTotalToHighlighted) ? '0.35' : '0.05';
            }

            const path = this._svgEl('path', {
                d,
                class: 'sankey-link',
                fill: link.color,
                'fill-opacity': opacity,
                stroke: 'none',
                'data-source': link.source,
                'data-target': link.target
            });

            path.addEventListener('mouseenter', (e) => this._onLinkHover(e, link, layout));
            path.addEventListener('mouseleave', () => this._onLinkLeave());
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
                // Determine dim state
                let nodeOpacity = '1';
                if (this.highlightedChain) {
                    if (node.type === 'chain' && node.chain !== this.highlightedChain) {
                        nodeOpacity = '0.25';
                    } else if (node.type === 'wallet' && node.chain !== this.highlightedChain) {
                        nodeOpacity = '0.25';
                    }
                }

                const rect = this._svgEl('rect', {
                    x: node.x,
                    y: node.y,
                    width: node.w,
                    height: node.h,
                    rx: 4,
                    ry: 4,
                    fill: node.color,
                    class: 'sankey-node',
                    'data-id': node.id,
                    opacity: nodeOpacity
                });

                // Chain nodes are clickable for highlight toggle
                if (node.type === 'chain' && node.chain !== 'other') {
                    rect.style.cursor = 'pointer';
                    rect.addEventListener('click', () => this._onChainClick(node));
                }

                rect.addEventListener('mouseenter', (e) => this._onNodeHover(e, node, layout));
                rect.addEventListener('mouseleave', () => this._onNodeLeave());
                rect.addEventListener('mousemove', (e) => this._moveTooltip(e));

                gNodes.appendChild(rect);
                this._drawLabel(gLabels, node, layout.columns.length, nodeOpacity);
            }
        }

        this.svg.appendChild(gNodes);
        this.svg.appendChild(gLabels);
    }

    _drawLabel(g, node, numCols, nodeOpacity) {
        const isMobile = this.width < 480;
        const isSmall = this.width < 768;

        // Skip labels on tiny nodes on mobile
        if (isMobile && node.h < 22) return;

        const fontSize = isSmall ? 10 : 12;
        const valueFontSize = isSmall ? 9 : 11;

        // Label placement:
        // Total (col 0): LEFT of node
        // Chains (col 1): LEFT of node (space between Total and Chains)
        // Wallets (col 2): RIGHT of node
        let textX, anchor;

        if (node.type === 'total') {
            textX = node.x - 8;
            anchor = 'end';
        } else if (node.type === 'wallet') {
            textX = node.x + node.w + 8;
            anchor = 'start';
        } else {
            // Chain column: left side if 3 cols, right side if 2 cols
            if (numCols > 2) {
                textX = node.x - 8;
                anchor = 'end';
            } else {
                textX = node.x + node.w + 8;
                anchor = 'start';
            }
        }

        const textY = node.y + node.h / 2;

        // Truncate long labels on small screens
        let labelText = node.label;
        const maxLen = isSmall ? 12 : (node.type === 'wallet' ? 20 : 15);
        if (labelText.length > maxLen) {
            labelText = labelText.substring(0, maxLen - 1) + '…';
        }

        const nameEl = this._svgEl('text', {
            x: textX,
            y: textY - (node.h > 30 ? 4 : 0),
            'text-anchor': anchor,
            'dominant-baseline': node.h > 30 ? 'auto' : 'central',
            class: 'sankey-label-name',
            'font-size': fontSize,
            fill: this._getTextColor(),
            opacity: nodeOpacity
        });
        nameEl.textContent = labelText;
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
                fill: this._getSecondaryTextColor(),
                opacity: nodeOpacity
            });
            valEl.textContent = this._formatCompactUSD(node.value);
            g.appendChild(valEl);
        }
    }

    // ===========================
    // Interactions
    // ===========================

    _onChainClick(node) {
        if (this.highlightedChain === node.chain) {
            this.highlightedChain = null;
        } else {
            this.highlightedChain = node.chain;
        }
        this.render();
    }

    _onNodeHover(e, node, layout) {
        // Highlight connected links
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => {
            const src = el.getAttribute('data-source');
            const tgt = el.getAttribute('data-target');
            if (src === node.id || tgt === node.id) {
                el.setAttribute('fill-opacity', '0.4');
            } else if (!this.highlightedChain) {
                el.setAttribute('fill-opacity', '0.06');
            }
        });

        // Tooltip
        const pct = this.totalValue > 0 ? ((node.value / this.totalValue) * 100).toFixed(1) : '0';
        let tooltipHtml = `<strong>${this._escapeHTML(node.label)}</strong><br>${this._formatCompactUSD(node.value)} (${pct}%)`;

        // For chain nodes, show wallet count
        if (node.type === 'chain' && this.walletsByChain[node.chain]) {
            const wCount = this.walletsByChain[node.chain].length;
            tooltipHtml += `<br><span style="opacity:0.7">${wCount} wallet${wCount !== 1 ? 's' : ''}</span>`;
        }

        this.tooltip.innerHTML = tooltipHtml;
        this.tooltip.style.display = 'block';
        this._moveTooltip(e);
    }

    _onNodeLeave() {
        // Restore link opacities based on highlight state
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        if (this.highlightedChain) {
            linkEls.forEach(el => {
                const src = el.getAttribute('data-source');
                const tgt = el.getAttribute('data-target');
                const isHighlighted = src === `chain-${this.highlightedChain}` ||
                                      tgt === `chain-${this.highlightedChain}` ||
                                      (src === 'total' && tgt === `chain-${this.highlightedChain}`);
                el.setAttribute('fill-opacity', isHighlighted ? '0.35' : '0.05');
            });
        } else {
            linkEls.forEach(el => el.setAttribute('fill-opacity', '0.18'));
        }
        this.tooltip.style.display = 'none';
    }

    _onLinkHover(e, link, layout) {
        const linkEls = this.svg.querySelectorAll('.sankey-link');
        linkEls.forEach(el => {
            if (el.getAttribute('data-source') === link.source && el.getAttribute('data-target') === link.target) {
                el.setAttribute('fill-opacity', '0.4');
            } else if (!this.highlightedChain) {
                el.setAttribute('fill-opacity', '0.06');
            }
        });

        const pct = this.totalValue > 0 ? ((link.value / this.totalValue) * 100).toFixed(1) : '0';
        const srcNode = layout.nodeMap[link.source];
        const tgtNode = layout.nodeMap[link.target];
        this.tooltip.innerHTML = `<strong>${this._escapeHTML(srcNode?.label || '')} → ${this._escapeHTML(tgtNode?.label || '')}</strong><br>${this._formatCompactUSD(link.value)} (${pct}%)`;
        this.tooltip.style.display = 'block';
        this._moveTooltip(e);
    }

    _onLinkLeave() {
        this._onNodeLeave(); // Same restore logic
    }

    _moveTooltip(e) {
        const containerRect = this.container.getBoundingClientRect();
        let x = e.clientX - containerRect.left + 12;
        let y = e.clientY - containerRect.top - 10;

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
        return this._getTheme() === 'light' ? '#1a1a2e' : '#eaeaea';
    }

    _getSecondaryTextColor() {
        return this._getTheme() === 'light' ? '#6b7280' : '#a0a0a0';
    }

    // ===========================
    // Utility
    // ===========================

    _svgEl(tag, attrs = {}) {
        const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
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
