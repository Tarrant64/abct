// ===========================
// Portfolio Flow Sankey Diagram
// ===========================
// Custom SVG-based Sankey: Total Portfolio → Chains → Wallets → [Categories]
// Click a chain to highlight its wallets, click a wallet to trace back and expand categories

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
        this.walletsByChain = {}; // { chainKey: [{label, usd, nativeCoinUsd, tokenUsd, nativeCoinSymbol, address}] }
        this.highlightedChain = null;
        this.highlightedWallet = null;  // specific wallet ID for reverse selection
        this.expandedWallet = null;     // wallet ID showing category breakdown
        this.width = 0;
        this.height = 0;

        // Layout config
        this.padding = { top: 24, right: 140, bottom: 24, left: 140 };
        this.nodeWidth = 22;
        this.nodeGap = 6;
        this.minNodeHeight = 18;
        this.compressionPower = 0.55; // Sublinear scaling to compress dominant chains

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

    setData(totalValue, chainAllocations, portfolioData, priceData) {
        this.totalValue = totalValue;
        this.chainAllocations = chainAllocations;
        this.highlightedChain = null;
        this.highlightedWallet = null;
        this.expandedWallet = null;

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
                const groups = chainData.stake_groups || [];
                for (const group of groups) {
                    const nativeCoinUsd = (group.total_ada || 0) * price;
                    const tokenUsd = group.native_assets_value_usd || 0;
                    const usd = nativeCoinUsd + tokenUsd;
                    if (usd > 0) {
                        wallets.push({
                            label: group.label || group.stake_address_short || 'Cardano Wallet',
                            usd,
                            nativeCoinUsd,
                            tokenUsd,
                            nativeCoinSymbol: cfg.priceKey,
                            address: group.stake_address || ''
                        });
                    }
                }
            } else {
                const chainWallets = chainData.wallets || [];
                for (const w of chainWallets) {
                    const nativeCoinUsd = (w.balance || 0) * price;
                    const tokenUsd = w.native_assets_value_usd || 0;
                    const usd = nativeCoinUsd + tokenUsd;
                    if (usd > 0) {
                        wallets.push({
                            label: w.label || w.address_short || (cfg.label + ' Wallet'),
                            usd,
                            nativeCoinUsd,
                            tokenUsd,
                            nativeCoinSymbol: cfg.priceKey,
                            address: w.address || ''
                        });
                    }
                }
            }

            if (wallets.length > 0) {
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

        const totalWallets = Object.values(this.walletsByChain).reduce((s, w) => s + w.length, 0);
        this.hasWalletColumn = totalWallets >= 2;

        // Dynamic height: fit content with compressed scaling
        const chainCount = this.chainAllocations.length;
        const baseHeight = rect.height || 480;
        let targetHeight = baseHeight;

        if (this.hasWalletColumn) {
            // With compressed scaling, nodes are more even — need less height per item
            const walletHeightNeed = totalWallets * 26 + 60;
            const chainHeightNeed = chainCount * 34 + 60;
            targetHeight = Math.max(baseHeight, Math.max(walletHeightNeed, chainHeightNeed));
            targetHeight = Math.min(targetHeight, 800);
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

        // Dynamic gaps/min height based on node count
        const maxColumnNodes = Math.max(chainCount, totalWallets);
        if (maxColumnNodes > 12) {
            this.nodeGap = 3;
            this.minNodeHeight = 12;
        } else if (maxColumnNodes > 8) {
            this.nodeGap = 4;
            this.minNodeHeight = 14;
        } else {
            this.nodeGap = 6;
            this.minNodeHeight = 18;
        }

        // Clear
        while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
        this.svg.setAttribute('viewBox', `0 0 ${this.width} ${this.height}`);

        const data = this._buildColumns();
        const layout = this._computeLayout(data);
        this._drawLinks(layout);
        this._drawNodes(layout);
        this._drawCategoryExpansion(layout);
    }

    // ===========================
    // Data / Layout
    // ===========================

    _buildColumns() {
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

        // Column 1: Chains (with themed colors)
        const col1 = mainChains.map(a => ({
            id: `chain-${a.chain}`,
            chain: a.chain,
            label: a.label,
            value: a.usd,
            color: this._getThemedNodeColor(a.color),
            baseColor: a.color,
            type: 'chain'
        }));

        if (otherValue > 0) {
            col1.push({
                id: 'chain-other',
                chain: 'other',
                label: `Other (${otherChains.length})`,
                value: otherValue,
                color: this._getThemedNodeColor('#666666'),
                baseColor: '#666666',
                type: 'chain'
            });
        }

        // Links: Total → Chains (themed link colors)
        const links = col1.map(node => ({
            source: 'total',
            target: node.id,
            value: node.value,
            color: this._getThemedLinkColor(node.baseColor || node.color)
        }));

        const columns = [
            { nodes: col0 },
            { nodes: col1 }
        ];

        // Column 2: Wallets
        if (this.hasWalletColumn) {
            const col2 = [];
            let walletIdx = 0;

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
                        baseColor: chainNode.baseColor || chainNode.color,
                        type: 'wallet',
                        chain: chainKey,
                        address: w.address,
                        nativeCoinUsd: w.nativeCoinUsd,
                        tokenUsd: w.tokenUsd,
                        nativeCoinSymbol: w.nativeCoinSymbol
                    });

                    links.push({
                        source: chainNode.id,
                        target: walletId,
                        value: w.usd,
                        color: this._getThemedLinkColor(chainNode.baseColor || chainNode.color)
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

        const nodeMap = {};
        for (let ci = 0; ci < numCols; ci++) {
            const col = columns[ci];
            const shouldCompress = col.nodes.length > 1;
            const totalGaps = (col.nodes.length - 1) * this.nodeGap;
            const availH = usableH - totalGaps;

            // Compute compressed proportions for multi-node columns
            let proportions;
            if (shouldCompress) {
                const compValues = col.nodes.map(n => Math.pow(Math.max(n.value, 0.01), this.compressionPower));
                const compTotal = compValues.reduce((s, v) => s + v, 0);
                proportions = compValues.map(v => compTotal > 0 ? v / compTotal : 0);
            } else {
                proportions = col.nodes.map(() => 1);
            }

            let y = this.padding.top;
            const x = this.padding.left + ci * (this.nodeWidth + columnGap);

            for (let i = 0; i < col.nodes.length; i++) {
                const node = col.nodes[i];
                node.h = Math.max(this.minNodeHeight, proportions[i] * availH);
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
                    node.h = Math.max(this.minNodeHeight * 0.7, node.h * scale);
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

            let opacity = '0.18';
            if (this.highlightedWallet) {
                // Wallet-level highlighting: trace path back from wallet through chain to total
                const walletChainId = `chain-${this.highlightedChain}`;
                const isWalletLink = link.target === this.highlightedWallet && link.source === walletChainId;
                const isChainLink = link.target === walletChainId && link.source === 'total';
                opacity = (isWalletLink || isChainLink) ? '0.4' : '0.04';
            } else if (this.highlightedChain) {
                const isChainLink = link.source === `chain-${this.highlightedChain}` ||
                                    link.target === `chain-${this.highlightedChain}`;
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
                let nodeOpacity = '1';
                if (this.highlightedWallet) {
                    // Wallet-level: highlight the selected wallet, its chain, and total
                    if (node.id === this.highlightedWallet) {
                        nodeOpacity = '1';
                    } else if (node.type === 'chain' && node.chain === this.highlightedChain) {
                        nodeOpacity = '1';
                    } else if (node.type === 'total') {
                        nodeOpacity = '1';
                    } else {
                        nodeOpacity = '0.15';
                    }
                } else if (this.highlightedChain) {
                    if (node.type === 'chain' && node.chain !== this.highlightedChain) {
                        nodeOpacity = '0.25';
                    } else if (node.type === 'wallet' && node.chain !== this.highlightedChain) {
                        nodeOpacity = '0.25';
                    }
                }

                const isExpanded = this.expandedWallet === node.id;

                const rect = this._svgEl('rect', {
                    x: node.x,
                    y: node.y,
                    width: node.w,
                    height: node.h,
                    rx: 4,
                    ry: 4,
                    fill: node.color,
                    class: 'sankey-node' + (isExpanded ? ' sankey-node-expanded' : ''),
                    'data-id': node.id,
                    opacity: nodeOpacity
                });

                // Expanded wallet gets a glowing stroke
                if (isExpanded) {
                    rect.setAttribute('stroke', this._getAccentColor());
                    rect.setAttribute('stroke-width', '2');
                }

                // Chain nodes: click to highlight
                if (node.type === 'chain' && node.chain !== 'other') {
                    rect.style.cursor = 'pointer';
                    rect.addEventListener('click', () => this._onChainClick(node));
                }

                // Wallet nodes: click for reverse selection + category expansion
                if (node.type === 'wallet') {
                    rect.style.cursor = 'pointer';
                    rect.addEventListener('click', () => this._onWalletClick(node));
                }

                rect.addEventListener('mouseenter', (e) => this._onNodeHover(e, node, layout));
                rect.addEventListener('mouseleave', () => this._onNodeLeave());
                rect.addEventListener('mousemove', (e) => this._moveTooltip(e));

                gNodes.appendChild(rect);

                // Don't draw label for expanded wallet (categories replace it)
                if (!isExpanded) {
                    this._drawLabel(gLabels, node, layout.columns.length, nodeOpacity);
                } else {
                    // Draw wallet name above the node instead
                    this._drawExpandedWalletLabel(gLabels, node);
                }
            }
        }

        this.svg.appendChild(gNodes);
        this.svg.appendChild(gLabels);
    }

    _drawLabel(g, node, numCols, nodeOpacity) {
        const isMobile = this.width < 480;
        const isSmall = this.width < 768;

        if (isMobile && node.h < 22) return;

        const fontSize = isSmall ? 10 : 12;
        const valueFontSize = isSmall ? 9 : 11;

        let textX, anchor;

        if (node.type === 'total') {
            textX = node.x - 8;
            anchor = 'end';
        } else if (node.type === 'wallet') {
            textX = node.x + node.w + 8;
            anchor = 'start';
        } else {
            if (numCols > 2) {
                textX = node.x - 8;
                anchor = 'end';
            } else {
                textX = node.x + node.w + 8;
                anchor = 'start';
            }
        }

        const textY = node.y + node.h / 2;

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

    _drawExpandedWalletLabel(g, node) {
        const isSmall = this.width < 768;
        const fontSize = isSmall ? 10 : 11;

        // Draw wallet name to the left of the node (above the category area)
        let labelText = node.label;
        const maxLen = isSmall ? 12 : 18;
        if (labelText.length > maxLen) {
            labelText = labelText.substring(0, maxLen - 1) + '…';
        }

        const nameEl = this._svgEl('text', {
            x: node.x + node.w + 8,
            y: node.y - 6,
            'text-anchor': 'start',
            'dominant-baseline': 'auto',
            class: 'sankey-label-name',
            'font-size': fontSize,
            fill: this._getAccentColor(),
            opacity: '1'
        });
        nameEl.textContent = labelText + ' ' + this._formatCompactUSD(node.value);
        g.appendChild(nameEl);
    }

    // ===========================
    // Category Expansion
    // ===========================

    _drawCategoryExpansion(layout) {
        if (!this.expandedWallet) return;

        const walletNode = layout.nodeMap[this.expandedWallet];
        if (!walletNode) return;

        const categories = [];
        if (walletNode.nativeCoinUsd > 0) {
            categories.push({
                label: walletNode.nativeCoinSymbol || 'Native',
                value: walletNode.nativeCoinUsd,
                color: walletNode.color
            });
        }
        if (walletNode.tokenUsd > 0) {
            categories.push({
                label: 'Tokens',
                value: walletNode.tokenUsd,
                color: this._lightenColor(walletNode.baseColor || walletNode.color, 0.35)
            });
        }

        // Need at least 2 categories to show the expansion
        if (categories.length < 2) return;

        const gCat = this._svgEl('g', { class: 'sankey-category-group' });
        const gCatLinks = this._svgEl('g', { class: 'sankey-category-links' });

        // Layout: category bars to the right of the wallet node
        const catGap = 15;
        const catBarX = walletNode.x + walletNode.w + catGap;
        const catBarW = 14;
        const catNodeGap = 3;
        const catTotalValue = categories.reduce((s, c) => s + c.value, 0);

        // Available height for categories = wallet node height
        const catAvailH = Math.max(walletNode.h, 30); // min 30px for readability
        const totalCatGaps = (categories.length - 1) * catNodeGap;
        const catDrawH = catAvailH - totalCatGaps;

        // Center categories on the wallet node
        const catStartY = walletNode.y + (walletNode.h - catAvailH) / 2;

        let catY = catStartY;
        const catNodes = [];

        for (const cat of categories) {
            const proportion = catTotalValue > 0 ? cat.value / catTotalValue : 0;
            const barH = Math.max(8, proportion * catDrawH);

            catNodes.push({
                x: catBarX,
                y: catY,
                w: catBarW,
                h: barH,
                label: cat.label,
                value: cat.value,
                color: cat.color
            });

            // Draw category bar
            const rect = this._svgEl('rect', {
                x: catBarX,
                y: catY,
                width: catBarW,
                height: barH,
                rx: 3,
                ry: 3,
                fill: cat.color,
                class: 'sankey-node sankey-category-bar',
                opacity: '1'
            });
            gCat.appendChild(rect);

            // Mini link from wallet to category
            const linkMidX = (walletNode.x + walletNode.w + catBarX) / 2;
            const srcY0 = walletNode.y + (catY - catStartY);
            const srcH = (barH / catAvailH) * walletNode.h;

            const linkD = [
                `M ${walletNode.x + walletNode.w},${srcY0}`,
                `C ${linkMidX},${srcY0} ${linkMidX},${catY} ${catBarX},${catY}`,
                `L ${catBarX},${catY + barH}`,
                `C ${linkMidX},${catY + barH} ${linkMidX},${srcY0 + srcH} ${walletNode.x + walletNode.w},${srcY0 + srcH}`,
                'Z'
            ].join(' ');

            const linkPath = this._svgEl('path', {
                d: linkD,
                class: 'sankey-link sankey-category-link',
                fill: cat.color,
                'fill-opacity': '0.25',
                stroke: 'none'
            });
            gCatLinks.appendChild(linkPath);

            // Category label
            const labelX = catBarX + catBarW + 6;
            const labelY = catY + barH / 2;

            const isSmall = this.width < 768;
            const fontSize = isSmall ? 9 : 11;

            const nameEl = this._svgEl('text', {
                x: labelX,
                y: labelY - (barH > 20 ? 3 : 0),
                'text-anchor': 'start',
                'dominant-baseline': barH > 20 ? 'auto' : 'central',
                class: 'sankey-label-name sankey-category-label',
                'font-size': fontSize,
                fill: this._getTextColor(),
                opacity: '1'
            });
            nameEl.textContent = cat.label;
            gCat.appendChild(nameEl);

            if (barH > 20) {
                const valEl = this._svgEl('text', {
                    x: labelX,
                    y: labelY + fontSize - 3,
                    'text-anchor': 'start',
                    'dominant-baseline': 'auto',
                    class: 'sankey-label-value sankey-category-label',
                    'font-size': fontSize - 1,
                    fill: this._getSecondaryTextColor(),
                    opacity: '1'
                });
                valEl.textContent = this._formatCompactUSD(cat.value);
                gCat.appendChild(valEl);
            }

            catY += barH + catNodeGap;
        }

        this.svg.appendChild(gCatLinks);
        this.svg.appendChild(gCat);
    }

    // ===========================
    // Interactions
    // ===========================

    _onChainClick(node) {
        if (this.highlightedChain === node.chain && !this.highlightedWallet) {
            this.highlightedChain = null;
        } else {
            this.highlightedChain = node.chain;
        }
        // Clear wallet-level selection when clicking a chain
        this.highlightedWallet = null;
        this.expandedWallet = null;
        this.render();
    }

    _onWalletClick(node) {
        if (this.highlightedWallet === node.id) {
            // Deselect
            this.highlightedWallet = null;
            this.highlightedChain = null;
            this.expandedWallet = null;
        } else {
            // Select: reverse-highlight path + expand categories
            this.highlightedWallet = node.id;
            this.highlightedChain = node.chain;
            this.expandedWallet = node.id;
        }
        this.render();
    }

    _onNodeHover(e, node, layout) {
        const linkEls = this.svg.querySelectorAll('.sankey-link:not(.sankey-category-link)');
        linkEls.forEach(el => {
            const src = el.getAttribute('data-source');
            const tgt = el.getAttribute('data-target');
            if (src === node.id || tgt === node.id) {
                el.setAttribute('fill-opacity', '0.4');
            } else if (!this.highlightedChain && !this.highlightedWallet) {
                el.setAttribute('fill-opacity', '0.06');
            }
        });

        const pct = this.totalValue > 0 ? ((node.value / this.totalValue) * 100).toFixed(1) : '0';
        let tooltipHtml = `<strong>${this._escapeHTML(node.label)}</strong><br>${this._formatCompactUSD(node.value)} (${pct}%)`;

        if (node.type === 'chain' && this.walletsByChain[node.chain]) {
            const wCount = this.walletsByChain[node.chain].length;
            tooltipHtml += `<br><span style="opacity:0.7">${wCount} wallet${wCount !== 1 ? 's' : ''}</span>`;
        }

        if (node.type === 'wallet') {
            tooltipHtml += `<br><span style="opacity:0.7">Click to expand categories</span>`;
        }

        this.tooltip.innerHTML = tooltipHtml;
        this.tooltip.style.display = 'block';
        this._moveTooltip(e);
    }

    _onNodeLeave() {
        const linkEls = this.svg.querySelectorAll('.sankey-link:not(.sankey-category-link)');
        if (this.highlightedWallet) {
            const walletChainId = `chain-${this.highlightedChain}`;
            linkEls.forEach(el => {
                const src = el.getAttribute('data-source');
                const tgt = el.getAttribute('data-target');
                const isWalletLink = tgt === this.highlightedWallet && src === walletChainId;
                const isChainLink = tgt === walletChainId && src === 'total';
                el.setAttribute('fill-opacity', (isWalletLink || isChainLink) ? '0.4' : '0.04');
            });
        } else if (this.highlightedChain) {
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
        const linkEls = this.svg.querySelectorAll('.sankey-link:not(.sankey-category-link)');
        linkEls.forEach(el => {
            if (el.getAttribute('data-source') === link.source && el.getAttribute('data-target') === link.target) {
                el.setAttribute('fill-opacity', '0.4');
            } else if (!this.highlightedChain && !this.highlightedWallet) {
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
        this._onNodeLeave();
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
    // Theme & Color Helpers
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

    /**
     * Adjust chain node color for theme visibility and cohesion.
     * Keeps brand colors recognizable but ensures visibility on each background.
     */
    _getThemedNodeColor(baseColor) {
        const theme = this._getTheme();
        const [r, g, b] = this._hexToRgb(baseColor);
        const brightness = (r * 0.299 + g * 0.587 + b * 0.114);

        switch (theme) {
            case 'light':
                // Very dark colors are invisible on light backgrounds — lighten them
                if (brightness < 80) {
                    return this._blendColors(baseColor, '#ffffff', 0.35);
                }
                // Very bright colors wash out — darken slightly
                if (brightness > 200) {
                    return this._blendColors(baseColor, '#000000', 0.15);
                }
                return baseColor;

            case 'cypherpunk1':
                // Subtle neon cyan tint for cyberpunk cohesion
                return this._blendColors(baseColor, '#0abdc6', 0.12);

            case 'ocean-depths':
                // Subtle deep blue tint
                return this._blendColors(baseColor, '#0077cc', 0.12);

            case 'sunset-horizon':
                // Subtle warm tint
                return this._blendColors(baseColor, '#ff8c42', 0.1);

            default: // dark-mode
                // Ensure very dark colors are visible on dark background
                if (brightness < 60) {
                    return this._blendColors(baseColor, '#ffffff', 0.3);
                }
                return baseColor;
        }
    }

    /**
     * Create themed link colors that blend chain color with theme accent.
     * Links carry the "feel" of the theme through the flow paths.
     */
    _getThemedLinkColor(baseColor) {
        const theme = this._getTheme();
        const accent = this._getAccentColor();

        switch (theme) {
            case 'light':
                // Softer links on light bg: blend with subtle gray
                return this._blendColors(baseColor, '#b0b0b0', 0.15);
            case 'cypherpunk1':
                // Strong neon tint in links
                return this._blendColors(baseColor, accent, 0.25);
            case 'ocean-depths':
                // Blue-tinted links
                return this._blendColors(baseColor, accent, 0.2);
            case 'sunset-horizon':
                // Warm-tinted links
                return this._blendColors(baseColor, accent, 0.18);
            default: // dark-mode
                // Subtle green tint
                return this._blendColors(baseColor, accent, 0.1);
        }
    }

    // ===========================
    // Color Utilities
    // ===========================

    _hexToRgb(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        return [
            parseInt(hex.slice(0, 2), 16),
            parseInt(hex.slice(2, 4), 16),
            parseInt(hex.slice(4, 6), 16)
        ];
    }

    _rgbToHex(r, g, b) {
        return '#' + [r, g, b]
            .map(c => Math.round(Math.max(0, Math.min(255, c))).toString(16).padStart(2, '0'))
            .join('');
    }

    _blendColors(hex1, hex2, ratio) {
        const [r1, g1, b1] = this._hexToRgb(hex1);
        const [r2, g2, b2] = this._hexToRgb(hex2);
        return this._rgbToHex(
            r1 + (r2 - r1) * ratio,
            g1 + (g2 - g1) * ratio,
            b1 + (b2 - b1) * ratio
        );
    }

    _lightenColor(hex, amount) {
        return this._blendColors(hex, '#ffffff', amount);
    }

    _darkenColor(hex, amount) {
        return this._blendColors(hex, '#000000', amount);
    }

    // ===========================
    // General Utilities
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
