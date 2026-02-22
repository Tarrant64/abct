// ABCT Portfolio Tracker - Frontend JavaScript

const API_BASE = '';

/**
 * Get authentication headers for API requests
 * @returns {Object} Headers object with Authorization token
 */
function getAuthHeaders() {
    const token = localStorage.getItem('abct_token');
    if (token) {
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    }
    return { 'Content-Type': 'application/json' };
}

/**
 * Authenticated fetch wrapper
 * Automatically includes auth token in requests
 */
async function authFetch(url, options = {}) {
    const token = localStorage.getItem('abct_token');
    if (token) {
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };
    }
    return fetch(url, options);
}

// Price data cache
let prices = { ADA: 0, BTC: 0, ETH: 0, SOL: 0, MATIC: 0, BNB: 0, AVAX: 0, TRX: 0 };

// Portfolio totals for calculating total value
let walletTotals = { ADA: 0, BTC: 0, ETH: 0, SOL: 0, MATIC: 0, ETH_BASE: 0, ALGO: 0, BNB: 0, ETH_ARB: 0, AVAX: 0, TRX: 0, XRP: 0, HBAR: 0, EGLD: 0, SUI: 0, APT: 0, FIL: 0, LTC: 0, DOGE: 0, ZEC: 0, XTZ: 0, STX: 0, VET: 0, ATOM: 0, NEAR: 0, ICP: 0, ETH_OPT: 0, ETH_ZK: 0, ETH_LINEA: 0, ETH_SCROLL: 0, FTM: 0, CRO: 0, XDAI: 0, GLMR: 0, OSMO: 0, TIA: 0, INJ: 0, DYDX: 0, SEI: 0, AKT: 0, TON: 0, DOT: 0, KSM: 0, XLM: 0, KAS: 0, KLAY: 0, ERG: 0, IOTA: 0, WAVES: 0, MINA: 0, ZIL: 0 };
let stakingTotals = {}; // { 'INDY': 1234.56, 'STRIKE': 789.01, etc. }
let defiTotals = {}; // DeFi tokens held in wallets (governance tokens, stablecoins, etc.)
let exchangeTotals = { usd: 0 }; // Total USD value from exchanges
let exchangeStakedAssets = []; // Staked assets from exchanges (display-only, not added to staking totals)
let snapshotTotals = { staking: 0, defi: 0, trackedTokens: 0 }; // From latest snapshot (dashboard only)
let nftTotals = { cardano: 0, ethereum: 0, solana: 0, polygon: 0, base: 0, algorand: 0, bsc: 0, arbitrum: 0, avalanche: 0 }; // NFT values by chain
let nftCounts = { cardano: 0, ethereum: 0, solana: 0, polygon: 0, base: 0, algorand: 0, bsc: 0, arbitrum: 0, avalanche: 0 }; // NFT counts by chain

// Lazy governance tab rendering
let _govRenderData = null; // { defiData, allStaking } for lazy governance tab
let _govRendered = false;

// NFT chain selection
let currentNFTChain = 'cardano';

// NFT Image caching
let imageCacheEnabled = false;

// ============================================================================
// XSS PROTECTION - Safe HTML Rendering
// ============================================================================

/**
 * Safely set HTML content using DOMPurify to prevent XSS attacks.
 * Use this instead of innerHTML when setting dynamic content from APIs or user input.
 *
 * @param {HTMLElement} element - The DOM element to update
 * @param {string} html - The HTML string to sanitize and set
 */
function setSafeHTML(element, html) {
    if (!element) return;
    if (typeof DOMPurify !== 'undefined') {
        element.innerHTML = DOMPurify.sanitize(html);
    } else {
        // Fallback if DOMPurify not loaded - use textContent for safety
        console.warn('DOMPurify not loaded, falling back to textContent');
        element.textContent = html;
    }
}

/**
 * Safely set text content (no HTML parsing).
 * Use this for plain text, numbers, or formatted strings that don't need HTML.
 *
 * @param {HTMLElement} element - The DOM element to update
 * @param {string} text - The text content to set
 */
function setSafeText(element, text) {
    if (!element) return;
    element.textContent = text;
}

// ============================================================================
// LOGOKIT API INTEGRATION
// ============================================================================

// Cached LogoKit token — loaded from backend /api/config/public on init
let _logokitToken = '';

/**
 * Fetch the LogoKit publishable token from the backend.
 * Called once on page load; result is cached in _logokitToken.
 */
async function initLogokitToken() {
    try {
        const resp = await fetch(`${API_BASE}/api/config/public`);
        if (resp.ok) {
            const data = await resp.json();
            _logokitToken = data.logokit_token || '';
        }
    } catch (e) {
        // Fail silently — logos will load without token (may hit rate limits)
    }
}

/**
 * Get LogoKit URL for a token symbol (client-side helper).
 *
 * @param {string} symbol - Token symbol (BTC, ETH, ADA, etc.)
 * @param {number} size - Optional size (64, 128, 256)
 * @returns {string} LogoKit CDN URL
 */
function getLogoKitUrl(symbol, size = 64) {
    const tokenParam = _logokitToken ? `?token=${_logokitToken}` : '';
    const sizeParam = size ? `${tokenParam ? '&' : '?'}size=${size}` : '';
    return `https://img.logokit.com/crypto/${symbol.toUpperCase()}${tokenParam}${sizeParam}`;
}

/**
 * Create an <img> element for a token/crypto logo with fallback.
 *
 * @param {string} logoUrl - LogoKit URL
 * @param {string} symbol - Token symbol (for alt text)
 * @param {string} fallbackText - Text to show if image fails (default: first letter)
 * @returns {HTMLElement} Image or fallback element
 */
function createTokenLogo(logoUrl, symbol, fallbackText = null) {
    const container = document.createElement('div');
    container.className = 'token-logo-container';

    if (!fallbackText) {
        fallbackText = symbol.charAt(0).toUpperCase();
    }

    // Create image
    const img = document.createElement('img');
    img.src = logoUrl;
    img.alt = `${symbol} logo`;
    img.className = 'token-logo-img';

    // Create fallback (shown if image fails to load)
    const fallback = document.createElement('div');
    fallback.className = 'token-logo-fallback';
    fallback.textContent = fallbackText;
    fallback.style.display = 'none';

    // Handle image load/error
    img.onerror = () => {
        img.style.display = 'none';
        fallback.style.display = 'flex';
    };

    img.onload = () => {
        img.style.display = 'block';
        fallback.style.display = 'none';
    };

    container.appendChild(img);
    container.appendChild(fallback);

    return container;
}

// Helper to get total NFT value across all chains
function getNftTotalUsd() {
    return (nftTotals.cardano || 0) + (nftTotals.ethereum || 0) + (nftTotals.solana || 0) + (nftTotals.polygon || 0) + (nftTotals.base || 0) + (nftTotals.algorand || 0) + (nftTotals.bsc || 0) + (nftTotals.arbitrum || 0) + (nftTotals.avalanche || 0);
}

// Update NFT counts in summary cards
function updateSummaryCardNftCounts() {
    const chains = ['cardano', 'ethereum', 'solana', 'polygon', 'base', 'algorand', 'bsc', 'arbitrum', 'avalanche'];
    for (const chain of chains) {
        const el = document.getElementById(`${chain}DynNfts`);
        if (el) {
            const count = nftCounts[chain] || 0;
            el.textContent = count > 0 ? `${count} NFT${count !== 1 ? 's' : ''}` : '';
        }
    }
}

// Format USD currency
function formatUSD(amount) {
    if (amount >= 1000000) {
        return '$' + (amount / 1000000).toFixed(2) + 'M';
    } else if (amount >= 1000) {
        return '$' + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else {
        return '$' + amount.toFixed(2);
    }
}

// Wrap value in blur-value span for privacy mode (only blurs the number, not labels)
function blurValue(value, label = '') {
    const labelHtml = label ? ` <span class="blur-label">${label}</span>` : '';
    return `<span class="blur-value">${value}</span>${labelHtml}`;
}

// Format USD with blur wrapper
function formatUSDBlur(amount) {
    return blurValue(formatUSD(amount));
}

// Format crypto balance with blur wrapper (value + label separate)
function formatCryptoBlur(value, symbol, decimals = 6) {
    const formatted = typeof value === 'number'
        ? value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: decimals})
        : value;
    return `<span class="blur-value">${formatted}</span> ${symbol}`;
}

// Theme management
function changeTheme(themeName) {
    // Apply theme to document
    document.documentElement.setAttribute('data-theme', themeName);

    // Save preference to localStorage
    localStorage.setItem('abct-theme', themeName);

    // Update select element if called programmatically
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect && themeSelect.value !== themeName) {
        themeSelect.value = themeName;
    }

    // Re-render portfolio history chart with new theme colors
    if (v2Chart) {
        const activeBtn = document.querySelector('.v2-range.active');
        const range = activeBtn ? activeBtn.dataset.range : '1w';
        loadV2BalanceHistory(range);
    }

    // Re-render analytics charts with new theme colors
    if (portfolioAnalyticsData) {
        if (coinAllocationChart) {
            renderCoinAllocationChart();
        }
        if (categoryAllocationChart) {
            renderCategoryAllocationChart();
        }
    }

    // Re-render Sankey with new theme colors
    if (window.portfolioSankey) {
        window.portfolioSankey.updateTheme();
    }

    // Re-render Streamgraph with new theme colors
    if (window.portfolioStream) {
        window.portfolioStream.updateTheme();
    }

    // Re-render intelligence tab with new theme colors
    if (typeof updateIntelligenceTheme === 'function') {
        updateIntelligenceTheme();
    }
}

function loadSavedTheme() {
    // Load saved theme from localStorage
    const savedTheme = localStorage.getItem('abct-theme') || 'dark-mode';
    changeTheme(savedTheme);
}

// Store full price data including changes
let priceData = {};

// Load prices from API (all tracked assets including DeFi)
async function loadPrices() {
    try {
        const response = await authFetch(`${API_BASE}/prices/all`);
        const data = await response.json();
        // Store full price data and convert to simple prices object
        prices = {};
        priceData = data.prices || {};
        for (const [symbol, pd] of Object.entries(priceData)) {
            prices[symbol] = pd.usd || 0;
        }

        // Debug logging
        console.log('[Prices] Loaded:', {
            ADA: prices.ADA,
            BTC: prices.BTC,
            ETH: prices.ETH,
            total_symbols: Object.keys(prices).length
        });

        // Update price display in summary cards
        updatePriceDisplay();
        return prices;
    } catch (error) {
        console.error('Error loading prices:', error);
        return prices;
    }
}

// Cardano SSE price stream (Charli3) - updates prices in real-time when available
let _cardanoPriceStream = null;
function initCardanoPriceStream() {
    if (_cardanoPriceStream) return;
    try {
        _cardanoPriceStream = new EventSource(`${API_BASE}/prices/stream/cardano`);
        _cardanoPriceStream.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.error) {
                    console.debug('Cardano stream:', data.error);
                    _cardanoPriceStream.close();
                    _cardanoPriceStream = null;
                    return;
                }
                // Update price data from stream events
                if (data.prices) {
                    for (const [symbol, priceInfo] of Object.entries(data.prices)) {
                        if (priceInfo && priceInfo.price) {
                            prices[symbol] = priceInfo.price;
                            if (priceData[symbol]) {
                                priceData[symbol].usd = priceInfo.price;
                            }
                        }
                    }
                    updatePriceDisplay();
                }
            } catch (e) {
                console.debug('SSE parse error:', e);
            }
        };
        _cardanoPriceStream.onerror = function() {
            console.debug('Cardano price stream disconnected, falling back to polling');
            _cardanoPriceStream.close();
            _cardanoPriceStream = null;
        };
    } catch (e) {
        console.debug('SSE not available:', e);
    }
}

// Format market cap as HTML with styled suffix (e.g., "45.2 <span>B</span>")
function formatMarketCap(marketCap) {
    if (!marketCap || marketCap === 0) return '';
    let value, suffix;
    if (marketCap >= 1e12) {
        value = (marketCap / 1e12).toFixed(1);
        suffix = 'T';
    } else if (marketCap >= 1e9) {
        value = (marketCap / 1e9).toFixed(1);
        suffix = 'B';
    } else if (marketCap >= 1e6) {
        value = (marketCap / 1e6).toFixed(0);
        suffix = 'M';
    } else {
        value = (marketCap / 1e3).toFixed(0);
        suffix = 'K';
    }
    return `${value} <span class="mcap-suffix">${suffix}</span>`;
}

// Update price and 1hr change display in dynamic summary cards
function updatePriceDisplay() {
    // Map each chain to its price symbol for lookup in priceData
    const chainPriceMap = {
        cardano: 'ADA', bitcoin: 'BTC', ethereum: 'ETH',
        solana: 'SOL', polygon: 'MATIC', base: 'ETH', algorand: 'ALGO'
    };

    for (const [chain, symbol] of Object.entries(chainPriceMap)) {
        const priceElement = document.getElementById(`${chain}DynPrice`);
        const changeElement = document.getElementById(`${chain}DynChange`);
        const mcapElement = document.getElementById(`${chain}DynMcap`);
        const pd = priceData[symbol];

        if (priceElement && pd) {
            priceElement.textContent = formatPriceStr(pd.usd || 0);
        }

        if (changeElement && pd) {
            const change1h = pd.usd_1h_change || 0;
            const changeText = `${change1h >= 0 ? '+' : ''}${change1h.toFixed(2)}%`;
            changeElement.textContent = changeText;
            changeElement.classList.remove('positive', 'negative');
            changeElement.classList.add(change1h >= 0 ? 'positive' : 'negative');
        }

        if (mcapElement && pd) {
            const mcap = pd.market_cap || 0;
            setSafeHTML(mcapElement, mcap > 0 ? `MCap: ${formatMarketCap(mcap)}` : '');
        }
    }
}

// Chain config for dynamic blockchain card rendering
const CHAIN_CONFIG = {
    cardano:  { name: 'Cardano',  symbol: 'ADA',   logo: 'ADA',  icon: '₳', decimals: 6, priceKey: 'ADA',   balanceKey: 'total_ada',   nativeLabel: 'ADA' },
    bitcoin:  { name: 'Bitcoin',  symbol: 'BTC',    logo: 'BTC',  icon: '₿', decimals: 8, priceKey: 'BTC',   balanceKey: 'total_btc',   nativeLabel: 'BTC' },
    ethereum: { name: 'Ethereum', symbol: 'ETH',    logo: 'ETH',  icon: 'Ξ', decimals: 8, priceKey: 'ETH',   balanceKey: 'total_eth',   nativeLabel: 'ETH' },
    solana:   { name: 'Solana',   symbol: 'SOL',    logo: 'SOL',  icon: '◎', decimals: 9, priceKey: 'SOL',   balanceKey: 'total_sol',   nativeLabel: 'SOL' },
    polygon:  { name: 'Polygon',  symbol: 'POL',    logo: 'MATIC', icon: '⬡', decimals: 6, priceKey: 'MATIC', balanceKey: 'total_matic', nativeLabel: 'POL' },
    base:     { name: 'Base',     symbol: 'ETH',    logo: null,    icon: 'Ⓑ', decimals: 8, priceKey: 'ETH',   balanceKey: 'total_eth',   nativeLabel: 'ETH', logoUrl: 'https://avatars.githubusercontent.com/u/108554348' },
    algorand: { name: 'Algorand', symbol: 'ALGO',   logo: 'ALGO', icon: 'Ⓐ', decimals: 6, priceKey: 'ALGO',  balanceKey: 'total_algo',  nativeLabel: 'ALGO' },
    bsc:       { name: 'BNB Chain',   symbol: 'BNB',  logo: 'BNB',  icon: '◆', decimals: 8, priceKey: 'BNB',   balanceKey: 'total_bnb',  nativeLabel: 'BNB' },
    arbitrum:  { name: 'Arbitrum',    symbol: 'ETH',  logo: 'ETH',  icon: '◇', decimals: 8, priceKey: 'ETH',   balanceKey: 'total_eth',  nativeLabel: 'ETH' },
    avalanche: { name: 'Avalanche',   symbol: 'AVAX', logo: 'AVAX', icon: '▲', decimals: 8, priceKey: 'AVAX',  balanceKey: 'total_avax', nativeLabel: 'AVAX' },
    tron:      { name: 'Tron',        symbol: 'TRX',  logo: 'TRX',  icon: '◈', decimals: 6, priceKey: 'TRX',   balanceKey: 'total_trx',  nativeLabel: 'TRX' },
    xrp:        { name: 'XRP Ledger',  symbol: 'XRP',  logo: 'XRP',  icon: '✕', decimals: 6, priceKey: 'XRP',   balanceKey: 'total_xrp',  nativeLabel: 'XRP' },
    hedera:     { name: 'Hedera',      symbol: 'HBAR', logo: 'HBAR', icon: 'ℏ', decimals: 8, priceKey: 'HBAR',  balanceKey: 'total_hbar', nativeLabel: 'HBAR' },
    multiversx: { name: 'MultiversX',  symbol: 'EGLD', logo: 'EGLD', icon: '⬢', decimals: 8, priceKey: 'EGLD',  balanceKey: 'total_egld', nativeLabel: 'EGLD' },
    sui:        { name: 'Sui',         symbol: 'SUI',  logo: 'SUI',  icon: '💧', decimals: 9, priceKey: 'SUI',   balanceKey: 'total_sui',  nativeLabel: 'SUI' },
    aptos:      { name: 'Aptos',       symbol: 'APT',  logo: 'APT',  icon: '⬡', decimals: 8, priceKey: 'APT',   balanceKey: 'total_apt',  nativeLabel: 'APT' },
    filecoin:   { name: 'Filecoin',    symbol: 'FIL',  logo: 'FIL',  icon: '⬡', decimals: 8, priceKey: 'FIL',   balanceKey: 'total_fil',  nativeLabel: 'FIL' },
    litecoin:   { name: 'Litecoin',   symbol: 'LTC',  logo: 'LTC',  icon: 'Ł', decimals: 8, priceKey: 'LTC',   balanceKey: 'total_ltc',  nativeLabel: 'LTC' },
    dogecoin:   { name: 'Dogecoin',   symbol: 'DOGE', logo: 'DOGE', icon: 'Ð', decimals: 8, priceKey: 'DOGE',  balanceKey: 'total_doge', nativeLabel: 'DOGE' },
    zcash:      { name: 'Zcash',      symbol: 'ZEC',  logo: 'ZEC',  icon: 'ⓩ', decimals: 8, priceKey: 'ZEC',   balanceKey: 'total_zec',  nativeLabel: 'ZEC' },
    tezos:      { name: 'Tezos',      symbol: 'XTZ',  logo: 'XTZ',  icon: 'ꜩ', decimals: 6, priceKey: 'XTZ',   balanceKey: 'total_xtz',  nativeLabel: 'XTZ' },
    stacks:     { name: 'Stacks',     symbol: 'STX',  logo: 'STX',  icon: '⟐', decimals: 6, priceKey: 'STX',   balanceKey: 'total_stx',  nativeLabel: 'STX' },
    vechain:    { name: 'VeChain',    symbol: 'VET',  logo: 'VET',  icon: '⌬', decimals: 8, priceKey: 'VET',   balanceKey: 'total_vet',  nativeLabel: 'VET' },
    cosmos:     { name: 'Cosmos',     symbol: 'ATOM', logo: 'ATOM', icon: '⚛', decimals: 6, priceKey: 'ATOM',  balanceKey: 'total_atom', nativeLabel: 'ATOM' },
    near:       { name: 'NEAR',       symbol: 'NEAR', logo: 'NEAR', icon: 'Ⓝ', decimals: 8, priceKey: 'NEAR',  balanceKey: 'total_near', nativeLabel: 'NEAR' },
    icp:        { name: 'ICP',        symbol: 'ICP',  logo: 'ICP',  icon: '∞', decimals: 8, priceKey: 'ICP',   balanceKey: 'total_icp',  nativeLabel: 'ICP' },
    osmosis:    { name: 'Osmosis',   symbol: 'OSMO', logo: 'OSMO', icon: '⚗', decimals: 6, priceKey: 'OSMO',  balanceKey: 'total_osmo', nativeLabel: 'OSMO' },
    celestia:   { name: 'Celestia',  symbol: 'TIA',  logo: 'TIA',  icon: '✦', decimals: 6, priceKey: 'TIA',   balanceKey: 'total_tia',  nativeLabel: 'TIA'  },
    injective:  { name: 'Injective', symbol: 'INJ',  logo: 'INJ',  icon: '⬡', decimals: 8, priceKey: 'INJ',   balanceKey: 'total_inj',  nativeLabel: 'INJ'  },
    dydx:       { name: 'dYdX',      symbol: 'DYDX', logo: 'DYDX', icon: '⬡', decimals: 8, priceKey: 'DYDX',  balanceKey: 'total_dydx', nativeLabel: 'DYDX' },
    sei:        { name: 'Sei',       symbol: 'SEI',  logo: 'SEI',  icon: '⬡', decimals: 6, priceKey: 'SEI',   balanceKey: 'total_sei',  nativeLabel: 'SEI'  },
    akash:      { name: 'Akash',     symbol: 'AKT',  logo: 'AKT',  icon: '☁', decimals: 6, priceKey: 'AKT',   balanceKey: 'total_akt',  nativeLabel: 'AKT'  },
    ton:        { name: 'TON',       symbol: 'TON',  logo: 'TON',  icon: '💎', decimals: 9, priceKey: 'TON',   balanceKey: 'total_ton',  nativeLabel: 'TON'  },
    polkadot:   { name: 'Polkadot',  symbol: 'DOT',  logo: 'DOT',  icon: '●', decimals: 10, priceKey: 'DOT',  balanceKey: 'total_dot',  nativeLabel: 'DOT'  },
    kusama:     { name: 'Kusama',    symbol: 'KSM',  logo: 'KSM',  icon: '⬡', decimals: 12, priceKey: 'KSM',  balanceKey: 'total_ksm',  nativeLabel: 'KSM'  },
    stellar:    { name: 'Stellar',   symbol: 'XLM',  logo: 'XLM',  icon: '*', decimals: 7, priceKey: 'XLM',   balanceKey: 'total_xlm',  nativeLabel: 'XLM'  },
    kaspa:      { name: 'Kaspa',     symbol: 'KAS',  logo: 'KAS',  icon: 'K', decimals: 8, priceKey: 'KAS',   balanceKey: 'total_kas',  nativeLabel: 'KAS'  },
    kaia:       { name: 'Kaia',      symbol: 'KLAY', logo: 'KLAY', icon: '⬡', decimals: 18, priceKey: 'KLAY', balanceKey: 'total_klay', nativeLabel: 'KLAY' },
    ergo:       { name: 'Ergo',      symbol: 'ERG',  logo: 'ERG',  icon: 'E', decimals: 9, priceKey: 'ERG',   balanceKey: 'total_erg',  nativeLabel: 'ERG'  },
    iota:       { name: 'IOTA',      symbol: 'IOTA', logo: 'IOTA', icon: 'I', decimals: 6, priceKey: 'IOTA',  balanceKey: 'total_iota', nativeLabel: 'IOTA' },
    waves:      { name: 'Waves',     symbol: 'WAVES',logo: 'WAVES',icon: '~', decimals: 8, priceKey: 'WAVES', balanceKey: 'total_waves',nativeLabel: 'WAVES'},
    mina:       { name: 'Mina',      symbol: 'MINA', logo: 'MINA', icon: 'M', decimals: 9, priceKey: 'MINA',  balanceKey: 'total_mina', nativeLabel: 'MINA' },
    zilliqa:    { name: 'Zilliqa',   symbol: 'ZIL',  logo: 'ZIL',  icon: 'Z', decimals: 12, priceKey: 'ZIL',  balanceKey: 'total_zil',  nativeLabel: 'ZIL'  },
};

// Render blockchain cards dynamically, sorted by value, only for chains with wallets
function renderBlockchainCards(portfolioData) {
    const container = document.getElementById('blockchainCards');
    if (!container) return;

    // Build chain data array with USD values
    const chains = [];
    for (const [chain, cfg] of Object.entries(CHAIN_CONFIG)) {
        const chainData = portfolioData[chain];
        if (!chainData) continue;
        const walletCount = chainData.wallet_count || 0;
        if (walletCount === 0) continue;

        const nativeBalance = chainData[cfg.balanceKey] || 0;
        const price = prices[cfg.priceKey] || 0;
        const nativeAssetsUsd = chainData.native_assets_value_usd || 0;
        const totalUsd = nativeBalance * price + nativeAssetsUsd;

        chains.push({ chain, cfg, chainData, nativeBalance, price, totalUsd, walletCount });
    }

    // Sort by USD value, highest first
    chains.sort((a, b) => b.totalUsd - a.totalUsd);

    if (chains.length === 0) {
        setSafeHTML(container, '<div class="empty-state" style="grid-column: 1/-1; text-align: center; padding: 40px;"><p>No wallets configured. Add wallets in <a href="/assets.html#manageWallets">Manage Wallets</a>.</p></div>');
        return;
    }

    // Build cards HTML
    let html = '';
    for (const { chain, cfg, chainData, nativeBalance, totalUsd, walletCount } of chains) {
        const pd = priceData[cfg.priceKey];
        const priceStr = formatPriceStr(pd?.usd || 0);
        const change1h = pd?.usd_1h_change || 0;
        const changeStr = `${change1h >= 0 ? '+' : ''}${change1h.toFixed(2)}%`;
        const changeClass = change1h >= 0 ? 'positive' : 'negative';
        const mcapHtml = pd?.market_cap ? `MCap: ${formatMarketCap(pd.market_cap)}` : '';

        // Build details spans
        let details = `<span>${walletCount} wallet${walletCount !== 1 ? 's' : ''}</span>`;
        if (chain === 'cardano' && chainData.native_assets_count) {
            details += `<span>${chainData.native_assets_count} native asset${chainData.native_assets_count !== 1 ? 's' : ''}</span>`;
        }
        if (chainData.token_count) {
            details += `<span>${chainData.token_count} token${chainData.token_count !== 1 ? 's' : ''}</span>`;
        }

        // NFT count for this chain (if any)
        const nftCount = nftCounts[chain] || 0;
        if (nftCount > 0) {
            details += `<span id="${chain}DynNfts">${nftCount} NFT${nftCount !== 1 ? 's' : ''}</span>`;
        } else {
            details += `<span id="${chain}DynNfts"></span>`;
        }

        // Logo: prefer CoinGecko image, then custom logoUrl, then LogoKit
        const logoSrc = pd?.image || cfg.logoUrl || getLogoKitUrl(cfg.logo, 32);

        html += `
            <div class="summary-card ${chain} clickable" data-chain="${chain}">
                <div class="card-header">
                    <img src="${logoSrc}" alt="${cfg.name}" class="blockchain-logo">
                    <span>${cfg.name}</span>
                    <div class="price-info">
                        <span class="token-price" id="${chain}DynPrice">${priceStr}</span>
                        <span class="price-change ${changeClass}" id="${chain}DynChange">${changeStr}</span>
                        <span class="market-cap" id="${chain}DynMcap">${mcapHtml}</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="balance">${formatCryptoBlur(nativeBalance.toFixed(cfg.decimals), cfg.nativeLabel, cfg.decimals)}</div>
                    <div class="balance-secondary">${formatUSDBlur(totalUsd)}</div>
                    <div class="details">${details}</div>
                </div>
            </div>`;
    }

    setSafeHTML(container, html);

    // Attach click handlers and image error handlers (DOMPurify strips inline event attributes)
    container.querySelectorAll('.summary-card[data-chain]').forEach(card => {
        card.addEventListener('click', () => openAssetBreakdown(card.dataset.chain));
    });
    container.querySelectorAll('img.blockchain-logo').forEach(img => {
        img.addEventListener('error', () => { img.style.display = 'none'; });
    });
}

// Format price string for card display
function formatPriceStr(price) {
    if (price >= 1000) return `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    if (price >= 1) return `$${price.toFixed(2)}`;
    return `$${price.toFixed(4)}`;
}

// Update total portfolio value display
function updateTotalPortfolioValue() {
    const totalValueEl = document.getElementById('totalPortfolioValue');

    if (!totalValueEl) return;

    // Calculate wallet value (all chains)
    const walletPriceMap = {
        ADA: 'ADA', BTC: 'BTC', ETH: 'ETH', SOL: 'SOL', MATIC: 'MATIC',
        ETH_BASE: 'ETH', ALGO: 'ALGO', BNB: 'BNB', ETH_ARB: 'ETH',
        AVAX: 'AVAX', TRX: 'TRX', XRP: 'XRP', HBAR: 'HBAR', EGLD: 'EGLD',
        SUI: 'SUI', APT: 'APT', FIL: 'FIL', LTC: 'LTC', DOGE: 'DOGE',
        ZEC: 'ZEC', XTZ: 'XTZ', STX: 'STX', VET: 'VET', ATOM: 'ATOM',
        NEAR: 'NEAR', ICP: 'ICP'
    };
    let walletsTotal = 0;
    for (const [walletKey, priceKey] of Object.entries(walletPriceMap)) {
        walletsTotal += (walletTotals[walletKey] || 0) * (prices[priceKey] || 0);
    }

    // Calculate staking value — use per-token totals if loaded (assets page), else snapshot USD
    let stakingTotal = 0;
    if (Object.keys(stakingTotals).length > 0) {
        for (const [token, amount] of Object.entries(stakingTotals)) {
            const price = prices[token] || 0;
            stakingTotal += amount * price;
        }
    } else {
        stakingTotal = snapshotTotals.staking || 0;
    }

    // Calculate DeFi tokens value — same fallback pattern
    let defiTotal = 0;
    if (Object.keys(defiTotals).length > 0) {
        for (const [token, amount] of Object.entries(defiTotals)) {
            const price = prices[token] || 0;
            defiTotal += amount * price;
        }
    } else {
        defiTotal = snapshotTotals.defi || 0;
    }

    // Exchange value (already in USD)
    const exchangesTotal = exchangeTotals.usd || 0;

    // NFT value (already in USD) - sum of all chains
    const nftsTotal = getNftTotalUsd();

    // Tracked native tokens value (from toggle selections, or snapshot fallback)
    const trackedTokensTotal = trackedTokensValue || snapshotTotals.trackedTokens || 0;

    // Custom tokens value (from toggle selections)
    const customTokensTotal = customTokensValue || 0;

    // Portfolio breakdown: Liquid / Staked / NFTs
    const liquidTotal = walletsTotal + exchangesTotal + trackedTokensTotal + customTokensTotal;
    const stakedTotal = stakingTotal + defiTotal;

    // Total portfolio value = sum of breakdown categories
    const totalValue = liquidTotal + stakedTotal + nftsTotal;

    // Update total display
    setSafeHTML(totalValueEl, formatUSDBlur(totalValue));

    // Update breakdown section
    const liquidEl = document.getElementById('breakdownLiquid');
    const stakedEl = document.getElementById('breakdownStaked');
    const nftsEl = document.getElementById('breakdownNfts');
    if (liquidEl) liquidEl.textContent = formatUSD(liquidTotal);
    if (stakedEl) stakedEl.textContent = formatUSD(stakedTotal);
    if (nftsEl) nftsEl.textContent = formatUSD(nftsTotal);

    // Cache for instant load on next visit
    if (totalValue > 0) {
        try {
            localStorage.setItem('cachedPortfolioTotal', JSON.stringify({
                total: totalValue,
                timestamp: Date.now()
            }));
        } catch (e) { /* localStorage full or unavailable */ }
    }

    // Update top holdings pills
    renderTopHoldings();

    // Store actual total for donut center display
    lastTotalPortfolioValue = totalValue;

    // Update portfolio donut chart
    updatePortfolioDonut();
}

// Portfolio donut chart instance
let portfolioDonutChart = null;
let donutSelectedIndex = -1;
let lastPortfolioData = null; // Stored for donut chart native asset values
let lastTotalPortfolioValue = 0; // Actual total including staking, exchanges, NFTs

function getChainAllocations() {
    const allocations = [];
    const chainMap = {
        cardano:  { label: 'Cardano',  symbol: 'ADA',  color: '#0033ad', balKey: 'ADA',   priceKey: 'ADA' },
        bitcoin:  { label: 'Bitcoin',  symbol: 'BTC',  color: '#f7931a', balKey: 'BTC',   priceKey: 'BTC' },
        ethereum: { label: 'Ethereum', symbol: 'ETH',  color: '#627eea', balKey: 'ETH',   priceKey: 'ETH' },
        solana:   { label: 'Solana',   symbol: 'SOL',  color: '#9945ff', balKey: 'SOL',   priceKey: 'SOL' },
        polygon:  { label: 'Polygon',  symbol: 'POL',  color: '#8247e5', balKey: 'MATIC', priceKey: 'MATIC' },
        base:     { label: 'Base',     symbol: 'ETH',  color: '#0052ff', balKey: 'ETH_BASE', priceKey: 'ETH' },
        algorand: { label: 'Algorand', symbol: 'ALGO', color: '#00d2c2', balKey: 'ALGO',  priceKey: 'ALGO' },
        bsc:      { label: 'BNB Chain', symbol: 'BNB', color: '#f3ba2f', balKey: 'BNB',  priceKey: 'BNB' },
        arbitrum: { label: 'Arbitrum', symbol: 'ETH', color: '#28a0f0', balKey: 'ETH_ARB', priceKey: 'ETH' },
        avalanche:{ label: 'Avalanche', symbol: 'AVAX', color: '#e84142', balKey: 'AVAX', priceKey: 'AVAX' },
        tron:     { label: 'Tron',     symbol: 'TRX', color: '#ff0013', balKey: 'TRX',  priceKey: 'TRX' },
        xrp:        { label: 'XRP Ledger', symbol: 'XRP',  color: '#23292f', balKey: 'XRP',  priceKey: 'XRP'  },
        hedera:     { label: 'Hedera',     symbol: 'HBAR', color: '#3d3d3d', balKey: 'HBAR', priceKey: 'HBAR' },
        multiversx: { label: 'MultiversX', symbol: 'EGLD', color: '#23f7dd', balKey: 'EGLD', priceKey: 'EGLD' },
        sui:        { label: 'Sui',        symbol: 'SUI',  color: '#4da2ff', balKey: 'SUI',  priceKey: 'SUI'  },
        aptos:      { label: 'Aptos',      symbol: 'APT',  color: '#2ed8a3', balKey: 'APT',  priceKey: 'APT'  },
        filecoin:   { label: 'Filecoin',   symbol: 'FIL',  color: '#0090ff', balKey: 'FIL',  priceKey: 'FIL'  },
        litecoin:   { label: 'Litecoin',   symbol: 'LTC',  color: '#345d9d', balKey: 'LTC',  priceKey: 'LTC'  },
        dogecoin:   { label: 'Dogecoin',   symbol: 'DOGE', color: '#c2a633', balKey: 'DOGE', priceKey: 'DOGE' },
        zcash:      { label: 'Zcash',      symbol: 'ZEC',  color: '#ecb244', balKey: 'ZEC',  priceKey: 'ZEC'  },
        tezos:      { label: 'Tezos',      symbol: 'XTZ',  color: '#2c7df7', balKey: 'XTZ',  priceKey: 'XTZ'  },
        stacks:     { label: 'Stacks',     symbol: 'STX',  color: '#5546ff', balKey: 'STX',  priceKey: 'STX'  },
        vechain:    { label: 'VeChain',    symbol: 'VET',  color: '#15bdff', balKey: 'VET',  priceKey: 'VET'  },
        cosmos:     { label: 'Cosmos',     symbol: 'ATOM', color: '#2e3148', balKey: 'ATOM', priceKey: 'ATOM' },
        near:       { label: 'NEAR',       symbol: 'NEAR', color: '#00c08b', balKey: 'NEAR', priceKey: 'NEAR' },
        icp:        { label: 'ICP',        symbol: 'ICP',  color: '#29abe2', balKey: 'ICP',  priceKey: 'ICP'  },
        optimism:   { label: 'Optimism',  symbol: 'ETH',  color: '#FF0420', balKey: 'ETH_OPT',    priceKey: 'ETH' },
        zksync:     { label: 'zkSync',    symbol: 'ETH',  color: '#8C8DFC', balKey: 'ETH_ZK',     priceKey: 'ETH' },
        linea:      { label: 'Linea',     symbol: 'ETH',  color: '#61DFFF', balKey: 'ETH_LINEA',  priceKey: 'ETH' },
        scroll:     { label: 'Scroll',    symbol: 'ETH',  color: '#FFEEDA', balKey: 'ETH_SCROLL', priceKey: 'ETH' },
        fantom:     { label: 'Fantom',    symbol: 'FTM',  color: '#1969FF', balKey: 'FTM',        priceKey: 'FTM' },
        cronos:     { label: 'Cronos',    symbol: 'CRO',  color: '#002D74', balKey: 'CRO',        priceKey: 'CRO' },
        gnosis:     { label: 'Gnosis',    symbol: 'xDAI', color: '#3E6957', balKey: 'XDAI',       priceKey: 'DAI' },
        moonbeam:   { label: 'Moonbeam',  symbol: 'GLMR', color: '#53CBC9', balKey: 'GLMR',       priceKey: 'GLMR' },
        osmosis:    { label: 'Osmosis',   symbol: 'OSMO', color: '#5604AB', balKey: 'OSMO',       priceKey: 'OSMO' },
        celestia:   { label: 'Celestia',  symbol: 'TIA',  color: '#7B2BF9', balKey: 'TIA',        priceKey: 'TIA'  },
        injective:  { label: 'Injective', symbol: 'INJ',  color: '#00F2FE', balKey: 'INJ',        priceKey: 'INJ'  },
        dydx:       { label: 'dYdX',      symbol: 'DYDX', color: '#6966FF', balKey: 'DYDX',       priceKey: 'DYDX' },
        sei:        { label: 'Sei',       symbol: 'SEI',  color: '#9B1B30', balKey: 'SEI',        priceKey: 'SEI'  },
        akash:      { label: 'Akash',     symbol: 'AKT',  color: '#FF414C', balKey: 'AKT',        priceKey: 'AKT'  },
        ton:        { label: 'TON',       symbol: 'TON',  color: '#0098EA', balKey: 'TON',        priceKey: 'TON'  },
        polkadot:   { label: 'Polkadot',  symbol: 'DOT',  color: '#E6007A', balKey: 'DOT',        priceKey: 'DOT'  },
        kusama:     { label: 'Kusama',    symbol: 'KSM',  color: '#000000', balKey: 'KSM',        priceKey: 'KSM'  },
        stellar:    { label: 'Stellar',   symbol: 'XLM',  color: '#14B6E7', balKey: 'XLM',        priceKey: 'XLM'  },
        kaspa:      { label: 'Kaspa',     symbol: 'KAS',  color: '#49EACB', balKey: 'KAS',        priceKey: 'KAS'  },
        kaia:       { label: 'Kaia',      symbol: 'KLAY', color: '#FE4101', balKey: 'KLAY',       priceKey: 'KLAY' },
        ergo:       { label: 'Ergo',      symbol: 'ERG',  color: '#FF5722', balKey: 'ERG',        priceKey: 'ERG'  },
        iota:       { label: 'IOTA',      symbol: 'IOTA', color: '#131F37', balKey: 'IOTA',       priceKey: 'IOTA' },
        waves:      { label: 'Waves',     symbol: 'WAVES',color: '#0055FF', balKey: 'WAVES',      priceKey: 'WAVES'},
        mina:       { label: 'Mina',      symbol: 'MINA', color: '#E49B13', balKey: 'MINA',       priceKey: 'MINA' },
        zilliqa:    { label: 'Zilliqa',   symbol: 'ZIL',  color: '#49C1BF', balKey: 'ZIL',        priceKey: 'ZIL'  },
    };

    for (const [chain, cfg] of Object.entries(chainMap)) {
        const balance = walletTotals[cfg.balKey] || 0;
        const price = prices[cfg.priceKey] || 0;
        const nativeAssetsUsd = lastPortfolioData?.[chain]?.native_assets_value_usd || 0;
        const usd = balance * price + nativeAssetsUsd;
        if (usd > 0) {
            allocations.push({
                chain, label: cfg.label, symbol: cfg.symbol,
                color: cfg.color, usd, balance, priceKey: cfg.priceKey
            });
        }
    }

    // Sort by value descending
    allocations.sort((a, b) => b.usd - a.usd);
    return allocations;
}

function updatePortfolioDonut() {
    const canvas = document.getElementById('portfolioDonutChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const allocations = getChainAllocations();
    const totalUsd = allocations.reduce((s, a) => s + a.usd, 0);

    if (totalUsd === 0) {
        // Hide donut if no data
        const container = document.getElementById('portfolioDonutContainer');
        if (container) container.style.display = 'none';
        return;
    }

    // Show container
    const container = document.getElementById('portfolioDonutContainer');
    if (container) container.style.display = 'flex';

    const labels = allocations.map(a => a.label);
    const data = allocations.map(a => a.usd);
    const colors = allocations.map(a => a.color);

    // Set default center text — use actual portfolio total (includes staking, exchanges, NFTs)
    const displayTotal = lastTotalPortfolioValue > 0 ? lastTotalPortfolioValue : totalUsd;
    if (donutSelectedIndex < 0) {
        setDonutCenterText('Total Balance', formatUSD(displayTotal), '');
    }

    if (portfolioDonutChart) {
        // Update existing chart data
        const ds = portfolioDonutChart.data.datasets[0];
        portfolioDonutChart.data.labels = labels;
        ds.data = data;
        // Only reset colors if no segment is selected
        if (donutSelectedIndex < 0) {
            ds.backgroundColor = colors;
        }
        portfolioDonutChart.update('none');
        return;
    }

    // Create new chart
    portfolioDonutChart = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors,
                borderWidth: 0,
                borderRadius: 2,
                spacing: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '68%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label: function(context) {
                            const currentAllocs = getChainAllocations();
                            const currentTotal = lastTotalPortfolioValue > 0 ? lastTotalPortfolioValue : currentAllocs.reduce((s, a) => s + a.usd, 0);
                            const alloc = currentAllocs[context.dataIndex];
                            if (!alloc) return '';
                            const pct = ((alloc.usd / currentTotal) * 100).toFixed(1);
                            return `${alloc.symbol}  ${pct}%`;
                        },
                        title: function() { return ''; }
                    },
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    bodyColor: '#fff',
                    bodyFont: { size: 13, weight: 'bold' },
                    padding: { top: 6, bottom: 6, left: 10, right: 10 },
                    cornerRadius: 8,
                    displayColors: true,
                    boxWidth: 10,
                    boxHeight: 10,
                    boxPadding: 4,
                },
            },
            layout: { padding: 4 },
            animation: { duration: 400, easing: 'easeOutQuart' },
            onClick: (evt, elements) => {
                // Recalculate fresh data for current state
                const currentAllocs = getChainAllocations();
                const currentAllocTotal = currentAllocs.reduce((s, a) => s + a.usd, 0);
                const currentDisplayTotal = lastTotalPortfolioValue > 0 ? lastTotalPortfolioValue : currentAllocTotal;

                if (!elements.length) {
                    donutSelectedIndex = -1;
                    resetDonutHighlight();
                    setDonutCenterText('Total Balance', formatUSD(currentDisplayTotal), '');
                    return;
                }
                const idx = elements[0].index;
                if (donutSelectedIndex === idx) {
                    donutSelectedIndex = -1;
                    resetDonutHighlight();
                    setDonutCenterText('Total Balance', formatUSD(currentDisplayTotal), '');
                } else {
                    donutSelectedIndex = idx;
                    highlightDonutSegment(idx);
                    const a = currentAllocs[idx];
                    if (a) {
                        const pct = ((a.usd / currentDisplayTotal) * 100).toFixed(1) + '%';
                        setDonutCenterText(a.label, formatUSD(a.usd), pct);
                    }
                }
            },
            onHover: (evt, elements) => {
                canvas.style.cursor = elements.length ? 'pointer' : 'default';
            }
        }
    });
}

function setDonutCenterText(label, value, sub) {
    const labelEl = document.getElementById('donutCenterLabel');
    const valueEl = document.getElementById('donutCenterValue');
    const subEl = document.getElementById('donutCenterSub');
    if (labelEl) labelEl.textContent = label;
    if (valueEl) valueEl.textContent = value;
    if (subEl) subEl.textContent = sub;
}

function highlightDonutSegment(activeIdx) {
    if (!portfolioDonutChart) return;
    const ds = portfolioDonutChart.data.datasets[0];
    const allocations = getChainAllocations();
    const newColors = allocations.map((a, i) => {
        if (i === activeIdx) return a.color;
        return a.color + '40'; // Dim non-selected segments
    });
    const newBorderWidths = allocations.map((_, i) => i === activeIdx ? 3 : 0);
    const newBorderColors = allocations.map((_, i) => i === activeIdx ? '#ffffff' : 'transparent');
    ds.backgroundColor = newColors;
    ds.borderWidth = newBorderWidths;
    ds.borderColor = newBorderColors;
    portfolioDonutChart.update('none');
}

function resetDonutHighlight() {
    if (!portfolioDonutChart) return;
    const ds = portfolioDonutChart.data.datasets[0];
    const allocations = getChainAllocations();
    ds.backgroundColor = allocations.map(a => a.color);
    ds.borderWidth = 0;
    ds.borderColor = 'transparent';
    portfolioDonutChart.update('none');
}

// Restore cached portfolio total for instant display on page load (before API calls complete)
function restoreCachedPortfolioTotal() {
    try {
        const cached = JSON.parse(localStorage.getItem('cachedPortfolioTotal'));
        if (!cached || !cached.total) return;
        // Only use cache if less than 24 hours old
        if (Date.now() - cached.timestamp > 86400000) return;
        const totalValueEl = document.getElementById('totalPortfolioValue');
        if (totalValueEl) setSafeHTML(totalValueEl, formatUSDBlur(cached.total));
    } catch (e) { /* parse error or missing */ }
}

// Get top N holdings by USD value from wallet/staking/defi data
function getTopHoldings(count = 3) {
    const holdings = {};

    // Wallet holdings
    for (const [symbol, amount] of Object.entries(walletTotals)) {
        const priceKey = symbol === 'ETH_BASE' ? 'ETH' : symbol;
        const price = prices[priceKey] || 0;
        const usdValue = amount * price;
        if (usdValue > 0) {
            const key = priceKey; // Merge ETH_BASE into ETH
            holdings[key] = (holdings[key] || 0) + usdValue;
        }
    }

    // Staking holdings
    for (const [token, amount] of Object.entries(stakingTotals)) {
        const price = prices[token] || 0;
        const usdValue = amount * price;
        if (usdValue > 0) {
            holdings[token] = (holdings[token] || 0) + usdValue;
        }
    }

    // DeFi holdings
    for (const [token, amount] of Object.entries(defiTotals)) {
        const price = prices[token] || 0;
        const usdValue = amount * price;
        if (usdValue > 0) {
            holdings[token] = (holdings[token] || 0) + usdValue;
        }
    }

    // Sort by USD value descending, take top N
    return Object.entries(holdings)
        .map(([symbol, usdValue]) => ({
            symbol,
            usdValue,
            price: prices[symbol] || 0,
            change24h: priceData[symbol]?.usd_24h_change || 0
        }))
        .sort((a, b) => b.usdValue - a.usdValue)
        .slice(0, count);
}

// Render top holdings pills into the portfolio card
function renderTopHoldings() {
    const container = document.getElementById('topHoldings');
    if (!container) return;

    const top = getTopHoldings(3);
    if (top.length === 0) {
        container.innerHTML = '';
        return;
    }

    const pills = top.map(h => {
        const priceStr = h.price >= 1000 ? '$' + h.price.toLocaleString(undefined, { maximumFractionDigits: 0 })
            : h.price >= 1 ? '$' + h.price.toFixed(2)
            : '$' + h.price.toFixed(4);
        const changeStr = (h.change24h >= 0 ? '+' : '') + h.change24h.toFixed(1) + '%';
        const changeClass = h.change24h >= 0 ? 'positive' : 'negative';
        return `<span class="top-holding-item">` +
            `<span class="holding-symbol">${h.symbol}</span> ` +
            `<span class="holding-price blur-value">${priceStr}</span> ` +
            `<span class="holding-change ${changeClass} blur-value">${changeStr}</span>` +
            `</span>`;
    }).join('');

    setSafeHTML(container, pills);
}

// Load and display global crypto market cap with 24h change
async function loadGlobalMarketCap() {
    const container = document.getElementById('globalMarketStat');
    if (!container) return;

    try {
        const response = await authFetch(`${API_BASE}/prices/global`);
        if (!response.ok) throw new Error('API error');
        const data = await response.json();

        const mcap = data.total_market_cap_usd || 0;
        const change = data.market_cap_change_percentage_24h || 0;

        if (mcap === 0) {
            container.innerHTML = '';
            return;
        }

        // Format market cap (trillions)
        let mcapStr;
        if (mcap >= 1e12) {
            mcapStr = '$' + (mcap / 1e12).toFixed(2) + 'T';
        } else if (mcap >= 1e9) {
            mcapStr = '$' + (mcap / 1e9).toFixed(1) + 'B';
        } else {
            mcapStr = '$' + (mcap / 1e6).toFixed(0) + 'M';
        }

        const changeStr = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
        const changeClass = change >= 0 ? 'positive' : 'negative';

        setSafeHTML(container,
            `<span class="global-mcap-label">Crypto Market Cap</span>` +
            `<span class="global-mcap-value">${mcapStr}</span>` +
            `<span class="global-mcap-change ${changeClass}">${changeStr}</span>`
        );
    } catch (e) {
        console.error('[Global] Failed to load market cap:', e);
    }
}

// Load 7-day portfolio change from balance history
async function load7DayPortfolioChange() {
    const valueEl = document.getElementById('change7dValue');
    const pctEl = document.getElementById('change7dPercent');
    if (!valueEl) return;

    try {
        const response = await authFetch(`${API_BASE}/balance-history/data?range=1w`);
        if (!response.ok) throw new Error('API error');
        const result = await response.json();

        if (!result.data || result.data.length < 2) {
            valueEl.textContent = '--';
            if (pctEl) pctEl.textContent = '';
            return;
        }

        const firstValue = result.data[0].total_value ?? result.data[0].value;
        const lastValue = result.data[result.data.length - 1].total_value ?? result.data[result.data.length - 1].value;
        const dollarChange = lastValue - firstValue;
        const pctChange = firstValue > 0 ? (dollarChange / firstValue) * 100 : 0;
        const isPositive = dollarChange >= 0;
        const sign = isPositive ? '+' : '';

        valueEl.textContent = (isPositive ? '+' : '-') + formatUSD(Math.abs(dollarChange));
        valueEl.className = 'stat-value ' + (isPositive ? 'positive' : 'negative');

        if (pctEl) {
            pctEl.textContent = sign + pctChange.toFixed(1) + '%';
            pctEl.className = 'stat-sub ' + (isPositive ? 'positive' : 'negative');
        }
    } catch (e) {
        console.error('[Portfolio] Failed to load 7-day change:', e);
        valueEl.textContent = '--';
        valueEl.className = 'stat-value';
        if (pctEl) { pctEl.textContent = ''; pctEl.className = 'stat-sub'; }
    }
}

// Load 7-day transaction count
async function load7DayTransactionCount() {
    const el = document.getElementById('txCount7dValue');
    if (!el) return;

    try {
        const response = await authFetch(`${API_BASE}/transactions/stats?days=7`);
        if (!response.ok) throw new Error('API error');
        const data = await response.json();
        el.textContent = (data.total_transactions || 0).toLocaleString();
    } catch (e) {
        console.error('[Portfolio] Failed to load 7-day tx count:', e);
        el.textContent = '--';
    }
}

// Load portfolio component totals from latest snapshot (lightweight, no external API calls)
async function loadPortfolioTotals() {
    try {
        const response = await authFetch(`${API_BASE}/portfolio/totals`);
        if (!response.ok) return;
        const data = await response.json();

        // Populate staking/defi totals as USD values for portfolio calculation
        // Store as special keys that updateTotalPortfolioValue can use
        snapshotTotals.staking = data.staking_usd || 0;
        snapshotTotals.defi = data.defi_usd || 0;
        snapshotTotals.trackedTokens = data.tracked_tokens_usd || 0;

        console.log(`[Overview] Snapshot totals: staking=$${data.staking_usd?.toFixed(2)}, defi=$${data.defi_usd?.toFixed(2)}, exchange=$${data.exchange_usd?.toFixed(2)}, nft=$${data.nft_usd?.toFixed(2)}`);
        updateTotalPortfolioValue();
    } catch (e) {
        console.error('[Overview] Failed to load portfolio totals:', e);
    }
}

// Lightweight staking fetch for Overview page (populates stakingTotals without rendering UI)
async function loadStakingTotalsForOverview() {
    try {
        const walletsResponse = await authFetch(`${API_BASE}/wallets`);
        const walletsData = await walletsResponse.json();
        const cardanoWallets = walletsData.wallets.filter(w => w.blockchain === 'cardano');
        if (cardanoWallets.length === 0) return;

        const newTotals = {};
        const results = await Promise.all(
            cardanoWallets.map(wallet =>
                authFetch(`${API_BASE}/defi/staking/${wallet.address}`)
                    .then(r => r.json())
                    .catch(() => null)
            )
        );
        for (const data of results) {
            if (!data) continue;
            for (const [protocol, pData] of Object.entries(data.protocols || {})) {
                for (const stake of (pData.staked || [])) {
                    const token = stake.token || 'ADA';
                    newTotals[token] = (newTotals[token] || 0) + (stake.amount || 0);
                }
                if (pData.reward_token && pData.pending_rewards > 0) {
                    newTotals[pData.reward_token] = (newTotals[pData.reward_token] || 0) + pData.pending_rewards;
                }
            }
        }

        if (Object.keys(newTotals).length > 0) {
            stakingTotals = newTotals;
            console.log('[Overview] Staking totals loaded:', stakingTotals);
            updateTotalPortfolioValue();
        }
    } catch (e) {
        console.debug('[Overview] Could not load staking totals:', e);
    }
}

// DOM Elements
const refreshBtn = document.getElementById('refreshBtn');
const statusBar = document.getElementById('statusBar');
const statusMessage = document.getElementById('statusMessage');
const adaBalance = document.getElementById('adaBalance');
const btcBalance = document.getElementById('btcBalance');
const cardanoWallets = document.getElementById('cardanoWallets');
const bitcoinWallets = document.getElementById('bitcoinWallets');
const cardanoAssets = document.getElementById('cardanoAssets');
const walletsList = document.getElementById('walletsList');
const assetsList = document.getElementById('assetsList');
const addWalletForm = document.getElementById('addWalletForm');
const ethBalance = document.getElementById('ethBalance');
const ethereumWallets = document.getElementById('ethereumWallets');
const ethereumTokens = document.getElementById('ethereumTokens');
const defiProtocolCount = document.getElementById('defiProtocolCount');
const defiWalletCount = document.getElementById('defiWalletCount');
const defiCategories = document.getElementById('defiCategories');
const stakingPositions = document.getElementById('stakingPositions');

// Toggle collapsible section
function toggleSection(header) {
    const section = header.closest('.collapsible-section');
    section.classList.toggle('collapsed');
}

// Toggle hidden stablecoins dropdown
function toggleHiddenStables(button) {
    const dropdown = button.closest('.hidden-stables-dropdown');
    const content = dropdown.querySelector('.hidden-stables-content');
    const icon = button.querySelector('.toggle-icon');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.textContent = '▼';
        dropdown.classList.add('expanded');
    } else {
        content.style.display = 'none';
        icon.textContent = '▶';
        dropdown.classList.remove('expanded');
    }
}

// Track sections state
let sectionsExpanded = false;

// Toggle all collapsible sections
function toggleAllSections() {
    const btn = document.getElementById('sectionsToggleBtn');

    if (sectionsExpanded) {
        // Collapse all
        document.querySelectorAll('.collapsible-section').forEach(section => {
            section.classList.add('collapsed');
        });
        document.querySelectorAll('.wallet-group').forEach(group => {
            group.classList.add('collapsed');
        });
        if (btn) btn.textContent = 'Expand All';
        sectionsExpanded = false;
    } else {
        // Expand all
        document.querySelectorAll('.collapsible-section').forEach(section => {
            section.classList.remove('collapsed');
        });
        document.querySelectorAll('.wallet-group').forEach(group => {
            group.classList.remove('collapsed');
        });
        if (btn) btn.textContent = 'Collapse All';
        sectionsExpanded = true;
    }
}

// Expand all collapsible sections
function expandAllSections() {
    document.querySelectorAll('.collapsible-section').forEach(section => {
        section.classList.remove('collapsed');
    });
    document.querySelectorAll('.wallet-group').forEach(group => {
        group.classList.remove('collapsed');
    });
    sectionsExpanded = true;
    const btn = document.getElementById('sectionsToggleBtn');
    if (btn) btn.textContent = 'Collapse All';
}

// Collapse all collapsible sections
function collapseAllSections() {
    document.querySelectorAll('.collapsible-section').forEach(section => {
        section.classList.add('collapsed');
    });
    document.querySelectorAll('.wallet-group').forEach(group => {
        group.classList.add('collapsed');
    });
    sectionsExpanded = false;
    const btn = document.getElementById('sectionsToggleBtn');
    if (btn) btn.textContent = 'Expand All';
}

// Privacy mode link protection - prevents browser status bar from showing sensitive URLs
const PRIVACY_LINK_SELECTOR = [
    'a.explorer-link',
    'a.gov-link',
    'a.nft-link',
    'a.hash-link',
    'a.defi-gov-link',
    'a.gov-vote-link',
    'a.action-link',
    'a.rewards-page-link'
].join(', ');

let privacyObserver = null;

function stripPrivacyLinks(root = document) {
    root.querySelectorAll(PRIVACY_LINK_SELECTOR).forEach(link => {
        if (link.getAttribute('href') && link.getAttribute('href') !== '#' && !link.hasAttribute('data-href')) {
            link.setAttribute('data-href', link.getAttribute('href'));
            link.removeAttribute('href');
        }
    });
}

function restorePrivacyLinks() {
    document.querySelectorAll('a[data-href]').forEach(link => {
        link.setAttribute('href', link.getAttribute('data-href'));
        link.removeAttribute('data-href');
    });
}

function startPrivacyObserver() {
    if (privacyObserver) return;
    privacyObserver = new MutationObserver(mutations => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === 1) {
                    if (node.matches && node.matches(PRIVACY_LINK_SELECTOR)) {
                        if (node.getAttribute('href') && node.getAttribute('href') !== '#' && !node.hasAttribute('data-href')) {
                            node.setAttribute('data-href', node.getAttribute('href'));
                            node.removeAttribute('href');
                        }
                    }
                    if (node.querySelectorAll) {
                        stripPrivacyLinks(node);
                    }
                }
            }
        }
    });
    privacyObserver.observe(document.body, { childList: true, subtree: true });
}

function stopPrivacyObserver() {
    if (privacyObserver) {
        privacyObserver.disconnect();
        privacyObserver = null;
    }
}

// Delegated click handler for privacy-stripped links
document.addEventListener('click', (e) => {
    const link = e.target.closest('a[data-href]');
    if (link) {
        e.preventDefault();
        window.open(link.getAttribute('data-href'), '_blank', 'noopener');
    }
});

// Initialize privacy mode from localStorage
function initializePrivacyMode() {
    const privacyEnabled = localStorage.getItem('privacyMode') === 'true';
    if (privacyEnabled) {
        document.body.classList.add('privacy-mode');
        const btn = document.getElementById('privacyBtn');
        if (btn) btn.classList.add('active');
        // Defer link stripping to after initial render
        requestAnimationFrame(() => {
            stripPrivacyLinks();
            startPrivacyObserver();
        });
    }
}

// Toggle privacy mode
function togglePrivacyMode() {
    const body = document.body;
    const isEnabled = body.classList.toggle('privacy-mode');

    // Legacy button support
    const btn = document.getElementById('privacyBtn');
    if (btn) btn.classList.toggle('active', isEnabled);

    // Sync avatar dropdown indicator
    if (typeof syncPrivacyIndicator === 'function') {
        syncPrivacyIndicator();
    }

    // Close user menu if open
    if (typeof closeUserMenu === 'function') {
        closeUserMenu();
    }

    // Strip or restore link hrefs to prevent status bar URL preview
    if (isEnabled) {
        stripPrivacyLinks();
        startPrivacyObserver();
    } else {
        stopPrivacyObserver();
        restorePrivacyLinks();
    }

    // Save to localStorage
    localStorage.setItem('privacyMode', isEnabled);
}

// Listen for storage events to sync privacy mode across tabs
window.addEventListener('storage', (e) => {
    if (e.key === 'privacyMode') {
        const privacyEnabled = e.newValue === 'true';
        document.body.classList.toggle('privacy-mode', privacyEnabled);
        const btn = document.getElementById('privacyBtn');
        if (btn) btn.classList.toggle('active', privacyEnabled);

        // Sync link stripping across tabs
        if (privacyEnabled) {
            stripPrivacyLinks();
            startPrivacyObserver();
        } else {
            stopPrivacyObserver();
            restorePrivacyLinks();
        }
    }
});

// Legacy waffle menu (no longer used - replaced by horizontal nav + avatar dropdown)
function toggleWaffleMenu() {
    // No-op for backward compatibility
}

// Show status message
function showStatus(message, isError = false) {
    if (!statusMessage || !statusBar) {
        console.log(`Status: ${message}${isError ? ' (error)' : ''}`);
        return;
    }
    statusMessage.textContent = message;
    statusBar.classList.remove('hidden', 'error');
    if (isError) {
        statusBar.classList.add('error');
    }
    // Auto-hide after 5 seconds
    setTimeout(() => {
        statusBar.classList.add('hidden');
    }, 5000);
}

// Format address for display
function formatAddress(address) {
    if (address.length > 14) {
        return `${address.slice(0, 8)}...${address.slice(-4)}`;
    }
    return address;
}

function formatAddressDisplay(address, blockchain) {
    if (!address) return '';
    if (address.length <= 14) return address;
    return `${address.slice(0, 8)}...${address.slice(-4)}`;
}

function copyToClipboard(text, button) {
    // Try modern clipboard API first (requires HTTPS)
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            showCopySuccess(button);
        }).catch(err => {
            console.error('Failed to copy:', err);
            fallbackCopy(text, button);
        });
    } else {
        // Fallback for HTTP (Docker deployments)
        fallbackCopy(text, button);
    }
}

function fallbackCopy(text, button) {
    // Create temporary textarea for copying
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();

    try {
        document.execCommand('copy');
        showCopySuccess(button);
    } catch (err) {
        console.error('Fallback copy failed:', err);
        alert('Copied to clipboard: ' + text);
    } finally {
        document.body.removeChild(textarea);
    }
}

function showCopySuccess(button) {
    const originalHTML = button.innerHTML;
    button.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
    `;
    setTimeout(() => {
        button.innerHTML = originalHTML;
    }, 1500);
}

// Load portfolio summary
async function loadPortfolioSummary() {
    try {
        const response = await authFetch(`${API_BASE}/portfolio/summary`);
        const data = await response.json();

        // Debug logging
        console.log('[Portfolio] Data loaded:', {
            from_cache: data.from_cache,
            last_updated: data.last_updated,
            cardano_ada: data.cardano?.total_ada,
            bitcoin_btc: data.bitcoin?.total_btc,
            current_prices: prices
        });

        // Update last updated timestamp
        if (data.last_updated) {
            const lastUpdatedEl = document.getElementById('lastUpdated');
            if (lastUpdatedEl) {
                const lastUpdate = new Date(data.last_updated);
                const now = new Date();
                const diffMinutes = Math.floor((now - lastUpdate) / 60000);

                let timeAgo;
                if (diffMinutes < 1) {
                    timeAgo = 'just now';
                } else if (diffMinutes < 60) {
                    timeAgo = `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
                } else if (diffMinutes < 1440) {
                    const hours = Math.floor(diffMinutes / 60);
                    timeAgo = `${hours} hour${hours > 1 ? 's' : ''} ago`;
                } else {
                    const days = Math.floor(diffMinutes / 1440);
                    timeAgo = `${days} day${days > 1 ? 's' : ''} ago`;
                }

                lastUpdatedEl.textContent = `Last updated: ${timeAgo}`;
                lastUpdatedEl.title = `${lastUpdate.toLocaleString()}`;
            }
        }

        // Store portfolio data for donut chart
        lastPortfolioData = data;

        // Store wallet totals for portfolio calculation
        walletTotals.ADA = data.cardano.total_ada;
        walletTotals.BTC = data.bitcoin.total_btc;
        walletTotals.ETH = data.ethereum?.total_eth || 0;
        walletTotals.SOL = data.solana?.total_sol || 0;
        walletTotals.MATIC = data.polygon?.total_matic || 0;
        walletTotals.ETH_BASE = data.base?.total_eth || 0;
        walletTotals.ALGO = data.algorand?.total_algo || 0;
        walletTotals.BNB = data.bsc?.total_bnb || 0;
        walletTotals.ETH_ARB = data.arbitrum?.total_eth || 0;
        walletTotals.AVAX = data.avalanche?.total_avax || 0;
        walletTotals.TRX = data.tron?.total_trx || 0;
        walletTotals.XRP = data.xrp?.total_xrp || 0;
        walletTotals.HBAR = data.hedera?.total_hbar || 0;
        walletTotals.EGLD = data.multiversx?.total_egld || 0;
        walletTotals.SUI = data.sui?.total_sui || 0;
        walletTotals.APT = data.aptos?.total_apt || 0;
        walletTotals.FIL = data.filecoin?.total_fil || 0;
        walletTotals.LTC = data.litecoin?.total_ltc || 0;
        walletTotals.DOGE = data.dogecoin?.total_doge || 0;
        walletTotals.ZEC = data.zcash?.total_zec || 0;
        walletTotals.XTZ = data.tezos?.total_xtz || 0;
        walletTotals.STX = data.stacks?.total_stx || 0;
        walletTotals.VET = data.vechain?.total_vet || 0;
        walletTotals.ATOM = data.cosmos?.total_atom || 0;
        walletTotals.NEAR = data.near?.total_near || 0;
        walletTotals.ICP = data.icp?.total_icp || 0;
        walletTotals.OSMO = data.osmosis?.total_osmo || 0;
        walletTotals.TIA = data.celestia?.total_tia || 0;
        walletTotals.INJ = data.injective?.total_inj || 0;
        walletTotals.DYDX = data.dydx?.total_dydx || 0;
        walletTotals.SEI = data.sei?.total_sei || 0;
        walletTotals.AKT = data.akash?.total_akt || 0;
        walletTotals.TON = data.ton?.total_ton || 0;
        walletTotals.DOT = data.polkadot?.total_dot || 0;
        walletTotals.KSM = data.kusama?.total_ksm || 0;
        walletTotals.XLM = data.stellar?.total_xlm || 0;
        walletTotals.KAS = data.kaspa?.total_kas || 0;
        walletTotals.KLAY = data.kaia?.total_klay || 0;
        walletTotals.ERG = data.ergo?.total_erg || 0;
        walletTotals.IOTA = data.iota?.total_iota || 0;
        walletTotals.WAVES = data.waves?.total_waves || 0;
        walletTotals.MINA = data.mina?.total_mina || 0;
        walletTotals.ZIL = data.zilliqa?.total_zil || 0;

        // Render blockchain cards dynamically (sorted by value, only chains with wallets)
        renderBlockchainCards(data);

        // Update Sankey flow diagram if initialized
        if (window.portfolioSankey) {
            const allocs = getChainAllocations();
            const total = allocs.reduce((sum, a) => sum + a.usd, 0);
            window.portfolioSankey.setData(total, allocs, lastPortfolioData, prices);
            window.portfolioSankey.render();
        }

        // Refresh streamgraph with current range
        if (window.portfolioStream) {
            window.portfolioStream.loadData(window.portfolioStream.activeRange);
        }

        // Update wallets section summary - overlapping chain icons
        const stakeGroupCount = data.cardano.stake_groups?.length || 0;
        const ethWalletCount = data.ethereum?.wallet_count || 0;
        const solWalletCount = data.solana?.wallet_count || 0;
        const polygonWalletCount = data.polygon?.wallet_count || 0;
        const baseWalletCount = data.base?.wallet_count || 0;
        const algoWalletCount = data.algorand?.wallet_count || 0;
        const bscWalletCount = data.bsc?.wallet_count || 0;
        const arbWalletCount = data.arbitrum?.wallet_count || 0;
        const avaxWalletCount = data.avalanche?.wallet_count || 0;
        const tronWalletCount = data.tron?.wallet_count || 0;
        const walletsSummary = document.getElementById('walletsSummary');
        if (walletsSummary) {
            const chainIconMap = {
                'Cardano': 'ADA', 'Bitcoin': 'BTC', 'Ethereum': 'ETH',
                'Solana': 'SOL', 'Polygon': 'MATIC', 'Algorand': 'ALGO',
                'BNB Chain': 'BNB', 'Arbitrum': 'ARB', 'Avalanche': 'AVAX', 'Tron': 'TRX'
            };
            const chainCustomLogoMap = {
                'Base': 'https://avatars.githubusercontent.com/u/108554348?s=28'
            };
            const chains = [];
            if (stakeGroupCount > 0) chains.push({ name: 'Cardano', count: stakeGroupCount, label: `${stakeGroupCount} stake key${stakeGroupCount !== 1 ? 's' : ''}` });
            if (data.bitcoin.wallet_count > 0) chains.push({ name: 'Bitcoin', count: data.bitcoin.wallet_count, label: `${data.bitcoin.wallet_count} wallet${data.bitcoin.wallet_count !== 1 ? 's' : ''}` });
            if (ethWalletCount > 0) chains.push({ name: 'Ethereum', count: ethWalletCount, label: `${ethWalletCount} wallet${ethWalletCount !== 1 ? 's' : ''}` });
            if (solWalletCount > 0) chains.push({ name: 'Solana', count: solWalletCount, label: `${solWalletCount} wallet${solWalletCount !== 1 ? 's' : ''}` });
            if (polygonWalletCount > 0) chains.push({ name: 'Polygon', count: polygonWalletCount, label: `${polygonWalletCount} wallet${polygonWalletCount !== 1 ? 's' : ''}` });
            if (baseWalletCount > 0) chains.push({ name: 'Base', count: baseWalletCount, label: `${baseWalletCount} wallet${baseWalletCount !== 1 ? 's' : ''}` });
            if (algoWalletCount > 0) chains.push({ name: 'Algorand', count: algoWalletCount, label: `${algoWalletCount} wallet${algoWalletCount !== 1 ? 's' : ''}` });
            if (bscWalletCount > 0) chains.push({ name: 'BNB Chain', count: bscWalletCount, label: `${bscWalletCount} wallet${bscWalletCount !== 1 ? 's' : ''}` });
            if (arbWalletCount > 0) chains.push({ name: 'Arbitrum', count: arbWalletCount, label: `${arbWalletCount} wallet${arbWalletCount !== 1 ? 's' : ''}` });
            if (avaxWalletCount > 0) chains.push({ name: 'Avalanche', count: avaxWalletCount, label: `${avaxWalletCount} wallet${avaxWalletCount !== 1 ? 's' : ''}` });
            if (tronWalletCount > 0) chains.push({ name: 'Tron', count: tronWalletCount, label: `${tronWalletCount} wallet${tronWalletCount !== 1 ? 's' : ''}` });

            const maxVisible = 4;
            let summaryHtml = '<span class="chain-icons-stack">';
            chains.slice(0, maxVisible).forEach(chain => {
                const customLogo = chainCustomLogoMap[chain.name];
                const logoSrc = customLogo || getLogoKitUrl(chainIconMap[chain.name] || chain.name, 28);
                summaryHtml += `<img src="${logoSrc}" alt="${chain.name}" title="${chain.name}: ${chain.label}" class="chain-icon-circle" onerror="this.style.display='none'">`;
            });
            if (chains.length > maxVisible) {
                summaryHtml += `<span class="chain-icon-overflow" title="${chains.slice(maxVisible).map(c => c.name).join(', ')}">+${chains.length - maxVisible}</span>`;
            }
            summaryHtml += '</span>';
            setSafeHTML(walletsSummary, summaryHtml);
            // Fix onerror stripped by DOMPurify
            walletsSummary.querySelectorAll('img.chain-icon-circle').forEach(img => {
                img.addEventListener('error', () => { img.style.display = 'none'; });
            });
        }

        // Render wallets list with stake groups for Cardano
        renderWalletsGrouped(data.cardano.stake_groups || [], data.bitcoin.wallets || [], data.ethereum?.wallets || [], data.solana?.wallets || [], data.polygon?.wallets || [], data.base?.wallets || [], data.algorand?.wallets || [], data.bsc?.wallets || [], data.arbitrum?.wallets || [], data.avalanche?.wallets || [], data.tron?.wallets || []);

        // Update total portfolio value
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading portfolio summary:', error);
        showStatus('Failed to load portfolio summary', true);
    }
}

// Render wallets list
function renderWallets(wallets) {
    if (wallets.length === 0) {
        setSafeHTML(walletsList, '<p class="empty-state">No wallets found. Add addresses to data/wallets.txt and click "Sync from File".</p>');
        return;
    }

    // Sort by blockchain then by balance
    wallets.sort((a, b) => {
        // First sort by blockchain (cardano first)
        const chainA = a.address.startsWith('addr1') ? 'cardano' : 'bitcoin';
        const chainB = b.address.startsWith('addr1') ? 'cardano' : 'bitcoin';
        if (chainA !== chainB) return chainA === 'cardano' ? -1 : 1;
        // Then sort by balance (descending)
        return (b.balance || 0) - (a.balance || 0);
    });

    setSafeHTML(walletsList, wallets.map(wallet => {
        const blockchain = wallet.address.startsWith('addr1') ? 'cardano' : 'bitcoin';
        const unit = blockchain === 'cardano' ? 'ADA' : 'BTC';
        const decimals = blockchain === 'cardano' ? 6 : 8;
        const balanceNum = wallet.balance || 0;
        const balance = balanceNum.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: decimals});
        const assetsInfo = wallet.native_assets_count ? `${wallet.native_assets_count} assets` : '';

        // Calculate USD value
        const priceKey = blockchain === 'cardano' ? 'ADA' : 'BTC';
        const usdValue = balanceNum * (prices[priceKey] || 0);
        const usdFormatted = formatUSD(usdValue);

        // External explorer links based on blockchain
        let explorerLinks = '';
        if (blockchain === 'cardano') {
            explorerLinks = `
                <div class="wallet-explorers">
                    <a href="https://adastat.net/addresses/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on AdaStat">
                        <span class="explorer-icon adastat">AS</span>
                    </a>
                    <a href="https://beta.cexplorer.io/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on cexplorer">
                        <span class="explorer-icon cexplorer">CX</span>
                    </a>
                    <a href="https://www.taptools.io/portfolio?address=${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on TapTools">
                        <span class="explorer-icon taptools">TT</span>
                    </a>
                </div>
            `;
        } else if (blockchain === 'bitcoin') {
            explorerLinks = `
                <div class="wallet-explorers">
                    <a href="https://mempool.space/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on Mempool">
                        <span class="explorer-icon mempool">MP</span>
                    </a>
                    <a href="https://blockstream.info/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on Blockstream">
                        <span class="explorer-icon blockstream">BS</span>
                    </a>
                    <a href="https://www.blockchain.com/explorer/addresses/btc/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on Blockchain.com">
                        <span class="explorer-icon blockchain">BC</span>
                    </a>
                </div>
            `;
        } else if (blockchain === 'ethereum') {
            explorerLinks = `
                <div class="wallet-explorers">
                    <a href="https://etherscan.io/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on Etherscan">
                        <span class="explorer-icon etherscan">ES</span>
                    </a>
                    <a href="https://debank.com/profile/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on DeBank">
                        <span class="explorer-icon debank">DB</span>
                    </a>
                    <a href="https://zapper.xyz/account/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="Click here to view this wallet on Zapper">
                        <span class="explorer-icon zapper">ZP</span>
                    </a>
                </div>
            `;
        }

        // Governance section placeholder for Cardano
        const govSection = blockchain === 'cardano' ? `
            <div class="wallet-governance" id="gov-${wallet.address.slice(0, 20)}">
                <div class="gov-loading">Loading staking info...</div>
            </div>
        ` : '';

        return `
            <div class="wallet-item ${blockchain}" data-address="${wallet.address}">
                <div class="wallet-info">
                    <div class="wallet-label-container">
                        <span class="wallet-label">${wallet.label || blockchain.charAt(0).toUpperCase() + blockchain.slice(1) + ' Wallet'}</span>
                        <button class="edit-label-btn" onclick="editWalletLabel('${wallet.address}', this)" title="Edit wallet name">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>
                    </div>
                    <span class="wallet-address">${formatAddress(wallet.address)}</span>
                    ${explorerLinks}
                    ${govSection}
                </div>
                <div class="wallet-balance">
                    <div class="amount">${balance} ${unit}</div>
                    <div class="amount-usd">${usdFormatted}</div>
                    ${assetsInfo ? `<div class="assets">${assetsInfo}</div>` : ''}
                </div>
            </div>
        `;
    }).join(''));

    // Load governance info for Cardano wallets
    loadWalletGovernanceInfo(wallets.filter(w => w.address.startsWith('addr1')));
}

// Render wallets grouped by stake key (Cardano) and individual (Bitcoin, Ethereum, Solana, Polygon, Base)
// Populate chain filter tabs dynamically based on which chains have wallets
function updateChainFilterTabs(chainData) {
    const container = document.getElementById('selfCustodyChainTabs');
    if (!container) return;

    const chainDisplayNames = {
        cardano: 'Cardano', bitcoin: 'Bitcoin', ethereum: 'Ethereum',
        solana: 'Solana', polygon: 'Polygon', base: 'Base',
        algorand: 'Algorand', bsc: 'BNB Chain', arbitrum: 'Arbitrum',
        avalanche: 'Avalanche', tron: 'Tron', xrp: 'XRP',
        hedera: 'Hedera', multiversx: 'MultiversX', sui: 'Sui',
        aptos: 'Aptos', filecoin: 'Filecoin', litecoin: 'Litecoin',
        dogecoin: 'Dogecoin', zcash: 'Zcash', tezos: 'Tezos',
        stacks: 'Stacks', vechain: 'VeChain', cosmos: 'Cosmos',
        near: 'NEAR', icp: 'ICP'
    };

    const activeChains = Object.entries(chainData)
        .filter(([_, wallets]) => wallets && wallets.length > 0)
        .map(([chain]) => chain);

    if (activeChains.length <= 1) {
        container.style.display = 'none';
        return;
    }

    container.style.display = '';
    let html = '<button class="chain-tab active" data-chain="all" onclick="filterSelfCustodyByChain(\'all\')">All</button>';
    activeChains.forEach(chain => {
        html += `<button class="chain-tab" data-chain="${chain}" onclick="filterSelfCustodyByChain('${chain}')">${chainDisplayNames[chain] || chain}</button>`;
    });
    container.innerHTML = html;
}

function renderWalletsGrouped(cardanoStakeGroups, bitcoinWallets, ethereumWallets = [], solanaWallets = [], polygonWallets = [], baseWallets = [], algorandWallets = [], bscWallets = [], arbitrumWallets = [], avalancheWallets = [], tronWallets = []) {
    if (!walletsList) return;

    const allEmpty = cardanoStakeGroups.length === 0 && bitcoinWallets.length === 0 && ethereumWallets.length === 0 && solanaWallets.length === 0 && polygonWallets.length === 0 && baseWallets.length === 0 && algorandWallets.length === 0 && bscWallets.length === 0 && arbitrumWallets.length === 0 && avalancheWallets.length === 0 && tronWallets.length === 0;

    if (allEmpty) {
        setSafeHTML(walletsList, '<p class="empty-state">No wallets found. Add addresses to data/wallets.txt and click "Sync from File".</p>');
        return;
    }

    let html = '';

    // Cardano Section
    if (cardanoStakeGroups.length > 0) {
        const totalCardanoAda = cardanoStakeGroups.reduce((sum, g) => sum + g.total_ada, 0);
        const totalCardanoUsd = totalCardanoAda * (prices.ADA || 0);
        const totalCardanoAssets = cardanoStakeGroups.reduce((sum, g) => sum + g.total_assets, 0);
        const nativeAssetsValueUsd = cardanoStakeGroups.reduce((sum, g) => sum + (g.native_assets_value_usd || 0), 0);

        html += `
            <div class="blockchain-section cardano collapsed" data-chain="cardano">
                <div class="blockchain-section-header">
                    <div class="blockchain-info">
                        <img src="${getLogoKitUrl('ADA', 24)}" alt="Cardano" class="blockchain-logo-small" onerror="this.style.display='none'">
                        <span class="blockchain-name">Cardano</span>
                        <span class="blockchain-stats">${cardanoStakeGroups.length} stake key${cardanoStakeGroups.length !== 1 ? 's' : ''} · ${totalCardanoAssets} asset${totalCardanoAssets !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="blockchain-balance">
                        <div class="amount">${formatCryptoBlur(totalCardanoAda, 'ADA', 6)}</div>
                        <div class="amount-usd">${formatUSDBlur(totalCardanoUsd + nativeAssetsValueUsd)}</div>
                    </div>
                    <span class="collapse-icon">▼</span>
                </div>
                <div class="blockchain-section-content">
        `;

        // Render ALL Cardano wallets in stake key group format
        for (const group of cardanoStakeGroups) {
            const walletCount = group.wallets.length;
            const groupUsdValue = group.total_ada * (prices.ADA || 0);
            const groupNativeAssetsValue = group.native_assets_value_usd || 0;
            const stakeId = group.stake_address ? group.stake_address.slice(0, 20) : 'none';

            html += `
                <div class="wallet-group cardano collapsed ${walletCount === 1 ? 'single-wallet' : ''}" data-stake="${group.stake_address || 'none'}">
                    <div class="wallet-group-header">
                        <div class="group-info">
                            <span class="group-label">${group.label || 'Stake Key'}: <span class="blur-sensitive stake-key-short">${group.stake_address_short || 'No Stake Key'}</span></span>
                            ${group.stake_address ? `<button class="copy-address-btn" data-address="${group.stake_address}" title="Copy stake key">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                            </button>` : ''}
                            <button class="edit-group-label-btn" data-stake="${group.stake_address || 'none'}" title="Edit group name">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                </svg>
                            </button>
                            ${group.stake_address ? `<button class="delete-wallet-btn delete-group-btn" data-stake="${group.stake_address}" title="Delete all wallets in this group">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M3 6h18"></path>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
                                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                            </button>` : ''}
                            <span class="group-wallet-count">${walletCount} address${walletCount !== 1 ? 'es' : ''}</span>
                        </div>
                        <div class="group-balance">
                            <div class="amount">${formatCryptoBlur(group.total_ada, 'ADA', 6)}</div>
                            <div class="amount-usd">${formatUSDBlur(groupUsdValue + groupNativeAssetsValue)}</div>
                        </div>
                        <span class="collapse-icon">▼</span>
                    </div>
                    <div class="stake-governance" id="stake-gov-${stakeId}">
                        <div class="gov-loading">Loading staking info...</div>
                    </div>
                    <div class="wallet-group-content">
            `;

            for (const wallet of group.wallets) {
                html += renderSingleWallet(wallet, 'cardano', true);
            }

            html += `
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    // Helper function to render blockchain section
    function renderBlockchainSection(blockchain, wallets, unit, decimals) {
        if (wallets.length === 0) return '';

        const totalBalance = wallets.reduce((sum, w) => sum + w.balance, 0);
        const totalAssets = wallets.reduce((sum, w) => sum + (w.native_assets_count || w.token_count || w.asset_count || 0), 0);
        const totalNativeAssetsValue = wallets.reduce((sum, w) => sum + (w.native_assets_value_usd || 0), 0);
        const totalUsd = totalBalance * (prices[unit] || 0) + totalNativeAssetsValue;

        const blockchainName = blockchain.charAt(0).toUpperCase() + blockchain.slice(1);

        // Blockchain logo mapping
        const logoMap = {
            'bitcoin': getLogoKitUrl('BTC', 24),
            'ethereum': getLogoKitUrl('ETH', 24),
            'solana': getLogoKitUrl('SOL', 24),
            'polygon': getLogoKitUrl('MATIC', 24),
            'base': 'https://avatars.githubusercontent.com/u/108554348?s=24',
            'algorand': getLogoKitUrl('ALGO', 24),
            'bsc': getLogoKitUrl('BNB', 24),
            'arbitrum': getLogoKitUrl('ARB', 24),
            'avalanche': getLogoKitUrl('AVAX', 24),
            'tron': getLogoKitUrl('TRX', 24),
            'xrp': getLogoKitUrl('XRP', 24),
            'hedera': getLogoKitUrl('HBAR', 24),
            'multiversx': getLogoKitUrl('EGLD', 24),
            'sui': getLogoKitUrl('SUI', 24),
            'aptos': getLogoKitUrl('APT', 24),
            'filecoin': getLogoKitUrl('FIL', 24)
        };
        const logoUrl = logoMap[blockchain] || '';

        return `
            <div class="blockchain-section ${blockchain} collapsed" data-chain="${blockchain}">
                <div class="blockchain-section-header">
                    <div class="blockchain-info">
                        ${logoUrl ? `<img src="${logoUrl}" alt="${blockchainName}" class="blockchain-logo-small" onerror="this.style.display='none'">` : ''}
                        <span class="blockchain-name">${blockchainName}</span>
                        <span class="blockchain-stats">${wallets.length} wallet${wallets.length !== 1 ? 's' : ''} · ${totalAssets} asset${totalAssets !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="blockchain-balance">
                        <div class="amount">${formatCryptoBlur(totalBalance, unit, decimals)}</div>
                        <div class="amount-usd">${formatUSDBlur(totalUsd)}</div>
                    </div>
                    <span class="collapse-icon">▼</span>
                </div>
                <div class="blockchain-section-content">
                    ${wallets.map(w => renderSingleWallet(w, blockchain, false)).join('')}
                </div>
            </div>
        `;
    }

    html += renderBlockchainSection('bitcoin', bitcoinWallets, 'BTC', 8);
    html += renderBlockchainSection('ethereum', ethereumWallets, 'ETH', 8);
    html += renderBlockchainSection('solana', solanaWallets, 'SOL', 9);
    html += renderBlockchainSection('polygon', polygonWallets, 'POL', 6);
    html += renderBlockchainSection('base', baseWallets, 'ETH', 8);
    html += renderBlockchainSection('algorand', algorandWallets, 'ALGO', 6);
    html += renderBlockchainSection('bsc', bscWallets, 'BNB', 8);
    html += renderBlockchainSection('arbitrum', arbitrumWallets, 'ETH', 8);
    html += renderBlockchainSection('avalanche', avalancheWallets, 'AVAX', 8);
    html += renderBlockchainSection('tron', tronWallets, 'TRX', 6);

    // Use innerHTML directly for internally generated HTML (not user input)
    walletsList.innerHTML = html;

    // Populate dynamic chain filter tabs
    updateChainFilterTabs({
        cardano: cardanoStakeGroups,
        bitcoin: bitcoinWallets,
        ethereum: ethereumWallets,
        solana: solanaWallets,
        polygon: polygonWallets,
        base: baseWallets,
        algorand: algorandWallets,
        bsc: bscWallets,
        arbitrum: arbitrumWallets,
        avalanche: avalancheWallets,
        tron: tronWallets
    });

    // Attach event listeners after DOM update
    attachDashboardWalletEventListeners();

    // Load governance info at the stake key level (Cardano only)
    loadStakeKeyGovernanceInfo(cardanoStakeGroups);
}

// Attach event listeners for dashboard wallet buttons
function attachDashboardWalletEventListeners() {
    // Blockchain section toggle listeners
    document.querySelectorAll('.blockchain-section-header').forEach(header => {
        header.addEventListener('click', function() {
            const section = this.closest('.blockchain-section');
            section.classList.toggle('collapsed');
        });
    });

    // Wallet group toggle listeners (Cardano stake keys)
    document.querySelectorAll('.wallet-group-header').forEach(header => {
        header.addEventListener('click', function() {
            toggleWalletGroup(this);
        });
    });

    // Edit label button listeners (individual wallets only, not grouped)
    document.querySelectorAll('.edit-label-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const address = this.closest('[data-address]').dataset.address;
            editWalletLabel(address, this);
        });
    });

    // Edit group label button listeners (stake key groups)
    document.querySelectorAll('.edit-group-label-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const stakeAddress = this.dataset.stake;
            editStakeGroupLabel(stakeAddress, this);
        });
    });

    // Copy address button listeners
    document.querySelectorAll('.copy-address-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const address = this.dataset.address;
            copyToClipboard(address, this);
        });
    });

    // Delete wallet button listeners (individual wallets)
    document.querySelectorAll('.delete-wallet-btn:not(.delete-group-btn)').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const address = this.closest('[data-address]').dataset.address;
            deleteWallet(address);
        });
    });

    // Delete stake group button listeners
    document.querySelectorAll('.delete-group-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const stakeAddress = this.dataset.stake;
            deleteStakeGroup(stakeAddress);
        });
    });

    // Wallet sync button listeners
    document.querySelectorAll('.btn-wallet-sync[data-wallet-sync]').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            syncSingleWallet(this.dataset.walletSync, this);
        });
    });

    // Assets toggle listeners (expand to show individual assets)
    document.querySelectorAll('.assets-toggle').forEach(toggle => {
        toggle.addEventListener('click', async function(event) {
            event.stopPropagation();
            const walletId = this.dataset.walletId;
            await toggleDashboardWalletAssets(walletId);
        });
    });
}

// Sync a single wallet's balance from the blockchain
async function syncSingleWallet(address, btn) {
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="sync-icon spinning">&#8635;</span>';

    // Map unit to price key
    const unitToPriceKey = { ADA: 'ADA', BTC: 'BTC', ETH: 'ETH', SOL: 'SOL', MATIC: 'MATIC', POL: 'MATIC', ALGO: 'ALGO', BNB: 'BNB', AVAX: 'AVAX', TRX: 'TRX' };

    try {
        const response = await authFetch(`${API_BASE}/wallets/${address}/refresh`, {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Refresh failed');

        const data = await response.json();

        if (data.success) {
            // Update the wallet card in-place
            const walletItem = btn.closest('.wallet-item');
            if (walletItem) {
                const amountEl = walletItem.querySelector('.wallet-balance .amount');
                const usdEl = walletItem.querySelector('.wallet-balance .amount-usd');

                if (amountEl && data.balance !== undefined) {
                    setSafeHTML(amountEl, formatCryptoBlur(data.balance, data.unit));
                }
                if (usdEl && data.balance !== undefined) {
                    const priceKey = unitToPriceKey[data.unit] || data.unit;
                    const price = prices[priceKey] || 0;
                    const usdValue = parseFloat(data.balance) * price;
                    setSafeHTML(usdEl, formatUSDBlur(usdValue));
                }
            }

            btn.innerHTML = '<span class="sync-icon">&#10003;</span>';
        } else {
            btn.innerHTML = '<span class="sync-icon">&#10007;</span>';
        }

        setTimeout(() => {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }, 3000);
    } catch (err) {
        console.error('Sync wallet error:', err);
        btn.innerHTML = '<span class="sync-icon">&#10007;</span>';
        setTimeout(() => {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }, 3000);
    }
}

// Toggle wallet assets display on dashboard
async function toggleDashboardWalletAssets(walletId) {
    const container = document.getElementById(`assets-${walletId}`);
    if (!container) return;

    // Toggle visibility
    if (container.style.display === 'block') {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';

    // Check if already loaded
    if (container.dataset.loaded === 'true') return;

    // Fetch assets
    try {
        const response = await authFetch(`${API_BASE}/wallets/id/${walletId}/assets`);
        const data = await response.json();
        let assets = data.assets || [];
        const nativeBalance = data.native_balance;

        if (assets.length === 0 && !nativeBalance) {
            container.innerHTML = '<div style="text-align: center; padding: 10px; color: #888;">No assets found</div>';
        } else {
            const blockchain = data.blockchain || 'cardano';
            const isCardano = blockchain === 'cardano';

            // Sort assets by total_value_usd descending
            assets.sort((a, b) => {
                const aVal = parseFloat(a.total_value_usd) || 0;
                const bVal = parseFloat(b.total_value_usd) || 0;
                return bVal - aVal;
            });

            // Calculate total portfolio value for percentage calculations (include native balance)
            let totalPortfolioValue = 0;
            if (nativeBalance) {
                totalPortfolioValue += parseFloat(nativeBalance.total_value_usd) || 0;
            }
            assets.forEach(asset => {
                totalPortfolioValue += parseFloat(asset.total_value_usd) || 0;
            });

            // Build table layout with native token pricing
            // Determine native token symbol
            const nativeSymbols = {
                'cardano': 'ADA',
                'bitcoin': 'BTC',
                'ethereum': 'ETH',
                'solana': 'SOL',
                'polygon': 'POL',
                'base': 'ETH'
            };
            const nativeSymbol = nativeSymbols[blockchain] || 'Token';

            // Check if we should use table layout (when we have native pricing)
            const useTableLayout = assets.some(a => a.price_native || a.price_ada) || nativeBalance;

            if (useTableLayout) {
                let html = `
                    <div class="assets-table-wrapper">
                        <table class="assets-table">
                            <thead>
                                <tr>
                                    <th>Asset</th>
                                    <th>${nativeSymbol} Price</th>
                                    <th>Owned</th>
                                    <th>${nativeSymbol}</th>
                                    <th>$</th>
                                    <th>% of Portfolio</th>
                                    <th>Ignore</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                // Always show native token first (pinned to top)
                if (nativeBalance) {
                    const actualQty = parseFloat(nativeBalance.actual_quantity) || 0;
                    const totalValueUsd = parseFloat(nativeBalance.total_value_usd) || 0;
                    const percentage = totalPortfolioValue > 0 ? (totalValueUsd / totalPortfolioValue * 100) : 0;

                    const ticker = nativeBalance.ticker || nativeSymbol;
                    const tokenName = nativeBalance.token_name || blockchain;

                    const ownedStr = actualQty.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
                    const totalNativeStr = actualQty.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
                    const totalUsdStr = totalValueUsd > 0 ? '$' + totalValueUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '$0.00';

                    html += `
                        <tr class="native-asset-row">
                            <td class="asset-name-cell">
                                <div class="asset-ticker">${ticker}</div>
                                <div class="asset-name-small">${tokenName}</div>
                            </td>
                            <td>1.000000</td>
                            <td>${ownedStr}</td>
                            <td class="ada-value">${totalNativeStr}</td>
                            <td>${totalUsdStr}</td>
                            <td>
                                <div class="portfolio-bar-wrapper">
                                    <div class="portfolio-bar" style="width: ${percentage}%"></div>
                                    <span class="portfolio-pct">${percentage.toFixed(1)}%</span>
                                </div>
                            </td>
                            <td>
                                <span class="ignore-na">-</span>
                            </td>
                        </tr>
                    `;
                }

                // Then show all other assets sorted by value
                assets.forEach(asset => {
                    const actualQty = parseFloat(asset.actual_quantity) || 0;
                    const ticker = asset.ticker || asset.asset_name?.substring(0, 10) || 'Unknown';
                    const displayName = asset.token_name || asset.asset_name || 'Unknown';
                    const logoUrl = asset.logo_url || '';

                    // Use generic native price or fallback to ADA price for backwards compatibility
                    const priceNative = parseFloat(asset.price_native || asset.price_ada) || 0;
                    const totalNative = parseFloat(asset.total_native || asset.total_ada) || 0;
                    const totalValueUsd = parseFloat(asset.total_value_usd) || 0;

                    // Only show if we have pricing data and value >= $1
                    if (totalValueUsd < 1.00 && priceNative === 0) {
                        return;
                    }

                    // Format values
                    const priceNativeStr = priceNative > 0 ? priceNative.toFixed(6) : 'N/A';
                    const ownedStr = actualQty.toLocaleString('en-US', { maximumFractionDigits: 2 });
                    const totalNativeStr = totalNative > 0 ? totalNative.toLocaleString('en-US', { maximumFractionDigits: 6 }) : '0';
                    const totalUsdStr = totalValueUsd > 0 ? '$' + totalValueUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '$0.00';

                    // Calculate percentage
                    const percentage = totalPortfolioValue > 0 ? (totalValueUsd / totalPortfolioValue * 100) : 0;

                    // Get ignore status
                    const assetId = asset.id;
                    const isIgnored = asset.ignored === 1 || asset.ignored === true;

                    html += `
                        <tr class="${isIgnored ? 'asset-ignored' : ''}">
                            <td class="asset-name-cell">
                                ${logoUrl ? `<img src="${logoUrl}" alt="${displayName}" class="token-logo" onerror="this.style.display='none';">` : ''}
                                <div style="flex: 1;">
                                    <div class="asset-ticker">${ticker}</div>
                                    <div class="asset-name-small">${displayName}</div>
                                </div>
                            </td>
                            <td>${priceNativeStr}</td>
                            <td>${ownedStr}</td>
                            <td class="ada-value">${totalNativeStr}</td>
                            <td>${totalUsdStr}</td>
                            <td>
                                <div class="portfolio-bar-wrapper">
                                    <div class="portfolio-bar" style="width: ${percentage}%"></div>
                                    <span class="portfolio-pct">${percentage.toFixed(1)}%</span>
                                </div>
                            </td>
                            <td>
                                <label class="ignore-toggle">
                                    <input type="checkbox" ${isIgnored ? 'checked' : ''}
                                           onchange="toggleAssetIgnore(${assetId}, this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
                container.innerHTML = html;
            } else {
                // Non-Cardano: use grid layout
                let html = '<div class="assets-grid">';
                assets.forEach(asset => {
                    const actualQty = parseFloat(asset.actual_quantity) || 0;
                    const quantity = actualQty >= 1000000
                        ? (actualQty / 1000000).toFixed(2) + 'M'
                        : actualQty >= 1000
                        ? (actualQty / 1000).toFixed(2) + 'K'
                        : actualQty.toLocaleString('en-US', { maximumFractionDigits: 6 });

                    const ticker = asset.ticker || asset.asset_name?.substring(0, 10) || 'Unknown';
                    const displayName = asset.token_name || asset.asset_name || 'Unknown';
                    const logoUrl = asset.logo_url || '';
                    const totalValue = parseFloat(asset.total_value_usd) || 0;
                    const priceUsd = parseFloat(asset.price_usd) || 0;

                    const showPrice = totalValue >= 1.00;
                    let priceDisplay = '';
                    if (showPrice && priceUsd > 0) {
                        const priceStr = priceUsd >= 1
                            ? '$' + priceUsd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                            : priceUsd >= 0.01
                            ? '$' + priceUsd.toFixed(4)
                            : '$' + priceUsd.toFixed(8);
                        priceDisplay = `<div class="asset-price">${priceStr}</div>`;
                    } else if (showPrice) {
                        priceDisplay = '<div class="asset-price">N/A</div>';
                    }

                    html += `
                        <div class="asset-item">
                            ${logoUrl ? `<img src="${logoUrl}" alt="${displayName}" class="token-logo" onerror="this.style.display='none';">` : ''}
                            <div class="asset-info">
                                <div class="asset-ticker">${ticker}</div>
                                <div class="asset-name">${displayName}</div>
                            </div>
                            <div class="asset-values">
                                <div class="asset-quantity">${quantity}</div>
                                ${priceDisplay}
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                container.innerHTML = html;
            }
        }

        container.dataset.loaded = 'true';
    } catch (error) {
        console.error('Error loading wallet assets:', error);
        container.innerHTML = '<div style="text-align: center; padding: 10px; color: #dc3545;">Failed to load assets</div>';
    }
}

// Toggle asset ignore status
async function toggleAssetIgnore(assetId, isIgnored) {
    try {
        const response = await authFetch(`${API_BASE}/wallets/assets/${assetId}/toggle-ignore`, {
            method: 'POST'
        });

        if (response.ok) {
            // Reload the portfolio summary to reflect changes
            await loadPortfolioSummary();

            // Show a brief confirmation
            console.log(`Asset ${assetId} ${isIgnored ? 'ignored' : 'included'} in portfolio totals`);
        } else {
            throw new Error('Failed to toggle asset ignore status');
        }
    } catch (error) {
        console.error('Error toggling asset ignore:', error);
        alert('Failed to update asset status. Please try again.');
    }
}

// Render a single wallet item
function renderSingleWallet(wallet, blockchain, isGrouped) {
    const units = { cardano: 'ADA', bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL', polygon: 'POL', base: 'ETH' };
    const decimalPlaces = { cardano: 6, bitcoin: 8, ethereum: 8, solana: 9, polygon: 6, base: 8 };
    const priceKeys = { cardano: 'ADA', bitcoin: 'BTC', ethereum: 'ETH', solana: 'SOL', polygon: 'MATIC', base: 'ETH' };

    const unit = units[blockchain] || '';
    const decimals = decimalPlaces[blockchain] || 8;
    const balanceNum = wallet.balance || 0;
    const balance = balanceNum.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: decimals});

    // Asset info - different label for Ethereum, Solana, Polygon, and Base
    let assetsInfo = '';
    if ((blockchain === 'ethereum' || blockchain === 'solana' || blockchain === 'polygon' || blockchain === 'base') && wallet.token_count) {
        assetsInfo = `${wallet.token_count} tokens`;
    } else if (wallet.native_assets_count) {
        assetsInfo = `${wallet.native_assets_count} assets`;
    }

    // Calculate USD value
    const priceKey = priceKeys[blockchain];
    const usdValue = balanceNum * (prices[priceKey] || 0);
    const usdFormatted = formatUSD(usdValue);

    // External explorer links based on blockchain
    let explorerLinks = '';
    if (blockchain === 'cardano') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://adastat.net/addresses/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on AdaStat">
                    <span class="explorer-icon adastat">AS</span>
                </a>
                <a href="https://beta.cexplorer.io/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on cexplorer">
                    <span class="explorer-icon cexplorer">CX</span>
                </a>
                <a href="https://www.taptools.io/portfolio?address=${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on TapTools">
                    <span class="explorer-icon taptools">TT</span>
                </a>
            </div>
        `;
    } else if (blockchain === 'bitcoin') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://mempool.space/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Mempool">
                    <span class="explorer-icon mempool">MP</span>
                </a>
                <a href="https://blockstream.info/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Blockstream">
                    <span class="explorer-icon blockstream">BS</span>
                </a>
                <a href="https://www.blockchain.com/explorer/addresses/btc/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Blockchain.com">
                    <span class="explorer-icon blockchain">BC</span>
                </a>
            </div>
        `;
    } else if (blockchain === 'ethereum') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://etherscan.io/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Etherscan">
                    <span class="explorer-icon etherscan">ES</span>
                </a>
                <a href="https://debank.com/profile/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on DeBank">
                    <span class="explorer-icon debank">DB</span>
                </a>
                <a href="https://zapper.xyz/account/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Zapper">
                    <span class="explorer-icon zapper">ZP</span>
                </a>
            </div>
        `;
    } else if (blockchain === 'solana') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://solscan.io/account/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Solscan">
                    <span class="explorer-icon solscan">SS</span>
                </a>
                <a href="https://explorer.solana.com/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Solana Explorer">
                    <span class="explorer-icon solana-explorer">SE</span>
                </a>
                <a href="https://solanabeach.io/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Solana Beach">
                    <span class="explorer-icon solana-beach">SB</span>
                </a>
            </div>
        `;
    } else if (blockchain === 'polygon') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://polygonscan.com/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Polygonscan">
                    <span class="explorer-icon polygonscan">PS</span>
                </a>
                <a href="https://debank.com/profile/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on DeBank">
                    <span class="explorer-icon debank">DB</span>
                </a>
                <a href="https://zapper.xyz/account/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Zapper">
                    <span class="explorer-icon zapper">ZP</span>
                </a>
            </div>
        `;
    } else if (blockchain === 'base') {
        explorerLinks = `
            <div class="wallet-explorers">
                <a href="https://basescan.org/address/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Basescan">
                    <span class="explorer-icon basescan">BS</span>
                </a>
                <a href="https://debank.com/profile/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on DeBank">
                    <span class="explorer-icon debank">DB</span>
                </a>
                <a href="https://zapper.xyz/account/${wallet.address}" target="_blank" rel="noopener" class="explorer-link" title="View on Zapper">
                    <span class="explorer-icon zapper">ZP</span>
                </a>
            </div>
        `;
    }

    // No governance section for individual wallets - it's at stake key level now
    const groupedClass = isGrouped ? 'grouped-wallet' : '';

    const walletId = wallet.id || wallet.wallet_id;
    const hasAssets = wallet.native_assets_count > 0 || wallet.token_count > 0;

    return `
        <div class="wallet-item ${blockchain} ${groupedClass}" data-address="${wallet.address}" data-wallet-id="${walletId}">
            <div class="wallet-info">
                ${!isGrouped ? `<div class="wallet-label-container">
                    <span class="wallet-label">${wallet.label || blockchain.charAt(0).toUpperCase() + blockchain.slice(1) + ' Wallet'}</span>
                    <button class="edit-label-btn" title="Edit wallet name">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    <button class="delete-wallet-btn" title="Delete wallet">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18"></path>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
                            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>` : ''}
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="wallet-address">${formatAddressDisplay(wallet.address, blockchain)}</span>
                    <button class="copy-address-btn" data-address="${wallet.address}" title="Copy full address">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                    </button>
                    <button class="btn-wallet-sync" data-wallet-sync="${wallet.address}" title="Refresh balance">
                        <span class="sync-icon">&#8635;</span>
                    </button>
                </div>
                ${explorerLinks}
            </div>
            <div class="wallet-balance">
                <div class="amount">${formatCryptoBlur(balance, unit)}</div>
                <div class="amount-usd">${formatUSDBlur(usdValue)}</div>
                ${assetsInfo && hasAssets ? `<div class="assets assets-toggle" data-wallet-id="${walletId}">${assetsInfo} ▼</div>` : (assetsInfo ? `<div class="assets">${assetsInfo}</div>` : '')}
            </div>
            ${hasAssets ? `<div class="wallet-assets-list" id="assets-${walletId}" style="display: none;"><div style="text-align: center; padding: 10px;"><div class="loading"></div></div></div>` : ''}
        </div>
    `;
}

// Toggle wallet group expansion
function toggleWalletGroup(header) {
    const group = header.closest('.wallet-group');
    group.classList.toggle('collapsed');
}

// Load governance info at stake key level
async function loadStakeKeyGovernanceInfo(stakeGroups) {
    for (const group of stakeGroups) {
        if (!group.stake_address) continue;

        const stakeId = group.stake_address.slice(0, 20);
        const govEl = document.getElementById(`stake-gov-${stakeId}`);
        if (!govEl) continue;

        // Use the first wallet address to fetch governance info
        const firstWallet = group.wallets[0];
        if (!firstWallet) continue;

        try {
            const response = await authFetch(`${API_BASE}/wallets/${firstWallet.address}/governance`);
            if (!response.ok) {
                setSafeHTML(govEl, '<div class="gov-error">No staking info</div>');
                continue;
            }

            const gov = await response.json();

            if (!gov.has_stake_key) {
                setSafeHTML(govEl, '<div class="gov-error">No stake key</div>');
                continue;
            }

            // Build governance display
            let html = '<div class="gov-details">';

            // Staking Pool
            if (gov.pool) {
                const poolId = gov.pool.pool_id;
                const poolDisplay = gov.pool.ticker || gov.pool.name;
                const poolLink = poolId ? `https://cexplorer.io/pool/${poolId}` : null;
                html += `
                    <div class="gov-item pool">
                        <span class="gov-icon">&#127944;</span>
                        <span class="gov-label">Pool:</span>
                        ${poolLink
                            ? `<a href="${poolLink}" target="_blank" rel="noopener" class="gov-link blur-sensitive">${poolDisplay}</a>`
                            : `<span class="gov-value blur-sensitive">${poolDisplay}</span>`
                        }
                    </div>
                `;
            } else {
                html += `
                    <div class="gov-item pool undelegated">
                        <span class="gov-icon">&#127944;</span>
                        <span class="gov-label">Pool:</span>
                        <span class="gov-value">Not delegated</span>
                    </div>
                `;
            }

            // DRep
            if (gov.drep && gov.drep.delegated) {
                const drepId = gov.drep.drep_id;
                const isSpecialDrep = drepId === 'drep_always_abstain' || drepId === 'drep_always_no_confidence';
                // Use name from backend (fetched from Blockfrost/cexplorer), fallback to truncated ID
                const truncatedId = drepId ? `${drepId.slice(0, 8)}...${drepId.slice(-4)}` : 'Unknown';
                const drepDisplay = gov.drep.drep_name || truncatedId;
                const drepLink = drepId && !isSpecialDrep ? `https://cexplorer.io/drep/${drepId}` : null;
                html += `
                    <div class="gov-item drep">
                        <span class="gov-icon">&#128499;</span>
                        <span class="gov-label">DRep:</span>
                        ${drepLink
                            ? `<a href="${drepLink}" target="_blank" rel="noopener" class="gov-link blur-sensitive">${drepDisplay}</a>`
                            : `<span class="gov-value blur-sensitive">${drepDisplay}</span>`
                        }
                    </div>
                `;
            } else {
                html += `
                    <div class="gov-item drep undelegated">
                        <span class="gov-icon">&#128499;</span>
                        <span class="gov-label">DRep:</span>
                        <span class="gov-value">Not delegated</span>
                    </div>
                `;
            }

            // Rewards
            if (gov.rewards && parseFloat(gov.rewards.withdrawable) > 0) {
                html += `
                    <div class="gov-item rewards">
                        <span class="gov-icon">&#127873;</span>
                        <span class="gov-label">Rewards:</span>
                        <span class="gov-value">${blurValue(parseFloat(gov.rewards.withdrawable).toFixed(2))} ADA pending</span>
                    </div>
                `;
            }

            html += '</div>';
            setSafeHTML(govEl, html);

        } catch (error) {
            console.error(`Error loading governance for stake key ${group.stake_address}:`, error);
            setSafeHTML(govEl, '<div class="gov-error">Failed to load</div>');
        }
    }
}

// Store for native token data
let nativeTokensData = null;
let trackedTokensValue = 0;
let customTokensValue = 0;

// Load native assets (cached by default, pass true to force refresh)
async function loadNativeAssets(forceRefresh = false) {
    try {
        const url = forceRefresh
            ? `${API_BASE}/portfolio/assets?refresh=true`
            : `${API_BASE}/portfolio/assets`;
        const response = await authFetch(url);
        const data = await response.json();
        nativeTokensData = data;

        // Update tracked value
        trackedTokensValue = data.tracked_value_usd || 0;

        // Update section summary
        const nativeTokensSummary = document.getElementById('nativeTokensSummary');
        if (nativeTokensSummary) {
            const totalTokens = data.total_unique_assets || data.assets?.length || 0;
            const cachedIndicator = data.cached ? ' <span class="cache-indicator" title="Cached data">(cached)</span>' : '';
            setSafeHTML(nativeTokensSummary, `
                <span class="token-count">${totalTokens} tokens${cachedIndicator}</span>
                <span class="tracked-value">Tracked: ${formatUSD(trackedTokensValue)}</span>
            `);
        }

        // Render consolidated native assets section
        renderNativeAssets(data.valuable_assets || [], data.assets || []);

        // Update portfolio total
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading native assets:', error);
    }
}

// Render consolidated native assets section with toggles for valuable tokens
function renderNativeAssets(valuableAssets, allAssets) {
    const tokensList = document.getElementById('nativeTokensList');
    if (!tokensList) return;

    if (allAssets.length === 0) {
        setSafeHTML(tokensList, '<p class="empty-state">No tokens found.</p>');
        return;
    }

    // Helper to get blockchain badge
    const getBlockchainBadge = (blockchain) => {
        const badges = {
            'cardano': '<span class="chain-badge cardano" title="Cardano">ADA</span>',
            'ethereum': '<span class="chain-badge ethereum" title="Ethereum">ETH</span>',
            'solana': '<span class="chain-badge solana" title="Solana">SOL</span>'
        };
        return badges[blockchain] || '';
    };

    let html = '';

    // Show valuable assets (with prices) with toggle switches
    if (valuableAssets.length > 0) {
        html += '<div class="assets-section-header">Tokens with Value</div>';
        html += valuableAssets.map(asset => {
            const displayName = asset.ticker || asset.asset_name || 'Unknown Token';
            const qty = asset.total_quantity_formatted || asset.total_quantity?.toLocaleString() || '0';
            const valueUsd = asset.value_usd || 0;
            const priceUsd = asset.price_usd ? `$${asset.price_usd.toFixed(4)}` : '';
            const isTracked = asset.tracked || false;
            const isDefiToken = asset.is_defi_token || false;
            const decimals = asset.decimals || 0;
            const blockchain = asset.blockchain || 'cardano';

            // Show indicator if token is tracked but counted in DeFi section
            const defiIndicator = isDefiToken
                ? '<span class="defi-badge" title="Counted in DeFi Tokens section">DeFi</span>'
                : '';

            // Get logo URL (from NMKR or LogoKit)
            const logoUrl = asset.logo_url || '';

            return `
                <div class="native-token-item ${isTracked ? 'tracked' : ''} ${isDefiToken ? 'is-defi' : ''} ${blockchain}"
                     data-asset-id="${asset.asset_id}"
                     data-blockchain="${blockchain}"
                     data-value="${valueUsd}"
                     data-is-defi="${isDefiToken}">
                    <div class="token-toggle">
                        <label class="toggle-switch">
                            <input type="checkbox" ${isTracked ? 'checked' : ''}
                                   onchange="toggleTokenTracking('${asset.asset_id}', this.checked, '${asset.ticker || ''}', ${decimals}, ${valueUsd})">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    ${logoUrl ? `<img src="${logoUrl}" alt="${displayName}" class="token-logo" onerror="this.style.display='none';">` : ''}
                    <div class="token-info">
                        <div class="token-name">
                            ${getBlockchainBadge(blockchain)}
                            ${displayName}
                            ${defiIndicator}
                        </div>
                        <div class="token-meta">
                            <span class="token-price">${priceUsd}</span>
                        </div>
                    </div>
                    <div class="token-values">
                        <div class="token-quantity">${qty}</div>
                        <div class="token-usd">${formatUSD(valueUsd)}</div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Show other assets without prices (no toggles needed)
    const otherAssets = allAssets.filter(a => !a.value_usd);
    if (otherAssets.length > 0) {
        html += '<div class="assets-section-header">Other Tokens (No Price Data)</div>';
        html += otherAssets.slice(0, 30).map(asset => {
            const displayName = asset.ticker || asset.asset_name || 'Unknown';
            const qty = asset.total_quantity_formatted || asset.total_quantity_raw?.toLocaleString() || '0';
            const blockchain = asset.blockchain || 'cardano';
            const logoUrl = asset.logo_url || '';

            return `
                <div class="native-token-item other ${blockchain}">
                    ${logoUrl ? `<img src="${logoUrl}" alt="${displayName}" class="token-logo" onerror="this.style.display='none';">` : ''}
                    <div class="token-info">
                        <div class="token-name">
                            ${getBlockchainBadge(blockchain)}
                            ${displayName}
                        </div>
                        <div class="token-meta">
                            <span class="token-policy">${asset.policy_id?.slice(0, 12)}...</span>
                        </div>
                    </div>
                    <div class="token-values">
                        <div class="token-quantity">${qty}</div>
                    </div>
                </div>
            `;
        }).join('');

        if (otherAssets.length > 30) {
            html += `<p class="more-tokens-note">And ${otherAssets.length - 30} more tokens...</p>`;
        }
    }

    setSafeHTML(tokensList, html);
}

// Flag to prevent race conditions during toggle
let isTogglingToken = false;

// Toggle token tracking with real-time update
async function toggleTokenTracking(assetId, track, ticker, decimals, tokenValue) {
    // Prevent concurrent toggles - revert checkbox if blocked
    if (isTogglingToken) {
        // Revert the checkbox since it changed before this handler fired
        const tokenItem = document.querySelector(`.native-token-item[data-asset-id="${assetId}"]`);
        if (tokenItem) {
            const checkbox = tokenItem.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = !track;
        }
        return;
    }
    isTogglingToken = true;

    // Immediately update the visual state
    const tokenItem = document.querySelector(`.native-token-item[data-asset-id="${assetId}"]`);
    if (tokenItem) {
        tokenItem.classList.toggle('tracked', track);
    }

    // Check if this is a DeFi token (already counted in DeFi section)
    const isDefiToken = tokenItem?.dataset?.isDefi === 'true';

    // Immediately update the tracked value for real-time feedback
    // DeFi tokens don't affect trackedTokensValue (they're in defiTotals)
    const previousTrackedValue = trackedTokensValue;
    if (!isDefiToken) {
        if (track) {
            trackedTokensValue += tokenValue;
        } else {
            trackedTokensValue -= tokenValue;
        }
    }

    // Update summary display immediately
    const nativeTokensSummary = document.getElementById('nativeTokensSummary');
    if (nativeTokensSummary) {
        const tokenCountEl = nativeTokensSummary.querySelector('.token-count');
        const tokenCountText = tokenCountEl ? tokenCountEl.outerHTML : '<span class="token-count">0 tokens</span>';
        setSafeHTML(nativeTokensSummary, `
            ${tokenCountText}
            <span class="tracked-value">Tracked: ${formatUSD(trackedTokensValue)}</span>
        `);
    }

    // Update portfolio total immediately
    updateTotalPortfolioValue();

    // Then persist to backend
    try {
        const response = await authFetch(`${API_BASE}/portfolio/tokens/track`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                asset_id: assetId,
                track: track,
                ticker: ticker || null,
                decimals: decimals || null
            })
        });

        if (!response.ok) {
            console.error('Failed to toggle token tracking');
            // Revert visual state on failure
            if (tokenItem) {
                tokenItem.classList.toggle('tracked', !track);
                const checkbox = tokenItem.querySelector('input[type="checkbox"]');
                if (checkbox) checkbox.checked = !track;
            }
            trackedTokensValue = previousTrackedValue;
            updateTotalPortfolioValue();
        }
    } catch (error) {
        console.error('Error toggling token tracking:', error);
        // Revert visual state on error
        if (tokenItem) {
            tokenItem.classList.toggle('tracked', !track);
            const checkbox = tokenItem.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = !track;
        }
        trackedTokensValue = previousTrackedValue;
        updateTotalPortfolioValue();
    } finally {
        isTogglingToken = false;
    }
}

// Load staking positions across all wallets
async function loadStakingPositions() {
    // Mark staking as loading
    document.body.classList.add('staking-loading');
    updateTotalPortfolioValue(); // Update to show spinner

    // Show loading state with progress bar
    setSafeHTML(stakingPositions, `
        <div class="loading-state">
            <div class="progress-container">
                <div class="progress-bar" id="stakingProgressBar"></div>
            </div>
            <p class="progress-text" id="stakingProgressText">Initializing...</p>
        </div>
    `);

    const progressBar = document.getElementById('stakingProgressBar');
    const progressText = document.getElementById('stakingProgressText');

    try {
        // First get all wallets
        const walletsResponse = await authFetch(`${API_BASE}/wallets`);
        const walletsData = await walletsResponse.json();

        const cardanoWallets = walletsData.wallets.filter(w => w.blockchain === 'cardano');

        if (cardanoWallets.length === 0) {
            setSafeHTML(stakingPositions, '<p class="empty-state">No Cardano wallets to check for staking.</p>');
            return;
        }

        // Aggregate staking from all wallets
        const allStaking = {};
        const totalWallets = cardanoWallets.length;
        let processedWallets = 0;

        for (const wallet of cardanoWallets) {
            // Update progress
            const percent = Math.round((processedWallets / totalWallets) * 100);
            if (progressBar) progressBar.style.width = `${percent}%`;
            if (progressText) progressText.textContent = `Checking wallet ${processedWallets + 1} of ${totalWallets}...`;

            try {
                const stakingResponse = await authFetch(`${API_BASE}/defi/staking/${wallet.address}`);
                const stakingData = await stakingResponse.json();

                for (const [protocol, data] of Object.entries(stakingData.protocols || {})) {
                    if (!allStaking[protocol]) {
                        allStaking[protocol] = {
                            staked: {},
                            pending_rewards: 0,
                            pending_indy: 0,
                            pending_ada: 0,
                            accumulated_rewards: 0,
                            reward_token: data.reward_token || '',
                            reward_tokens: data.reward_tokens || [],
                            apy: data.apy || null,
                            claimed_rewards: data.claimed_rewards || 0,
                            total_earned: data.total_earned || 0,
                            rewards_url: data.rewards_url || null
                        };
                    }

                    // Aggregate staked amounts
                    for (const stake of data.staked || []) {
                        if (!allStaking[protocol].staked[stake.token]) {
                            allStaking[protocol].staked[stake.token] = {
                                amount: 0,
                                positions: 0
                            };
                        }
                        allStaking[protocol].staked[stake.token].amount += stake.amount;
                        allStaking[protocol].staked[stake.token].positions += stake.positions;
                        // Carry logo_url from backend (first wallet wins)
                        if (stake.logo_url && !allStaking[protocol].staked[stake.token].logo_url) {
                            allStaking[protocol].staked[stake.token].logo_url = stake.logo_url;
                        }
                    }

                    // Aggregate rewards based on protocol
                    if (protocol === 'Indigo') {
                        allStaking[protocol].pending_indy += data.pending_indy || 0;
                        allStaking[protocol].pending_ada += data.pending_ada || 0;
                    } else {
                        allStaking[protocol].pending_rewards += data.pending_rewards || 0;
                        allStaking[protocol].accumulated_rewards += data.accumulated_rewards || 0;
                    }
                    allStaking[protocol].claimed_rewards += data.claimed_rewards || 0;
                    allStaking[protocol].total_earned += data.total_earned || 0;

                    // Take APY and rewards_url from first wallet that has it
                    if (data.apy && !allStaking[protocol].apy) {
                        allStaking[protocol].apy = data.apy;
                    }
                    if (data.rewards_url && !allStaking[protocol].rewards_url) {
                        allStaking[protocol].rewards_url = data.rewards_url;
                    }
                }
            } catch (e) {
                console.error(`Error loading staking for ${wallet.address}:`, e);
            }

            processedWallets++;
        }

        // Final progress update
        if (progressBar) progressBar.style.width = '100%';
        if (progressText) progressText.textContent = 'Complete!';

        // Store staking totals for portfolio calculation (including pending rewards)
        stakingTotals = {};
        for (const [protocol, data] of Object.entries(allStaking)) {
            for (const [token, stakeData] of Object.entries(data.staked || {})) {
                if (!stakingTotals[token]) {
                    stakingTotals[token] = 0;
                }
                stakingTotals[token] += stakeData.amount;
            }
            // Add pending rewards to totals
            if (data.reward_token && data.pending_rewards > 0) {
                if (!stakingTotals[data.reward_token]) {
                    stakingTotals[data.reward_token] = 0;
                }
                stakingTotals[data.reward_token] += data.pending_rewards;
            }
        }

        // Small delay to show 100% before rendering
        await new Promise(resolve => setTimeout(resolve, 300));

        renderStakingPositions(allStaking);

        // Mark staking as complete and update total portfolio value
        document.body.classList.remove('staking-loading');
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading staking positions:', error);
        setSafeHTML(stakingPositions, '<p class="empty-state">Error loading staking positions.</p>');
        document.body.classList.remove('staking-loading');
        updateTotalPortfolioValue();
    }
}

// Render staking positions with pending rewards and APY
function renderStakingPositions(allStaking) {
    const protocols = Object.keys(allStaking);
    const stakingSummary = document.getElementById('stakingSummary');

    if (protocols.length === 0 && exchangeStakedAssets.length === 0) {
        setSafeHTML(stakingPositions, '<p class="empty-state">No staked positions found.</p>');
        if (stakingSummary) {
            setSafeHTML(stakingSummary, '<span class="staking-status">No positions</span>');
        }
        return;
    }

    let html = '';
    let totalStakingValue = 0;
    let totalPendingValue = 0;
    let totalPositions = 0;

    for (const protocol of protocols) {
        const protocolData = allStaking[protocol];
        const stakes = protocolData.staked;
        const apy = protocolData.apy;
        const rewardsUrl = protocolData.rewards_url;

        for (const [token, data] of Object.entries(stakes)) {
            // Calculate USD value for staked amount
            const tokenPrice = prices[token] || 0;
            const usdValue = data.amount * tokenPrice;
            totalStakingValue += usdValue;
            totalPositions += data.positions;
            const usdFormatted = formatUSD(usdValue);


            // Build pending rewards display based on protocol
            let pendingHtml = '';
            let hasPendingRewards = false;

            if (protocol === 'Indigo') {
                // Indigo has both INDY and ADA rewards
                const pendingIndy = protocolData.pending_indy || 0;
                const pendingAda = protocolData.pending_ada || 0;

                if (pendingIndy > 0 || pendingAda > 0) {
                    hasPendingRewards = true;
                    const indyPrice = prices['INDY'] || 0;
                    const adaPrice = prices['ADA'] || 0;
                    const indyUsd = pendingIndy * indyPrice;
                    const adaUsd = pendingAda * adaPrice;
                    totalPendingValue += indyUsd + adaUsd;

                    pendingHtml = `<div class="staking-pending">
                        <span class="pending-label">Pending Rewards:</span>`;
                    if (pendingIndy > 0) {
                        pendingHtml += `
                            <div class="pending-row">
                                <span class="pending-amount">${formatCryptoBlur(pendingIndy.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}), 'INDY')}</span>
                                ${indyUsd > 0 ? `<span class="pending-usd">${formatUSDBlur(indyUsd)}</span>` : ''}
                            </div>`;
                    }
                    if (pendingAda > 0) {
                        pendingHtml += `
                            <div class="pending-row">
                                <span class="pending-amount">${formatCryptoBlur(pendingAda.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}), 'ADA')}</span>
                                ${adaUsd > 0 ? `<span class="pending-usd">${formatUSDBlur(adaUsd)}</span>` : ''}
                            </div>`;
                    }
                    pendingHtml += '</div>';
                }
            } else if (protocol === 'Strike') {
                // Strike has pending and accumulated rewards
                const pendingRewards = protocolData.pending_rewards || 0;
                const accumulatedRewards = protocolData.accumulated_rewards || 0;
                const rewardToken = protocolData.reward_token || 'STRIKE';
                const rewardPrice = prices[rewardToken] || 0;

                if (pendingRewards > 0 || accumulatedRewards > 0) {
                    hasPendingRewards = pendingRewards > 0;
                    const pendingUsd = pendingRewards * rewardPrice;
                    const accumulatedUsd = accumulatedRewards * rewardPrice;
                    totalPendingValue += pendingUsd;

                    pendingHtml = '<div class="staking-pending">';
                    if (pendingRewards > 0) {
                        pendingHtml += `
                            <div class="pending-row">
                                <span class="pending-label">Pending:</span>
                                <span class="pending-amount">${pendingRewards.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${rewardToken}</span>
                                ${pendingUsd > 0 ? `<span class="pending-usd">${formatUSD(pendingUsd)}</span>` : ''}
                            </div>`;
                    }
                    if (accumulatedRewards > 0) {
                        pendingHtml += `
                            <div class="accumulated-row">
                                <span class="accumulated-label">Accumulated:</span>
                                <span class="accumulated-amount">${accumulatedRewards.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${rewardToken}</span>
                                ${accumulatedUsd > 0 ? `<span class="accumulated-usd">${formatUSD(accumulatedUsd)}</span>` : ''}
                            </div>`;
                    }
                    pendingHtml += '</div>';
                }
            } else if (protocol === 'Liqwid') {
                // Liqwid has pending, claimed, and total earned
                const pendingRewards = protocolData.pending_rewards || 0;
                const claimedRewards = protocolData.claimed_rewards || 0;
                const totalEarned = protocolData.total_earned || 0;
                const rewardToken = protocolData.reward_token || 'LQ';
                const rewardPrice = prices[rewardToken] || 0;

                if (pendingRewards > 0 || claimedRewards > 0 || totalEarned > 0) {
                    hasPendingRewards = pendingRewards > 0;
                    const pendingUsd = pendingRewards * rewardPrice;
                    totalPendingValue += pendingUsd;

                    pendingHtml = '<div class="staking-pending">';
                    if (pendingRewards > 0) {
                        pendingHtml += `
                            <div class="pending-row">
                                <span class="pending-label">Pending:</span>
                                <span class="pending-amount">${pendingRewards.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${rewardToken}</span>
                                ${pendingUsd > 0 ? `<span class="pending-usd">${formatUSD(pendingUsd)}</span>` : ''}
                            </div>`;
                    }
                    if (claimedRewards > 0) {
                        pendingHtml += `
                            <div class="claimed-row">
                                <span class="claimed-label">Previously Claimed:</span>
                                <span class="claimed-amount">${claimedRewards.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${rewardToken}</span>
                            </div>`;
                    }
                    if (totalEarned > 0) {
                        pendingHtml += `
                            <div class="total-earned-row">
                                <span class="total-earned-label">Total Earned:</span>
                                <span class="total-earned-amount">${totalEarned.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${rewardToken}</span>
                            </div>`;
                    }
                    pendingHtml += '</div>';
                }
            } else {
                // Generic handling for other protocols
                const pendingRewards = protocolData.pending_rewards || 0;
                const rewardToken = protocolData.reward_token || '';
                if (pendingRewards > 0) {
                    hasPendingRewards = true;
                    const rewardPrice = prices[rewardToken] || 0;
                    const pendingUsd = pendingRewards * rewardPrice;
                    totalPendingValue += pendingUsd;

                    pendingHtml = `
                        <div class="staking-pending">
                            <span class="pending-label">Pending:</span>
                            <span class="pending-amount">${formatCryptoBlur(pendingRewards.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}), rewardToken)}</span>
                            ${pendingUsd > 0 ? `<span class="pending-usd">${formatUSDBlur(pendingUsd)}</span>` : ''}
                        </div>
                    `;
                }
            }

            // Build rewards page link (not claim button)
            let rewardsLinkHtml = '';
            if (rewardsUrl) {
                rewardsLinkHtml = `<a href="${rewardsUrl}" target="_blank" rel="noopener" class="rewards-page-link" title="View rewards page">View Rewards</a>`;
            }

            html += `
                <div class="staking-card" data-protocol="${protocol}">
                    <div class="staking-card-header">
                        <span class="staking-protocol">${protocol}</span>
                        <div class="staking-badges">
                            <span class="staking-badge">Staked</span>
                            ${hasPendingRewards ? '<span class="staking-badge rewards">Rewards</span>' : ''}
                        </div>
                    </div>
                    <div class="staking-amount">${blurValue(data.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}))}</div>
                    <div class="staking-token">${token}</div>
                    <div class="staking-usd">${formatUSDBlur(usdValue)}</div>
                    ${pendingHtml}
                    <div class="staking-details">
                        ${data.positions} staking position${data.positions !== 1 ? 's' : ''}
                        ${rewardsLinkHtml}
                    </div>
                </div>
            `;
        }
    }

    // Add exchange staked assets (display-only, already counted in exchange totals)
    let exchangeStakedCount = 0;
    if (exchangeStakedAssets.length > 0) {
        for (const staked of exchangeStakedAssets) {
            const usdValue = staked.usd_value || 0;
            totalStakingValue += usdValue;
            exchangeStakedCount++;

            const apyBadge = staked.apy > 0
                ? `<span class="staking-badge apy">${(staked.apy * 100).toFixed(2)}% APY</span>` : '';

            html += `
                <div class="staking-card exchange-staked" data-protocol="${staked.exchangeName}">
                    <div class="staking-card-header">
                        <span class="staking-protocol">${staked.exchangeName}</span>
                        <div class="staking-badges">
                            <span class="staking-badge exchange">Exchange Staked</span>
                            ${apyBadge}
                        </div>
                    </div>
                    <div class="staking-amount">${blurValue(staked.staked_balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}))}</div>
                    <div class="staking-token">${staked.currency}</div>
                    <div class="staking-usd">${formatUSDBlur(usdValue)}</div>
                    <div class="staking-details">
                        Custodial staking via ${staked.exchangeName}
                        <span class="exchange-staked-note">(included in exchange total)</span>
                    </div>
                </div>
            `;
        }
    }

    // Build summary counts
    const totalSources = protocols.length + (exchangeStakedCount > 0 ? 1 : 0);
    const sourceLabel = protocols.length > 0 && exchangeStakedCount > 0
        ? `${protocols.length} protocol${protocols.length !== 1 ? 's' : ''} + ${exchangeStakedCount} exchange`
        : exchangeStakedCount > 0
            ? `${exchangeStakedCount} exchange staked`
            : `${protocols.length} protocol${protocols.length !== 1 ? 's' : ''}`;

    // Update section summary
    if (stakingSummary) {
        let summaryHtml = `
            <span class="staking-status">${sourceLabel}</span>
            <span class="staking-total">${formatUSDBlur(totalStakingValue)}</span>
        `;
        if (totalPendingValue > 0) {
            summaryHtml += `<span class="staking-pending-summary">+${formatUSDBlur(totalPendingValue)} pending</span>`;
        }
        setSafeHTML(stakingSummary, summaryHtml);
    }

    // Add total staking value header with pending rewards
    let headerHtml = `
        <div class="staking-total">
            <span class="staking-total-label">Total Staked Value:</span>
            <span class="staking-total-value">${formatUSDBlur(totalStakingValue)}</span>
    `;
    if (totalPendingValue > 0) {
        headerHtml += `
            <span class="staking-pending-total">
                <span class="pending-label">+ Pending Rewards:</span>
                <span class="pending-value">${formatUSD(totalPendingValue)}</span>
            </span>
        `;
    }
    headerHtml += '</div>';

    setSafeHTML(stakingPositions, headerHtml + html);
}

// Load DeFi positions
async function loadDefiPositions() {
    // Mark DeFi as loading
    document.body.classList.add('defi-loading');
    updateTotalPortfolioValue();

    try {
        const response = await authFetch(`${API_BASE}/defi/summary`);
        const data = await response.json();

        // Update summary counts
        defiProtocolCount.textContent = `${data.protocols_used.length} protocol${data.protocols_used.length !== 1 ? 's' : ''}`;
        defiWalletCount.textContent = `${data.wallets_with_defi} wallet${data.wallets_with_defi !== 1 ? 's' : ''} with DeFi`;

        // Calculate and store DeFi totals for portfolio calculation
        defiTotals = {};
        let totalDefiValue = 0;
        if (data.positions_by_category) {
            for (const [category, positions] of Object.entries(data.positions_by_category)) {
                for (const pos of positions) {
                    // Use token (standard symbol from DEFI_PROTOCOLS) for price lookup
                    const token = pos.token || pos.asset_name || pos.symbol;
                    if (token && pos.quantity) {
                        if (!defiTotals[token]) {
                            defiTotals[token] = 0;
                        }
                        defiTotals[token] += pos.quantity;

                        // Calculate USD value
                        const price = prices[token] || 0;
                        totalDefiValue += pos.quantity * price;
                    }
                }
            }
        }

        // Render DeFi categories
        renderDefiPositions(data);

        // Mark DeFi as complete and update total portfolio value
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading DeFi positions:', error);
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();
    }
}

// Render DeFi positions by category
function renderDefiPositions(data) {
    if (!data.positions_by_category || Object.keys(data.positions_by_category).length === 0) {
        setSafeHTML(defiCategories, '<p class="empty-state">No DeFi positions found.</p>');
        return;
    }

    // Category icons
    const categoryIcons = {
        'Governance Tokens': '\u{1F3DB}',
        'Liquidity Pool Tokens': '\u{1F4B1}',
        'Staking Receipts': '\u{1F4C4}',
        'Protocol Receipts': '\u{1F4C3}',
        'Synthetic Assets': '\u{1F4B5}',
        'Stablecoins': '\u{1F4B0}',
        'Reserve Tokens': '\u{1F3E6}',
        'Liquid Staking': '\u{1F4A7}'
    };

    // Governance links for each token
    const governanceLinks = {
        'INDY': 'https://app.indigoprotocol.io/earn',
        'LQ': 'https://app.liqwid.finance/agora',
        'MIN': 'https://app.minswap.org/governance',
        'SUNDAE': 'https://vote.sundaeswap.finance/',
        'STRIKE': 'https://app.strikefinance.org/perpetuals/ada',
        'WRT': 'https://app.wingriders.com/governance',
        'LENFI': 'https://app.lenfi.io/governance',
        'OPTIM': 'https://app.optim.finance/governance',
        'SPF': 'https://spectrum.fi/governance',
        'VYFI': 'https://app.vyfi.io/governance',
        'IAG': 'https://iagon.com/governance',
        'AGIX': 'https://singularitynet.io/vote'
    };

    // Known stablecoins to always show
    const knownStablecoins = {
        'USDC': { name: 'USD Coin', minShow: 0.01 },
        'USDM': { name: 'Moneta USD', minShow: 0.01 },
        'iUSD': { name: 'Indigo USD', minShow: 0.01 },
        'DJED': { name: 'DJED', minShow: 0.01 },
        'USDT': { name: 'Tether USD', minShow: 0.01 },
        'DAI': { name: 'DAI', minShow: 0.01 }
    };

    // Define category order
    const categoryOrder = [
        'Governance Tokens',
        'Liquidity Pool Tokens',
        'Staking Receipts',
        'Stablecoins',
        'Synthetic Assets',
        'Protocol Receipts',
        'Reserve Tokens',
        'Liquid Staking'
    ];

    let html = '';

    // Sort categories by defined order
    const sortedCategories = Object.keys(data.positions_by_category).sort((a, b) => {
        const indexA = categoryOrder.indexOf(a);
        const indexB = categoryOrder.indexOf(b);
        return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
    });

    for (const category of sortedCategories) {
        const positions = data.positions_by_category[category];
        const icon = categoryIcons[category] || '\u{1F4CA}';

        // Sort positions by quantity descending
        positions.sort((a, b) => b.quantity - a.quantity);

        if (category === 'Governance Tokens') {
            // Line-by-line format with governance links
            html += `
                <div class="defi-category defi-category-compact">
                    <div class="defi-category-header">
                        <span class="defi-category-icon">${icon}</span>
                        <span class="defi-category-title">${category}</span>
                    </div>
                    <div class="defi-positions-list">
                        ${positions.map(pos => {
                            const govLink = governanceLinks[pos.asset_name];
                            const price = prices[pos.asset_name] || 0;
                            const usdValue = pos.quantity * price;
                            return `
                                <div class="defi-position-line">
                                    <span class="defi-line-token">${pos.asset_name}</span>
                                    <span class="defi-line-amount">${pos.quantity_formatted}</span>
                                    ${usdValue > 0 ? `<span class="defi-line-usd">${formatUSD(usdValue)}</span>` : ''}
                                    ${govLink ? `<a href="${govLink}" target="_blank" rel="noopener" class="defi-gov-link" title="Vote with ${pos.asset_name}">Vote</a>` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        } else if (category === 'Stablecoins') {
            // Condensed line-by-line format, show all stables including small balances
            const stablePositions = positions.filter(pos => pos.quantity >= 0.01);

            html += `
                <div class="defi-category defi-category-compact">
                    <div class="defi-category-header">
                        <span class="defi-category-icon">${icon}</span>
                        <span class="defi-category-title">${category}</span>
                    </div>
                    <div class="defi-positions-list">
                        ${stablePositions.map(pos => {
                            const stableInfo = knownStablecoins[pos.asset_name];
                            const displayName = stableInfo ? stableInfo.name : pos.asset_name;
                            return `
                                <div class="defi-position-line defi-stable-line">
                                    <span class="defi-line-token">${pos.asset_name}</span>
                                    <span class="defi-line-amount">${pos.quantity_formatted}</span>
                                    <span class="defi-line-usd">~${formatUSD(pos.quantity)}</span>
                                </div>
                            `;
                        }).join('')}
                        ${stablePositions.length === 0 ? '<div class="defi-empty-line">No stablecoins held</div>' : ''}
                    </div>
                </div>
            `;
        } else {
            // Default boxed format for other categories
            html += `
                <div class="defi-category">
                    <div class="defi-category-header">
                        <span class="defi-category-icon">${icon}</span>
                        <span class="defi-category-title">${category}</span>
                        <span class="defi-category-count">${positions.length} token${positions.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="defi-positions">
                        ${positions.map(pos => `
                            <div class="defi-position" data-protocol="${pos.protocol}">
                                <div class="defi-position-protocol">${pos.protocol}</div>
                                <div class="defi-position-token">${pos.asset_name}</div>
                                <div class="defi-position-amount">${pos.quantity_formatted}</div>
                                ${pos.wallet_count > 1 ? `<div class="defi-position-wallets">In ${pos.wallet_count} wallets</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
    }

    setSafeHTML(defiCategories, html);
}

// ============================================================================
// CONSOLIDATED DEFI & GOVERNANCE SECTION
// ============================================================================

// Governance links for DeFi protocols
const GOVERNANCE_LINKS = {
    'INDY': { url: 'https://app.indigoprotocol.io/earn', name: 'Indigo' },
    'LQ': { url: 'https://app.liqwid.finance/agora', name: 'Liqwid' },
    'MIN': { url: 'https://app.minswap.org/governance', name: 'Minswap' },
    'SUNDAE': { url: 'https://vote.sundaeswap.finance/', name: 'SundaeSwap' },
    'STRIKE': { url: 'https://app.strikefinance.org/perpetuals/ada', name: 'Strike' },
    'WRT': { url: 'https://app.wingriders.com/governance', name: 'WingRiders' },
    'LENFI': { url: 'https://app.lenfi.io/governance', name: 'Lenfi' },
    'OPTIM': { url: 'https://app.optim.finance/governance', name: 'Optim' },
    'SPF': { url: 'https://spectrum.fi/governance', name: 'Spectrum' },
    'VYFI': { url: 'https://app.vyfi.io/governance', name: 'VyFi' },
    'IAG': { url: 'https://iagon.com/governance', name: 'Iagon' },
    'AGIX': { url: 'https://singularitynet.io/vote', name: 'SingularityNET' }
};


// Known stablecoins
const KNOWN_STABLECOINS = ['USDC', 'USDT', 'DAI', 'USDM', 'iUSD', 'DJED', 'BUSD', 'TUSD'];

// Restore defiTotals/stakingTotals from cached data for portfolio calculations
function restoreDefiTotalsFromCache(cached) {
    defiTotals = {};
    if (cached.defiData && cached.defiData.positions_by_category) {
        for (const [category, positions] of Object.entries(cached.defiData.positions_by_category)) {
            for (const pos of positions) {
                const token = pos.token || pos.asset_name || pos.symbol;
                if (token && pos.quantity) {
                    if (!defiTotals[token]) defiTotals[token] = 0;
                    defiTotals[token] += pos.quantity;
                }
            }
        }
    }

    stakingTotals = {};
    for (const [protocol, data] of Object.entries(cached.allStaking || {})) {
        for (const [token, stakeData] of Object.entries(data.staked || {})) {
            if (!stakingTotals[token]) stakingTotals[token] = 0;
            stakingTotals[token] += stakeData.amount;
        }
        if (data.reward_token && data.pending_rewards > 0) {
            if (!stakingTotals[data.reward_token]) stakingTotals[data.reward_token] = 0;
            stakingTotals[data.reward_token] += data.pending_rewards;
        }
    }
}

// Show/hide the DeFi background refresh bar
function setDefiRefreshBar(visible) {
    const bar = document.getElementById('defiRefreshBar');
    if (bar) {
        bar.classList.toggle('active', visible);
    }
}

// Load consolidated DeFi & Governance data
async function loadDefiGovernance(forceRefresh = false) {
    const content = document.getElementById('defiGovernanceContent');
    const summary = document.getElementById('defiGovernanceSummary');

    if (!content) return;

    // Check for cached data and render instantly if available
    const cached = getCachedDefi();
    const cacheAge = getCachedDefiAge();
    if (cached) {
        // Render immediately from cache - no spinners
        restoreDefiTotalsFromCache(cached);
        document.body.classList.remove('defi-loading');
        document.body.classList.remove('staking-loading');
        renderDefiGovernance(
            cached.allStaking || {},
            cached.defiData,
            cached.exchangeStablecoins || [],
            cached.nativeStablecoins || [],
            cached.adaDelegation
        );
        updateTotalPortfolioValue();
        updateDefiTimestamp();

        // Cache < 2 min old: skip background refresh entirely (unless forced)
        if (!forceRefresh && cacheAge < 2 * 60 * 1000) {
            // Ensure wallet addresses are available for per-card refresh buttons
            if (!window._defiWalletAddresses) {
                authFetch(`${API_BASE}/wallets`).then(r => r.json()).then(data => {
                    window._defiWalletAddresses = {
                        cardano: data.wallets.filter(w => w.blockchain === 'cardano').map(w => w.address),
                        solana: data.wallets.filter(w => w.blockchain === 'solana').map(w => w.address)
                    };
                }).catch(() => {});
            }
            return;
        }
    } else {
        // No cache - show loading state
        document.body.classList.add('staking-loading');
        document.body.classList.add('defi-loading');
        updateTotalPortfolioValue();
        setSafeHTML(content, `
            <div class="loading-state">
                <p class="progress-text" id="defiGovProgressText">Loading DeFi data...</p>
            </div>
        `);
    }

    // Show subtle refresh bar for background fetch
    setDefiRefreshBar(true);

    try {
        // Phase 1: Fetch base data in parallel (wallets, defi summary, exchanges, native assets)
        const [walletsResponse, defiResponse, exchangeResponse, nativeAssetsResponse] = await Promise.all([
            authFetch(`${API_BASE}/wallets`),
            authFetch(`${API_BASE}/defi/summary`),
            authFetch(`${API_BASE}/exchanges/coinbase`).catch(() => ({ ok: false })),
            authFetch(`${API_BASE}/portfolio/assets`).catch(() => ({ ok: false }))
        ]);

        const walletsData = await walletsResponse.json();
        const defiData = await defiResponse.json();
        let exchangeData = null;
        if (exchangeResponse.ok) {
            exchangeData = await exchangeResponse.json();
        }
        let nativeAssetsData = null;
        if (nativeAssetsResponse.ok) {
            nativeAssetsData = await nativeAssetsResponse.json();
        }

        const cardanoWallets = walletsData.wallets.filter(w => w.blockchain === 'cardano');

        // Extract stablecoins immediately (no waiting needed)
        let exchangeStablecoins = [];
        if (exchangeData && exchangeData.assets) {
            exchangeStablecoins = exchangeData.assets.filter(asset =>
                KNOWN_STABLECOINS.includes(asset.currency)
            ).map(asset => ({
                symbol: asset.currency,
                balance: asset.balance,
                chain: 'exchange'
            }));
        }

        let nativeStablecoins = [];
        if (nativeAssetsData && nativeAssetsData.assets) {
            nativeStablecoins = nativeAssetsData.assets.filter(asset => {
                const ticker = asset.ticker || asset.asset_name || '';
                return KNOWN_STABLECOINS.includes(ticker);
            }).map(asset => ({
                symbol: asset.ticker || asset.asset_name,
                balance: asset.total_quantity || 0,
                chain: asset.blockchain || 'cardano'
            }));
        }

        // Store DeFi totals immediately from cached summary
        defiTotals = {};
        if (defiData.positions_by_category) {
            for (const [category, positions] of Object.entries(defiData.positions_by_category)) {
                for (const pos of positions) {
                    const token = pos.token || pos.asset_name || pos.symbol;
                    if (token && pos.quantity) {
                        if (!defiTotals[token]) defiTotals[token] = 0;
                        defiTotals[token] += pos.quantity;
                    }
                }
            }
        }

        // Phase 2: Render with DeFi data (staking shows as loading if no cache)
        document.body.classList.remove('defi-loading');
        if (!cached) {
            // Pre-seed DePIN loading placeholders so cards appear immediately
            const initialStaking = {};
            const govTokens = defiData.positions_by_category?.['Governance Tokens'] || [];
            const hasIAG = govTokens.some(p => (p.token || p.asset_name) === 'IAG');
            if (hasIAG || cardanoWallets.length > 0) {
                initialStaking['Iagon'] = {
                    staked: {},
                    category: 'depin',
                    status: 'loading',
                    reward_token: 'IAG',
                    rewards_url: 'https://iagon.com/staking',
                    blockchain: 'cardano',
                    total_positions: 0
                };
            }
            renderDefiGovernance(initialStaking, defiData, exchangeStablecoins, nativeStablecoins, null);
        }

        // Show subtle updating indicator for staking section (only if no cache)
        if (!cached) {
            const stakingSection = document.querySelector('.defi-gov-subsection');
            if (stakingSection) {
                const header = stakingSection.querySelector('.defi-gov-subsection-header');
                if (header) {
                    const indicator = document.createElement('span');
                    indicator.className = 'staking-update-indicator';
                    indicator.id = 'stakingUpdateIndicator';
                    indicator.textContent = ' Loading staking...';
                    indicator.style.cssText = 'font-size: 0.8em; opacity: 0.6; font-weight: normal;';
                    header.appendChild(indicator);
                }
            }
        }

        // Phase 3: Fetch ALL wallet staking + governance in parallel (background)
        const adaDelegation = { totalAda: 0, stakedAda: 0, pools: [], undelegatedWallets: [] };

        // Pre-compute ADA delegation totals from wallet balances
        for (const wallet of cardanoWallets) {
            adaDelegation.totalAda += parseFloat(wallet.balance) || 0;
        }

        // Fire all wallet requests simultaneously
        const refreshParam = forceRefresh ? '?refresh=true' : '';
        const walletPromises = cardanoWallets.map(wallet =>
            Promise.allSettled([
                authFetch(`${API_BASE}/wallets/${wallet.address}/governance${refreshParam}`),
                authFetch(`${API_BASE}/defi/staking/${wallet.address}${refreshParam}`)
            ]).then(results => ({ wallet, results }))
        );

        const walletResults = await Promise.allSettled(walletPromises);

        // Process all results
        const allStaking = {};
        for (const settled of walletResults) {
            if (settled.status !== 'fulfilled') continue;
            const { wallet, results } = settled.value;
            const [govResult, stakingResult] = results;

            const walletBalance = parseFloat(wallet.balance) || 0;

            // Process governance result
            let walletDelegated = false;
            if (govResult.status === 'fulfilled' && govResult.value.ok) {
                try {
                    const govData = await govResult.value.json();
                    if (govData.pool && govData.pool.pool_id) {
                        walletDelegated = true;
                        adaDelegation.stakedAda += walletBalance;
                        const existingPool = adaDelegation.pools.find(p => p.pool_id === govData.pool.pool_id);
                        if (!existingPool) {
                            adaDelegation.pools.push({
                                pool_id: govData.pool.pool_id,
                                name: govData.pool.name || 'Unknown Pool',
                                ticker: govData.pool.ticker || ''
                            });
                        }
                    }
                } catch (e) {
                    console.error(`[DeFi] Governance parse error for ${wallet.address.slice(0,15)}:`, e);
                }
            }
            if (!walletDelegated && walletBalance > 1) {
                adaDelegation.undelegatedWallets.push({
                    address: wallet.address,
                    label: wallet.label || null,
                    balance: walletBalance
                });
            }

            // Process staking result
            try {
                if (stakingResult.status !== 'fulfilled') continue;
                const stakingData = await stakingResult.value.json();

                for (const [protocol, data] of Object.entries(stakingData.protocols || {})) {
                    if (!allStaking[protocol]) {
                        allStaking[protocol] = {
                            staked: {},
                            pending_rewards: 0,
                            pending_indy: 0,
                            pending_ada: 0,
                            accumulated_rewards: 0,
                            reward_token: data.reward_token || '',
                            reward_tokens: data.reward_tokens || [],
                            apy: data.apy || null,
                            claimed_rewards: data.claimed_rewards || 0,
                            total_earned: data.total_earned || 0,
                            rewards_url: data.rewards_url || null,
                            blockchain: data.blockchain || 'cardano',
                            category: data.category || null,
                            status: data.status || null
                        };
                    }

                    for (const stake of data.staked || []) {
                        if (!allStaking[protocol].staked[stake.token]) {
                            allStaking[protocol].staked[stake.token] = { amount: 0, positions: 0, logo_url: stake.logo_url };
                        }
                        allStaking[protocol].staked[stake.token].amount += stake.amount;
                        allStaking[protocol].staked[stake.token].positions += stake.positions;
                        if (stake.logo_url && !allStaking[protocol].staked[stake.token].logo_url) {
                            allStaking[protocol].staked[stake.token].logo_url = stake.logo_url;
                        }
                        // Clear placeholder status when real staked data arrives
                        if (stake.amount > 0 && allStaking[protocol].status) {
                            allStaking[protocol].status = null;
                        }
                    }

                    if (protocol === 'Indigo') {
                        allStaking[protocol].pending_indy += data.pending_indy || 0;
                        allStaking[protocol].pending_ada += data.pending_ada || 0;
                    } else {
                        allStaking[protocol].pending_rewards += data.pending_rewards || 0;
                        allStaking[protocol].accumulated_rewards += data.accumulated_rewards || 0;
                    }
                    allStaking[protocol].claimed_rewards += data.claimed_rewards || 0;
                    allStaking[protocol].total_earned += data.total_earned || 0;

                    if (data.apy && !allStaking[protocol].apy) {
                        allStaking[protocol].apy = data.apy;
                    }
                    if (data.rewards_url && !allStaking[protocol].rewards_url) {
                        allStaking[protocol].rewards_url = data.rewards_url;
                    }
                }
            } catch (e) {
                console.error(`Error loading staking for ${wallet.address}:`, e);
            }
        }

        // Phase 3b: Fetch Helium rewards for Solana wallets in parallel
        const solanaWallets = walletsData.wallets.filter(w => w.blockchain === 'solana');

        // Store wallet addresses for per-card refresh
        window._defiWalletAddresses = {
            cardano: cardanoWallets.map(w => w.address),
            solana: solanaWallets.map(w => w.address)
        };
        if (solanaWallets.length > 0) {
            const heliumPromises = solanaWallets.map(wallet =>
                authFetch(`${API_BASE}/defi/helium/${wallet.address}${refreshParam}`)
                    .then(r => r.ok ? r.json() : null)
                    .catch(() => null)
            );
            const heliumResults = await Promise.all(heliumPromises);

            for (const heliumData of heliumResults) {
                if (!heliumData || !heliumData.protocols) continue;
                for (const [protocol, data] of Object.entries(heliumData.protocols)) {
                    if (!allStaking[protocol]) {
                        allStaking[protocol] = {
                            staked: {},
                            pending_rewards: 0,
                            reward_token: data.reward_token || '',
                            rewards_url: data.rewards_url || null,
                            blockchain: data.blockchain || 'solana',
                            category: data.category || null,
                            status: data.status || null
                        };
                    }
                    for (const stake of data.staked || []) {
                        if (!allStaking[protocol].staked[stake.token]) {
                            allStaking[protocol].staked[stake.token] = { amount: 0, positions: 0, logo_url: stake.logo_url };
                        }
                        allStaking[protocol].staked[stake.token].amount += stake.amount;
                        allStaking[protocol].staked[stake.token].positions += stake.positions;
                    }
                    allStaking[protocol].pending_rewards += data.pending_rewards || 0;
                }
            }
        }

        // Store staking totals for portfolio calculation
        stakingTotals = {};
        for (const [protocol, data] of Object.entries(allStaking)) {
            for (const [token, stakeData] of Object.entries(data.staked || {})) {
                if (!stakingTotals[token]) stakingTotals[token] = 0;
                stakingTotals[token] += stakeData.amount;
            }
            if (data.reward_token && data.pending_rewards > 0) {
                if (!stakingTotals[data.reward_token]) stakingTotals[data.reward_token] = 0;
                stakingTotals[data.reward_token] += data.pending_rewards;
            }
        }

        // Phase 4: Re-render with full fresh data
        renderDefiGovernance(allStaking, defiData, exchangeStablecoins, nativeStablecoins, adaDelegation);

        document.body.classList.remove('staking-loading');
        updateTotalPortfolioValue();

        // Cache the complete result
        setCachedDefi({ defiData, allStaking, exchangeStablecoins, nativeStablecoins, adaDelegation });
        updateDefiTimestamp();

        // Auto-refresh DePIN cards that timed out (fetch via dedicated endpoint in background)
        for (const [protocol, data] of Object.entries(allStaking)) {
            if (data.category === 'depin' && data.status === 'timeout') {
                console.log(`[DePIN] ${protocol} timed out in batch — auto-refreshing via dedicated endpoint`);
                const btn = document.querySelector(`#depin-card-${protocol} .card-refresh-btn`);
                refreshDepinCard(protocol, btn);  // fire-and-forget, no await
            }
        }

    } catch (error) {
        console.error('Error loading DeFi & Governance:', error);
        // Only show error state if we had no cached data
        if (!cached) {
            setSafeHTML(content, '<p class="empty-state">Error loading DeFi & Governance data.</p>');
        }
        document.body.classList.remove('staking-loading');
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();
    } finally {
        setDefiRefreshBar(false);
    }
}

// Chain badge helper (shared across DeFi/Governance sections)
function getGovChainBadge(chain) {
    const badges = {
        'cardano': '<span class="chain-badge cardano" title="Cardano">ADA</span>',
        'ethereum': '<span class="chain-badge ethereum" title="Ethereum">ETH</span>',
        'solana': '<span class="chain-badge solana" title="Solana">SOL</span>'
    };
    return badges[chain] || badges['cardano'];
}

// Render consolidated DeFi & Governance section (calls DeFi immediately, defers Governance)
function renderDefiGovernance(allStaking, defiData, exchangeStablecoins, nativeStablecoins = [], adaDelegation = null) {
    renderDefiContent(allStaking, defiData, exchangeStablecoins, nativeStablecoins, adaDelegation);
    // Store data for lazy governance rendering
    _govRenderData = { defiData, allStaking };
    _govRendered = false;
    // Only render governance if that tab is currently active
    const govTab = document.getElementById('governanceTab');
    if (govTab && govTab.classList.contains('active')) {
        renderGovernanceContent(defiData, allStaking);
        _govRendered = true;
    }
}

// Render DeFi tab: Staked Positions + Stablecoins + Other DeFi Tokens
function renderDefiContent(allStaking, defiData, exchangeStablecoins, nativeStablecoins = [], adaDelegation = null) {
    const content = document.getElementById('defiGovernanceContent');
    const summary = document.getElementById('defiGovernanceSummary');

    if (!content) return;

    let html = '';
    let totalStakedValue = 0;
    let totalStableValue = 0;
    let stakedCount = 0;

    // ========================================
    // SECTION 1: STAKED POSITIONS
    // ========================================
    // Separate DePIN protocols from staking protocols
    const allProtocols = Object.keys(allStaking);
    const depinProtocols = allProtocols.filter(p => allStaking[p].category === 'depin');
    const protocols = allProtocols.filter(p => allStaking[p].category !== 'depin');
    const liquidStakingPositions = defiData.positions_by_category?.['Liquid Staking'] || [];
    const hasAdaDelegation = adaDelegation && adaDelegation.totalAda > 0;
    const hasStakedSection = protocols.length > 0 || hasAdaDelegation || liquidStakingPositions.length > 0 || exchangeStakedAssets.length > 0;

    if (hasStakedSection) {
        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">🔒</span>
                <span class="subsection-title">Staked Positions</span>
                <button class="staking-refresh-btn" title="Refresh staking data">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                </button>
            </div>
            <div class="defi-gov-cards">`;

        // --- ADA Delegation Card (pinned first) ---
        if (hasAdaDelegation) {
            const adaPrice = prices['ADA'] || 0;
            const stakedUsd = adaDelegation.stakedAda * adaPrice;
            totalStakedValue += stakedUsd;
            if (adaDelegation.stakedAda > 0) stakedCount++;

            const totalFormatted = adaDelegation.totalAda.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0});
            const pctDelegated = adaDelegation.totalAda > 0
                ? Math.floor((adaDelegation.stakedAda / adaDelegation.totalAda) * 10000) / 100 : 0;

            let delegationDetailHtml;
            if (adaDelegation.undelegatedWallets.length === 0) {
                delegationDetailHtml = `<div class="ada-delegation-detail">${blurValue(totalFormatted)} ADA (${pctDelegated}% delegated)</div>`;
            } else {
                const escHtml = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
                const undelegatedItems = adaDelegation.undelegatedWallets.map(w => {
                    const shortAddr = w.address.slice(0, 8) + '...' + w.address.slice(-4);
                    const displayLabel = w.label ? escHtml(w.label) : shortAddr;
                    const balFormatted = w.balance.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0});
                    return `<div class="undelegated-wallet-item" onclick="event.stopPropagation(); navigator.clipboard.writeText('${w.address}').then(() => { const el = this.querySelector('.copy-feedback'); el.style.opacity='1'; setTimeout(() => el.style.opacity='0', 1200); })">
                        <div class="undelegated-wallet-row">
                            <span class="undelegated-label">${displayLabel}</span>
                            <span class="undelegated-balance">${balFormatted} ADA</span>
                        </div>
                        <span class="undelegated-addr">${shortAddr}</span>
                        <span class="copy-feedback">Copied!</span>
                    </div>`;
                }).join('');
                delegationDetailHtml = `<div class="ada-delegation-detail">${blurValue(totalFormatted)} ADA <span class="delegation-pct-link" tabindex="0">(${pctDelegated}% delegated)<div class="undelegated-tooltip"><div class="undelegated-tooltip-header">Undelegated Wallets</div>${undelegatedItems}</div></span></div>`;
            }

            let poolInfoHtml = '';
            if (adaDelegation.pools.length > 0) {
                const escHtml = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
                const poolLabels = adaDelegation.pools.map(p => p.ticker ? `[${escHtml(p.ticker)}] ${escHtml(p.name)}` : escHtml(p.name));
                poolInfoHtml = `<div class="pool-info">\u2192 ${poolLabels.join(', ')}</div>`;
            }

            html += `
                <div class="defi-gov-card staked">
                    <div class="card-header">
                        <span class="token-logo-wrap"><img src="${getLogoKitUrl('ADA', 32)}" alt="ADA" class="token-logo-staking" onerror="this.parentElement.innerHTML='<span class=\\'logo-fallback\\'>ADA</span>'"></span>
                        <span class="protocol-name"><span class="chain-badge cardano" title="Cardano">ADA</span> ADA Delegation</span>
                        <span class="liquid-badge">\uD83D\uDCA7 Liquid</span>
                    </div>
                    ${delegationDetailHtml}
                    <div class="card-value">${formatUSDBlur(stakedUsd)}</div>
                    ${poolInfoHtml}
                </div>
            `;
        }

        // --- Protocol Staking Cards ---
        for (const protocol of protocols) {
            const protocolData = allStaking[protocol];
            const stakes = protocolData.staked;
            const rewardsUrl = protocolData.rewards_url;

            for (const [token, data] of Object.entries(stakes)) {
                const tokenPrice = prices[token] || 0;
                const usdValue = data.amount * tokenPrice;
                totalStakedValue += usdValue;
                stakedCount++;

                // Check if this token has governance
                const govInfo = GOVERNANCE_LINKS[token];

                // Build pending rewards display
                let pendingHtml = '';
                let totalPendingUsd = 0;

                if (protocol === 'Indigo') {
                    const pendingIndy = protocolData.pending_indy || 0;
                    const pendingAda = protocolData.pending_ada || 0;
                    if (pendingIndy > 0 || pendingAda > 0) {
                        const indyUsd = pendingIndy * (prices['INDY'] || 0);
                        const adaUsd = pendingAda * (prices['ADA'] || 0);
                        totalPendingUsd = indyUsd + adaUsd;
                        pendingHtml = `<div class="staking-pending-compact">`;
                        if (pendingIndy > 0) {
                            pendingHtml += `<span class="pending-item">${pendingIndy.toFixed(2)} INDY</span>`;
                        }
                        if (pendingAda > 0) {
                            pendingHtml += `<span class="pending-item">${pendingAda.toFixed(2)} ADA</span>`;
                        }
                        pendingHtml += `</div>`;
                    }
                } else {
                    const pendingRewards = protocolData.pending_rewards || 0;
                    const rewardToken = protocolData.reward_token || '';
                    if (pendingRewards > 0 && rewardToken) {
                        totalPendingUsd = pendingRewards * (prices[rewardToken] || 0);
                        pendingHtml = `<div class="staking-pending-compact">
                            <span class="pending-item">${pendingRewards.toFixed(2)} ${rewardToken}</span>
                        </div>`;
                    }
                }

                // Chain badge for staked position (read from protocol data, fallback to cardano)
                const stakingChain = protocolData.blockchain || 'cardano';
                const chainBadge = getGovChainBadge(stakingChain);

                // Use backend logo URL or fallback to LogoKit
                const tokenLogoUrl = data.logo_url || getLogoKitUrl(token, 32);

                html += `
                    <div class="defi-gov-card staked">
                        <div class="card-header">
                            <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${token}" class="token-logo-staking"></span>
                            <span class="protocol-name">${chainBadge} ${protocol}</span>
                            <span class="staked-badge">Staked</span>
                        </div>
                        <div class="card-amount">${formatCryptoBlur(data.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4}), token)}</div>
                        <div class="card-value">${formatUSDBlur(usdValue)}</div>
                        ${pendingHtml ? `<div class="card-pending">Pending: ${pendingHtml}</div>` : ''}
                        <div class="card-actions">
                            ${rewardsUrl ? `<a href="${rewardsUrl}" target="_blank" rel="noopener" class="action-link">Rewards</a>` : ''}
                            ${govInfo ? `<a href="${govInfo.url}" target="_blank" rel="noopener" class="action-link gov-link">Vote</a>` : ''}
                        </div>
                    </div>
                `;
            }
        }

        // --- Liquid Staking Cards ---
        for (const pos of liquidStakingPositions) {
            const displayName = pos.token || pos.asset_name;
            const tokenPrice = prices[displayName] || prices[pos.asset_name] || prices[pos.token] || 0;
            const usdValue = (pos.quantity || 0) * tokenPrice;
            totalStakedValue += usdValue;
            stakedCount++;

            const tokenLogoUrl = getLogoKitUrl(displayName, 32);
            const lsChain = pos.blockchain || 'cardano';
            const chainBadge = getGovChainBadge(lsChain);
            const formattedQty = (pos.quantity || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4});

            html += `
                <div class="defi-gov-card staked">
                    <div class="card-header">
                        <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${displayName}" class="token-logo-staking" onerror="this.parentElement.innerHTML='<span class=\\'logo-fallback\\'>${displayName.slice(0,3)}</span>'"></span>
                        <span class="protocol-name">${chainBadge} ${pos.protocol}</span>
                        <span class="liquid-badge">\uD83D\uDCA7 Liquid</span>
                    </div>
                    <div class="card-amount">${formatCryptoBlur(formattedQty, displayName)}</div>
                    <div class="card-value">${usdValue > 0 ? formatUSDBlur(usdValue) : '--'}</div>
                </div>
            `;
        }

        // --- Exchange Staked Cards ---
        for (const staked of exchangeStakedAssets) {
            const usdValue = staked.usd_value || 0;
            totalStakedValue += usdValue;
            stakedCount++;

            const tokenLogoUrl = getLogoKitUrl(staked.currency, 32);
            const apyBadge = staked.apy > 0
                ? `<span class="apy-badge">${(staked.apy * 100).toFixed(2)}% APY</span>` : '';

            html += `
                <div class="defi-gov-card staked exchange-staked">
                    <div class="card-header">
                        <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${staked.currency}" class="token-logo-staking"></span>
                        <span class="protocol-name">${staked.exchangeName}</span>
                        <span class="exchange-staked-badge">Exchange Staked</span>
                        ${apyBadge}
                    </div>
                    <div class="card-amount">${formatCryptoBlur(staked.staked_balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6}), staked.currency)}</div>
                    <div class="card-value">${formatUSDBlur(usdValue)}</div>
                    <div class="card-note">Included in exchange total</div>
                </div>
            `;
        }

        html += `</div></div>`;
    }

    // ========================================
    // SECTION 2: DePIN (Decentralized Physical Infrastructure)
    // ========================================
    if (depinProtocols.length > 0) {
        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">\uD83D\uDCE1</span>
                <span class="subsection-title">DePIN</span>
            </div>
            <div class="defi-gov-cards">`;

        for (const protocol of depinProtocols) {
            const protocolData = allStaking[protocol];
            const rewardsUrl = protocolData.rewards_url;
            const stakingChain = protocolData.blockchain || 'cardano';
            const chainBadge = getGovChainBadge(stakingChain);
            const refreshBtn = `<button class="card-refresh-btn" data-protocol="${protocol}" title="Refresh ${protocol}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>`;

            // Loading state — show placeholder card with spinner
            if (protocolData.status === 'loading') {
                const fallbackToken = protocolData.reward_token || protocol;
                const tokenLogoUrl = getLogoKitUrl(fallbackToken, 32);
                html += `
                    <div class="defi-gov-card staked depin-loading" id="depin-card-${protocol}">
                        <div class="card-header">
                            <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${fallbackToken}" class="token-logo-staking"></span>
                            <span class="protocol-name">${chainBadge} ${protocol}</span>
                            <span class="depin-badge">\uD83D\uDCE1 Mining</span>
                        </div>
                        <div class="card-loading-msg"><span class="depin-spinner"></span> Scanning staking data...</div>
                    </div>
                `;
                continue;
            }

            // Timeout/error state — show placeholder card with retry
            if (protocolData.status === 'timeout') {
                const fallbackToken = protocolData.reward_token || protocol;
                const tokenLogoUrl = getLogoKitUrl(fallbackToken, 32);
                html += `
                    <div class="defi-gov-card staked depin-timeout" id="depin-card-${protocol}">
                        <div class="card-header">
                            <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${fallbackToken}" class="token-logo-staking"></span>
                            <span class="protocol-name">${chainBadge} ${protocol}</span>
                            <span class="depin-badge">\uD83D\uDCE1 Mining</span>
                            ${refreshBtn}
                        </div>
                        <div class="card-timeout-msg">Data unavailable — timed out</div>
                    </div>
                `;
                continue;
            }

            // No staking found — show card with refresh option
            if (protocolData.status === 'no_staking') {
                const fallbackToken = protocolData.reward_token || protocol;
                const tokenLogoUrl = getLogoKitUrl(fallbackToken, 32);
                html += `
                    <div class="defi-gov-card staked depin-no-data" id="depin-card-${protocol}">
                        <div class="card-header">
                            <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${fallbackToken}" class="token-logo-staking"></span>
                            <span class="protocol-name">${chainBadge} ${protocol}</span>
                            <span class="depin-badge">\uD83D\uDCE1 Mining</span>
                            ${refreshBtn}
                        </div>
                        <div class="card-timeout-msg">No staked ${fallbackToken} found</div>
                        <div class="card-actions">
                            ${protocolData.rewards_url ? `<a href="${protocolData.rewards_url}" target="_blank" rel="noopener" class="action-link">Staking</a>` : ''}
                        </div>
                    </div>
                `;
                continue;
            }

            const stakes = protocolData.staked;
            for (const [token, data] of Object.entries(stakes)) {
                const tokenPrice = prices[token] || 0;
                const usdValue = data.amount * tokenPrice;
                totalStakedValue += usdValue;
                stakedCount++;

                // Build pending rewards display
                let pendingHtml = '';
                const pendingRewards = protocolData.pending_rewards || 0;
                const rewardToken = protocolData.reward_token || '';
                if (pendingRewards > 0 && rewardToken) {
                    pendingHtml = `<div class="staking-pending-compact">
                        <span class="pending-item">${pendingRewards.toFixed(2)} ${rewardToken}</span>
                    </div>`;
                }

                const tokenLogoUrl = data.logo_url || getLogoKitUrl(token, 32);

                html += `
                    <div class="defi-gov-card staked" id="depin-card-${protocol}">
                        <div class="card-header">
                            <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${token}" class="token-logo-staking"></span>
                            <span class="protocol-name">${chainBadge} ${protocol}</span>
                            <span class="depin-badge">\uD83D\uDCE1 Mining</span>
                            ${refreshBtn}
                        </div>
                        <div class="card-amount">${formatCryptoBlur(data.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4}), token)}</div>
                        <div class="card-value">${formatUSDBlur(usdValue)}</div>
                        ${pendingHtml ? `<div class="card-pending">Pending: ${pendingHtml}</div>` : ''}
                        <div class="card-actions">
                            ${rewardsUrl ? `<a href="${rewardsUrl}" target="_blank" rel="noopener" class="action-link">Rewards</a>` : ''}
                        </div>
                    </div>
                `;
            }
        }

        html += `</div></div>`;
    }

    // ========================================
    // SECTION 3: STABLECOINS (All Chains + Exchange)
    // ========================================
    const walletStablecoins = defiData.positions_by_category?.['Stablecoins'] || [];
    const MIN_STABLE_VALUE = 1.00; // Minimum USD value to display

    // Chain badge helper
    const getChainBadge = (chain) => {
        const badges = {
            'cardano': '<span class="chain-badge cardano" title="Cardano">ADA</span>',
            'ethereum': '<span class="chain-badge ethereum" title="Ethereum">ETH</span>',
            'solana': '<span class="chain-badge solana" title="Solana">SOL</span>',
            'exchange': '<span class="chain-badge exchange" title="Exchange">CEX</span>'
        };
        return badges[chain] || '';
    };

    // Combine stablecoins from all sources with chain tracking
    // Structure: { symbol: { chains: { cardano: amount, ethereum: amount, solana: amount, exchange: amount } } }
    const stableTotals = {};

    // Cardano DeFi stablecoins
    for (const pos of walletStablecoins) {
        if (!stableTotals[pos.asset_name]) {
            stableTotals[pos.asset_name] = { chains: {} };
        }
        if (!stableTotals[pos.asset_name].chains.cardano) {
            stableTotals[pos.asset_name].chains.cardano = 0;
        }
        stableTotals[pos.asset_name].chains.cardano += pos.quantity;
    }

    // Exchange stablecoins
    for (const asset of exchangeStablecoins) {
        if (!stableTotals[asset.symbol]) {
            stableTotals[asset.symbol] = { chains: {} };
        }
        if (!stableTotals[asset.symbol].chains.exchange) {
            stableTotals[asset.symbol].chains.exchange = 0;
        }
        stableTotals[asset.symbol].chains.exchange += asset.balance;
    }

    // Native stablecoins from all chains (ETH, SOL, etc.)
    for (const asset of nativeStablecoins) {
        const chain = asset.chain || 'cardano';
        // Skip cardano since those are handled by DeFi summary
        if (chain === 'cardano') continue;

        if (!stableTotals[asset.symbol]) {
            stableTotals[asset.symbol] = { chains: {} };
        }
        if (!stableTotals[asset.symbol].chains[chain]) {
            stableTotals[asset.symbol].chains[chain] = 0;
        }
        stableTotals[asset.symbol].chains[chain] += asset.balance;
    }

    const hasStablecoins = Object.keys(stableTotals).length > 0;

    if (hasStablecoins) {
        // Calculate totals and sort
        const stableEntries = Object.entries(stableTotals).map(([symbol, data]) => {
            const total = Object.values(data.chains).reduce((sum, val) => sum + val, 0);
            return { symbol, chains: data.chains, total };
        }).filter(s => s.total >= 0.01); // Skip dust

        stableEntries.sort((a, b) => b.total - a.total);

        // Separate visible and hidden
        const visibleStables = [];
        const hiddenStables = [];

        for (const stable of stableEntries) {
            if (stable.total >= MIN_STABLE_VALUE) {
                visibleStables.push(stable);
                totalStableValue += stable.total;
            } else {
                hiddenStables.push(stable);
            }
        }

        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">💰</span>
                <span class="subsection-title">Stablecoins</span>
            </div>
            <div class="defi-gov-list stablecoins-list">`;

        // Render visible stablecoins
        for (const { symbol, chains, total } of visibleStables) {
            const chainBadges = Object.keys(chains)
                .filter(c => chains[c] > 0)
                .map(c => getChainBadge(c))
                .join('');

            // Build breakdown tooltip
            const breakdownParts = [];
            if (chains.cardano) breakdownParts.push(`Cardano: ${chains.cardano.toFixed(2)}`);
            if (chains.ethereum) breakdownParts.push(`Ethereum: ${chains.ethereum.toFixed(2)}`);
            if (chains.solana) breakdownParts.push(`Solana: ${chains.solana.toFixed(2)}`);
            if (chains.exchange) breakdownParts.push(`Exchange: ${chains.exchange.toFixed(2)}`);
            const breakdown = breakdownParts.join(' · ');

            // Get token logo with fallback
            const stableLogoUrl = getLogoKitUrl(symbol, 32);

            html += `
                <div class="defi-gov-line stable-line">
                    <span class="line-logo"><img src="${stableLogoUrl}" alt="${symbol}" onerror="this.parentElement.innerHTML='<span class=\\'logo-fallback\\'>${symbol.slice(0,3)}</span>'"></span>
                    <span class="line-token">${symbol}</span>
                    <span class="line-chains">${chainBadges}</span>
                    <span class="line-amount" title="${breakdown}">${blurValue(total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}))}</span>
                    <span class="line-value">~${formatUSDBlur(total)}</span>
                </div>
            `;
        }

        if (visibleStables.length === 0 && hiddenStables.length === 0) {
            html += `<div class="defi-empty-line">No stablecoins held</div>`;
        } else if (visibleStables.length === 0 && hiddenStables.length > 0) {
            html += `<div class="defi-empty-line">No stablecoins over $1.00</div>`;
        }

        // Render hidden stablecoins dropdown if any
        if (hiddenStables.length > 0) {
            const hiddenTotal = hiddenStables.reduce((sum, s) => sum + s.total, 0);
            html += `
                <div class="hidden-stables-dropdown">
                    <button class="hidden-stables-toggle">
                        <span class="toggle-icon">▶</span>
                        <span class="toggle-text">Hidden Stablecoins (${hiddenStables.length})</span>
                        <span class="toggle-value">~${formatUSDBlur(hiddenTotal)}</span>
                    </button>
                    <div class="hidden-stables-content" style="display: none;">
            `;

            for (const { symbol, chains, total } of hiddenStables) {
                const chainBadges = Object.keys(chains)
                    .filter(c => chains[c] > 0)
                    .map(c => getChainBadge(c))
                    .join('');

                // Get token logo with fallback
                const hiddenStableLogoUrl = getLogoKitUrl(symbol, 32);

                html += `
                    <div class="defi-gov-line stable-line hidden-stable">
                        <span class="line-logo"><img src="${hiddenStableLogoUrl}" alt="${symbol}" onerror="this.parentElement.innerHTML='<span class=\\'logo-fallback\\'>${symbol.slice(0,3)}</span>'"></span>
                        <span class="line-token">${symbol}</span>
                        <span class="line-chains">${chainBadges}</span>
                        <span class="line-amount">${blurValue(total.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 6}))}</span>
                        <span class="line-value">~${formatUSDBlur(total)}</span>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        html += `</div></div>`;
    }

    // ========================================
    // SECTION 4: OTHER DEFI TOKENS
    // ========================================
    const otherCategories = ['Liquidity Pool Tokens', 'Staking Receipts', 'Protocol Receipts', 'Synthetic Assets', 'Reserve Tokens'];

    for (const category of otherCategories) {
        const positions = defiData.positions_by_category?.[category] || [];
        if (positions.length === 0) continue;

        const categoryIcons = {
            'Liquidity Pool Tokens': '💱',
            'Staking Receipts': '📄',
            'Protocol Receipts': '📃',
            'Synthetic Assets': '💵',
            'Reserve Tokens': '🏦'
        };

        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">${categoryIcons[category] || '📊'}</span>
                <span class="subsection-title">${category}</span>
                <span class="subsection-count">${positions.length}</span>
            </div>
            <div class="defi-gov-tokens">`;

        for (const pos of positions) {
            html += `
                <div class="defi-token-chip">
                    <span class="chip-name">${pos.asset_name}</span>
                    <span class="chip-amount">${blurValue(pos.quantity_formatted)}</span>
                </div>
            `;
        }

        html += `</div></div>`;
    }

    // Empty state
    if (html === '') {
        html = '<p class="empty-state">No DeFi positions found.</p>';
    }

    setSafeHTML(content, html);

    // Attach click handlers (DOMPurify strips inline onclick/onerror attributes)
    content.querySelectorAll('.card-refresh-btn[data-protocol]').forEach(btn => {
        btn.addEventListener('click', () => refreshDepinCard(btn.dataset.protocol, btn));
    });
    content.querySelectorAll('.staking-refresh-btn').forEach(btn => {
        btn.addEventListener('click', () => refreshStakingOnly(btn));
    });
    content.querySelectorAll('.hidden-stables-toggle').forEach(btn => {
        btn.addEventListener('click', () => toggleHiddenStables(btn));
    });
    content.querySelectorAll('.token-logo-staking').forEach(img => {
        img.addEventListener('error', function() {
            const alt = this.alt || '';
            this.parentElement.innerHTML = `<span class="logo-fallback">${alt.slice(0,3)}</span>`;
        });
    });

    // Update DeFi summary
    if (summary) {
        const totalValue = totalStakedValue + totalStableValue;
        setSafeHTML(summary, `
            <span class="defi-gov-total">${formatUSDBlur(totalValue)}</span>
        `);
    }
}

// Render Governance tab: Governance Tokens (wallet + staked combined)
function renderGovernanceContent(defiData, allStaking = {}) {
    const content = document.getElementById('governanceContent');
    const summary = document.getElementById('governanceSummary');

    if (!content) return;

    let html = '';
    let totalGovValue = 0;
    let governanceTokenCount = 0;

    // Build combined governance token map: wallet holdings + staked amounts
    const govTokenMap = {};

    // 1. Wallet (unstaked) governance positions
    const governancePositions = defiData.positions_by_category?.['Governance Tokens'] || [];
    for (const pos of governancePositions) {
        const token = pos.asset_name;
        if (!govTokenMap[token]) {
            govTokenMap[token] = { wallet: 0, staked: 0, blockchain: pos.blockchain || 'cardano', logo_url: null };
        }
        govTokenMap[token].wallet += pos.quantity || 0;
        if (pos.logo_url && !govTokenMap[token].logo_url) {
            govTokenMap[token].logo_url = pos.logo_url;
        }
    }

    // 2. Staked governance tokens (LQ, INDY, etc. are still usable in governance)
    for (const [protocol, data] of Object.entries(allStaking)) {
        for (const [token, stakeData] of Object.entries(data.staked || {})) {
            if (GOVERNANCE_LINKS[token]) {
                if (!govTokenMap[token]) {
                    govTokenMap[token] = { wallet: 0, staked: 0, blockchain: data.blockchain || 'cardano', logo_url: null };
                }
                govTokenMap[token].staked += stakeData.amount || 0;
                if (stakeData.logo_url && !govTokenMap[token].logo_url) {
                    govTokenMap[token].logo_url = stakeData.logo_url;
                }
            }
        }
    }

    // Build sorted list, filter out < $1 total value
    const govTokens = Object.entries(govTokenMap)
        .map(([token, data]) => {
            const total = data.wallet + data.staked;
            const tokenPrice = prices[token] || 0;
            const usdValue = total * tokenPrice;
            return { token, wallet: data.wallet, staked: data.staked, total, usdValue, blockchain: data.blockchain, logo_url: data.logo_url };
        })
        .filter(t => t.usdValue >= 1)
        .sort((a, b) => b.usdValue - a.usdValue);

    if (govTokens.length > 0) {
        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">\uD83C\uDFDB\uFE0F</span>
                <span class="subsection-title">Governance Tokens</span>
            </div>
            <div class="defi-gov-list">`;

        for (const t of govTokens) {
            totalGovValue += t.usdValue;
            governanceTokenCount++;

            const govInfo = GOVERNANCE_LINKS[t.token];
            const tokenLogoUrl = t.logo_url || getLogoKitUrl(t.token, 32);
            const totalFormatted = t.total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            // Show breakdown if both wallet and staked exist
            let amountHtml = blurValue(totalFormatted);
            if (t.staked > 0 && t.wallet > 0) {
                const walletFmt = t.wallet.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                const stakedFmt = t.staked.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                amountHtml = `<span title="${walletFmt} wallet + ${stakedFmt} staked">${blurValue(totalFormatted)}</span>`;
            } else if (t.staked > 0) {
                amountHtml = `<span title="All staked">${blurValue(totalFormatted)}</span>`;
            }

            const logoFallback = t.token.slice(0, 3);
            html += `
                <div class="defi-gov-line">
                    <span class="line-logo"><img src="${tokenLogoUrl}" alt="${t.token}" onerror="this.parentElement.innerHTML='<span class=\\'logo-fallback\\'>${logoFallback}</span>'"></span>
                    <span class="line-token">${getGovChainBadge(t.blockchain)} ${t.token}</span>
                    <span class="line-amount">${amountHtml}</span>
                    <span class="line-value">${formatUSDBlur(t.usdValue)}</span>
                    ${govInfo ? `<a href="${govInfo.url}" target="_blank" rel="noopener" class="gov-vote-link" title="Vote with ${t.token} on ${govInfo.name}">Vote</a>` : '<span class="gov-vote-placeholder"></span>'}
                </div>
            `;
        }

        html += `</div></div>`;
    }

    // Empty state
    if (html === '') {
        html = '<p class="empty-state">No governance tokens found.</p>';
    }

    setSafeHTML(content, html);

    // Update governance summary
    if (summary) {
        let summaryParts = [];
        if (governanceTokenCount > 0) {
            summaryParts.push(`${governanceTokenCount} tokens`);
        }

        setSafeHTML(summary, `
            <span class="governance-count">${summaryParts.join(' · ') || 'No tokens'}</span>
            <span class="governance-total">${formatUSDBlur(totalGovValue)}</span>
        `);
    }
}

// Refresh DeFi & Governance section
async function refreshDefiGovernance() {
    const btn = document.querySelector('.defi-governance-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    try {
        // Force refresh on backend
        const cardanoWallets = await authFetch(`${API_BASE}/wallets`).then(r => r.json());
        const refreshPromises = [];

        for (const wallet of cardanoWallets.wallets.filter(w => w.blockchain === 'cardano')) {
            refreshPromises.push(
                authFetch(`${API_BASE}/defi/staking/${wallet.address}?refresh=true`).catch(() => null)
            );
        }
        refreshPromises.push(authFetch(`${API_BASE}/defi/summary?refresh=true`).catch(() => null));

        await Promise.all(refreshPromises);
        await loadDefiGovernance(true);

        showStatus('DeFi & Governance refreshed');
    } catch (error) {
        console.error('Error refreshing DeFi & Governance:', error);
        showStatus('Failed to refresh DeFi & Governance', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
    }
}

// Refresh only staking positions (per-section refresh)
async function refreshStakingOnly(btn) {
    if (btn) {
        btn.classList.add('refreshing');
        btn.disabled = true;
    }

    try {
        const walletsResponse = await authFetch(`${API_BASE}/wallets`);
        const walletsData = await walletsResponse.json();
        const cardanoWallets = walletsData.wallets.filter(w => w.blockchain === 'cardano');

        // Refresh staking for each Cardano wallet + Helium for Solana wallets in parallel
        const solanaWallets = walletsData.wallets.filter(w => w.blockchain === 'solana');
        const stakingPromises = [
            ...cardanoWallets.map(wallet =>
                authFetch(`${API_BASE}/defi/staking/${wallet.address}?refresh=true`).catch(() => null)
            ),
            ...solanaWallets.map(wallet =>
                authFetch(`${API_BASE}/defi/helium/${wallet.address}?refresh=true`).catch(() => null)
            )
        ];
        await Promise.all(stakingPromises);

        // Reload the full DeFi view with fresh data
        await loadDefiGovernance(true);
        showStatus('Staking positions refreshed');
    } catch (error) {
        console.error('Error refreshing staking:', error);
        showStatus('Failed to refresh staking', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
            btn.disabled = false;
        }
    }
}

// Refresh a single DePIN protocol card (per-card retry)
async function refreshDepinCard(protocol, btn) {
    const cardEl = document.getElementById(`depin-card-${protocol}`);
    if (btn) {
        btn.classList.add('refreshing');
        btn.disabled = true;
    }

    // Show scanning state on card
    if (cardEl) {
        const msgEl = cardEl.querySelector('.card-timeout-msg, .card-loading-msg');
        if (msgEl) msgEl.innerHTML = '<span class="depin-spinner"></span> Scanning staking data...';
    }

    try {
        // Clear staking cache first to ensure fresh Blockfrost scan
        await authFetch(`${API_BASE}/api/cache/clear/staking-cache`, { method: 'POST' }).catch(() => {});

        // Ensure wallet addresses are available (may not be loaded yet from fire-and-forget fetch)
        if (!window._defiWalletAddresses) {
            try {
                const r = await authFetch(`${API_BASE}/wallets`);
                const data = await r.json();
                window._defiWalletAddresses = {
                    cardano: data.wallets.filter(w => w.blockchain === 'cardano').map(w => w.address),
                    solana: data.wallets.filter(w => w.blockchain === 'solana').map(w => w.address)
                };
            } catch (e) {
                console.error('Failed to fetch wallet addresses for refresh:', e);
            }
        }

        const addrs = window._defiWalletAddresses || {};
        let endpoints = [];

        if (protocol === 'Iagon') {
            endpoints = (addrs.cardano || []).map(addr =>
                authFetch(`${API_BASE}/defi/iagon/${addr}?refresh=true`).then(r => {
                    if (!r.ok) console.warn(`[DePIN] Iagon fetch for ${addr.slice(0,15)}... returned ${r.status}`);
                    return r.ok ? r.json() : null;
                }).catch(e => { console.error(`[DePIN] Iagon fetch error:`, e); return null; })
            );
        } else if (protocol === 'Helium') {
            endpoints = (addrs.solana || []).map(addr =>
                authFetch(`${API_BASE}/defi/helium/${addr}?refresh=true`).then(r => {
                    if (!r.ok) console.warn(`[DePIN] Helium fetch for ${addr.slice(0,15)}... returned ${r.status}`);
                    return r.ok ? r.json() : null;
                }).catch(e => { console.error(`[DePIN] Helium fetch error:`, e); return null; })
            );
        }

        console.log(`[DePIN] Fetching ${protocol} data from ${endpoints.length} wallets...`);
        const results = await Promise.all(endpoints);
        console.log(`[DePIN] ${protocol} results:`, results.map(r => r ? `protocols: ${Object.keys(r.protocols || {}).join(',')}` : 'null'));

        // Aggregate results across wallets
        let totalAmount = 0, pendingRewards = 0;
        let rewardToken = '', rewardsUrl = '', token = '', logoUrl = '', blockchain = '';
        let hasData = false;

        for (const data of results) {
            if (!data?.protocols?.[protocol]) continue;
            hasData = true;
            const pData = data.protocols[protocol];
            rewardToken = pData.reward_token || rewardToken;
            rewardsUrl = pData.rewards_url || rewardsUrl;
            blockchain = pData.blockchain || blockchain;
            pendingRewards += pData.pending_rewards || 0;

            for (const stake of pData.staked || []) {
                token = stake.token || token;
                totalAmount += stake.amount || 0;
                logoUrl = stake.logo_url || logoUrl;
            }
        }

        if (hasData && cardEl) {
            const tokenPrice = prices[token] || 0;
            const usdValue = totalAmount * tokenPrice;
            const chainBadge = getGovChainBadge(blockchain || 'cardano');
            const tokenLogoUrl = logoUrl || getLogoKitUrl(token, 32);
            const refreshBtnHtml = `<button class="card-refresh-btn" data-protocol="${protocol}" title="Refresh ${protocol}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>`;

            let pendingHtml = '';
            if (pendingRewards > 0 && rewardToken) {
                pendingHtml = `<div class="card-pending">Pending: <div class="staking-pending-compact"><span class="pending-item">${pendingRewards.toFixed(2)} ${rewardToken}</span></div></div>`;
            }

            setSafeHTML(cardEl, `
                <div class="card-header">
                    <span class="token-logo-wrap"><img src="${tokenLogoUrl}" alt="${token}" class="token-logo-staking"></span>
                    <span class="protocol-name">${chainBadge} ${protocol}</span>
                    <span class="depin-badge">\uD83D\uDCE1 Mining</span>
                    ${refreshBtnHtml}
                </div>
                <div class="card-amount">${formatCryptoBlur(totalAmount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4}), token)}</div>
                <div class="card-value">${formatUSDBlur(usdValue)}</div>
                ${pendingHtml}
                <div class="card-actions">
                    ${rewardsUrl ? `<a href="${rewardsUrl}" target="_blank" rel="noopener" class="action-link">Rewards</a>` : ''}
                </div>
            `);
            // Attach click handler (DOMPurify strips inline onclick)
            const newBtn = cardEl.querySelector('.card-refresh-btn[data-protocol]');
            if (newBtn) newBtn.addEventListener('click', () => refreshDepinCard(protocol, newBtn));
            // Attach image error handler
            const img = cardEl.querySelector('.token-logo-staking');
            if (img) img.addEventListener('error', function() { this.parentElement.innerHTML = `<span class="logo-fallback">${token.slice(0,3)}</span>`; });
            cardEl.classList.remove('depin-timeout', 'depin-no-data', 'depin-loading');

            // Update frontend localStorage cache so data persists across renders
            try {
                const cachedDefi = getCachedDefi();
                if (cachedDefi && cachedDefi.allStaking) {
                    cachedDefi.allStaking[protocol] = {
                        staked: { [token]: { amount: totalAmount, positions: 1, logo_url: logoUrl } },
                        pending_rewards: pendingRewards,
                        reward_token: rewardToken,
                        rewards_url: rewardsUrl,
                        blockchain: blockchain || 'cardano',
                        category: 'depin',
                        status: null
                    };
                    setCachedDefi(cachedDefi);
                }
            } catch (e) { /* cache update is best-effort */ }

            showStatus(`${protocol} data loaded`);
        } else if (cardEl) {
            showStatus(`No ${protocol} data found`, true);
        }
    } catch (error) {
        console.error(`Error refreshing ${protocol}:`, error);
        showStatus(`Failed to refresh ${protocol}`, true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
            btn.disabled = false;
        }
    }
}

// Extract staked assets from exchange data for display in staking section
function extractExchangeStakedAssets(exchanges) {
    exchangeStakedAssets = [];
    if (!exchanges) return;

    const exchangeNameMap = {
        'coinbase': 'Coinbase', 'binance': 'Binance', 'binance_us': 'Binance.US',
        'okx': 'OKX', 'bitget': 'Bitget', 'gate': 'Gate.io', 'kucoin': 'KuCoin'
    };

    for (const exchange of exchanges) {
        if (!exchange.assets) continue;
        const name = exchangeNameMap[exchange.exchange] || exchange.exchange;

        for (const asset of exchange.assets) {
            if (asset.staked_balance && asset.staked_balance > 0) {
                const price = asset.price || 0;
                exchangeStakedAssets.push({
                    exchange: exchange.exchange,
                    exchangeName: name,
                    currency: asset.currency,
                    staked_balance: asset.staked_balance,
                    usd_value: asset.staked_balance * price,
                    price: price,
                    apy: asset.staking_apy || 0
                });
            }
        }
    }
}

// Load exchange portfolio data
async function loadExchangeData() {
    const exchangesList = document.getElementById('exchangesList');
    const exchangesSummary = document.getElementById('exchangesSummary');

    if (exchangesList) {
        setSafeHTML(exchangesList, '<p class="loading-state">Loading exchange data...</p>');
    }

    try {
        // Fetch all exchanges at once
        const response = await authFetch(`${API_BASE}/exchanges/all`);

        if (!response.ok) {
            if (exchangesList) {
                const error = await response.json();
                setSafeHTML(exchangesList, `<p class="empty-state error">Error: ${error.detail || 'Failed to load exchange data'}</p>`);
            }
            return;
        }

        const data = await response.json();

        // Check if any exchanges are configured
        if (!data.exchanges || data.exchanges.length === 0) {
            if (exchangesList) {
                setSafeHTML(exchangesList, '<p class="empty-state">No exchanges configured. Add API keys to .env file.</p>');
            }
            if (exchangesSummary) {
                setSafeHTML(exchangesSummary, '<span class="exchange-status not-configured">Not configured</span>');
            }
            return;
        }

        // Store exchange total for portfolio calculation
        exchangeTotals.usd = data.total_usd || 0;

        // Extract staked assets for display in staking section
        extractExchangeStakedAssets(data.exchanges);

        // Update summary
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, `
                <span class="exchange-count">${data.exchange_count || 0} exchange${data.exchange_count !== 1 ? 's' : ''} · ${data.total_assets || 0} assets</span>
                <span class="exchange-total">${formatUSD(data.total_usd || 0)}</span>
            `);
        }

        // Render all exchanges (only if DOM exists on this page)
        if (exchangesList) {
            renderAllExchanges(data.exchanges);
        }

        // Update total portfolio value
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading exchange data:', error);
        if (exchangesList) {
            setSafeHTML(exchangesList, '<p class="empty-state error">Failed to load exchange data.</p>');
        }
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, '<span class="exchange-status error">Error</span>');
        }
    }
}

// Render all exchanges
function renderAllExchanges(exchanges) {
    const exchangesList = document.getElementById('exchangesList');

    if (!exchanges || exchanges.length === 0) {
        setSafeHTML(exchangesList, '<p class="empty-state">No exchanges configured.</p>');
        return;
    }

    let html = '';

    // Exchange logo mapping
    const exchangeLogos = {
        'coinbase': 'https://www.coinbase.com/favicon.ico',
        'binance': 'https://bin.bnbstatic.com/static/images/common/favicon.ico',
        'binance_us': 'https://www.binance.us/favicon.ico',
        'okx': 'https://static.okx.com/cdn/assets/imgs/MjAyMQ/C18EFDB60B2E2E21.png',
        'bitget': 'https://www.bitget.com/favicon.ico',
        'gate': 'https://www.gate.io/favicon.ico',
        'kucoin': 'https://www.kucoin.com/favicon.ico',
        'bybit': 'https://www.bybit.com/favicon.ico',
        'mexc': 'https://www.mexc.com/favicon.ico',
        'htx': 'https://www.htx.com/favicon.ico',
        'bingx': 'https://bingx.com/favicon.ico',
        'poloniex': 'https://poloniex.com/favicon.ico',
        'lbank': 'https://www.lbank.info/favicon.ico',
        'bitmart': 'https://www.bitmart.com/favicon.ico',
        'whitebit': 'https://whitebit.com/favicon.ico',
        'coinex': 'https://www.coinex.com/favicon.ico',
        'bitvavo': 'https://bitvavo.com/favicon.ico',
        'bitrue': 'https://www.bitrue.com/favicon.ico',
        'xt': 'https://www.xt.com/favicon.ico',
        'digifinex': 'https://www.digifinex.com/favicon.ico',
        'coinw': 'https://www.coinw.com/favicon.ico',
        'pionex': 'https://www.pionex.com/favicon.ico',
        'phemex': 'https://phemex.com/favicon.ico',
        'woox': 'https://woo.org/favicon.ico',
        'ascendex': 'https://ascendex.com/favicon.ico',
        'deribit': 'https://www.deribit.com/favicon.ico',
        'bitflyer': 'https://bitflyer.com/favicon.ico',
        'gemini': 'https://www.gemini.com/favicon.ico',
        'bitfinex': 'https://www.bitfinex.com/favicon.ico',
        'btse': 'https://www.btse.com/favicon.ico',
        'kraken': 'https://www.kraken.com/favicon.ico',
        'coinspot': 'https://www.coinspot.com.au/favicon.ico',
        'cryptocom': 'https://crypto.com/favicon.ico',
        'bitstamp': 'https://www.bitstamp.net/favicon.ico',
        'upbit': 'https://upbit.com/favicon.ico',
        'backpack': 'https://backpack.exchange/favicon.ico',
        'swyftx': 'https://swyftx.com/favicon.ico',
        'bitpanda': 'https://www.bitpanda.com/favicon.ico',
        'robinhood': 'https://robinhood.com/favicon.ico',
        'hitbtc': 'https://hitbtc.com/favicon.ico',
        'independentreserve': 'https://www.independentreserve.com/favicon.ico',
        'probit': 'https://www.probit.com/favicon.ico'
    };

    const exchangeNames = {
        'coinbase': 'Coinbase',
        'binance': 'Binance',
        'binance_us': 'Binance.US',
        'okx': 'OKX',
        'bitget': 'Bitget',
        'gate': 'Gate.io',
        'kucoin': 'KuCoin',
        'bybit': 'Bybit',
        'mexc': 'MEXC',
        'htx': 'HTX',
        'bingx': 'BingX',
        'poloniex': 'Poloniex',
        'lbank': 'LBank',
        'bitmart': 'BitMart',
        'whitebit': 'WhiteBIT',
        'coinex': 'CoinEx',
        'bitvavo': 'Bitvavo',
        'bitrue': 'Bitrue',
        'xt': 'XT.com',
        'digifinex': 'DigiFinex',
        'coinw': 'CoinW',
        'pionex': 'Pionex',
        'phemex': 'Phemex',
        'woox': 'WOO X',
        'ascendex': 'AscendEX',
        'deribit': 'Deribit',
        'bitflyer': 'BitFlyer',
        'gemini': 'Gemini',
        'bitfinex': 'Bitfinex',
        'btse': 'BTSE',
        'kraken': 'Kraken',
        'coinspot': 'CoinSpot',
        'cryptocom': 'Crypto.com',
        'bitstamp': 'Bitstamp',
        'upbit': 'Upbit',
        'backpack': 'Backpack',
        'swyftx': 'Swyftx',
        'bitpanda': 'Bitpanda',
        'robinhood': 'Robinhood',
        'hitbtc': 'HitBTC',
        'independentreserve': 'Independent Reserve',
        'probit': 'ProBit'
    };

    const exchangeFallbacks = {
        'coinbase': 'CB',
        'binance': 'BN',
        'binance_us': 'BN.US',
        'okx': 'OKX',
        'bitget': 'BG',
        'gate': 'GT',
        'kucoin': 'KC',
        'bybit': 'BY',
        'mexc': 'MX',
        'htx': 'HTX',
        'bingx': 'BX',
        'poloniex': 'PLX',
        'lbank': 'LB',
        'bitmart': 'BM',
        'whitebit': 'WB',
        'coinex': 'CEX',
        'bitvavo': 'BV',
        'bitrue': 'BR',
        'xt': 'XT',
        'digifinex': 'DFX',
        'coinw': 'CW',
        'pionex': 'PNX',
        'phemex': 'PHX',
        'woox': 'WX',
        'ascendex': 'AEX',
        'deribit': 'DRB',
        'bitflyer': 'BFY',
        'gemini': 'GMN',
        'bitfinex': 'BFX',
        'btse': 'BSE',
        'kraken': 'KRK',
        'coinspot': 'CS',
        'cryptocom': 'CDC',
        'bitstamp': 'BST',
        'upbit': 'UPB',
        'backpack': 'BPK',
        'swyftx': 'SWX',
        'bitpanda': 'BPD',
        'robinhood': 'RH',
        'hitbtc': 'HIT',
        'independentreserve': 'IR',
        'probit': 'PRB'
    };

    for (const exchange of exchanges) {
        const exchangeId = exchange.exchange;
        const exchangeName = exchangeNames[exchangeId] || exchange.name || exchangeId;
        const logoUrl = exchangeLogos[exchangeId] || '';
        const fallback = exchangeFallbacks[exchangeId] || exchangeId.substring(0, 2).toUpperCase();

        html += `
            <div class="exchange-section" data-exchange="${exchangeId}">
                <div class="exchange-header">
                    ${logoUrl ? `<img src="${logoUrl}" alt="${exchangeName}" class="exchange-logo" data-fallback="${fallback}" data-exchange-class="${exchangeId}">` : `<span class="exchange-icon ${exchangeId}">${fallback}</span>`}
                    <span class="exchange-name">${exchangeName}</span>
                    <button class="btn-exchange-sync" data-exchange-sync="${exchangeId}" title="Refresh balances from ${exchangeName}">
                        <span class="sync-icon">&#8635;</span> Sync
                    </button>
                    <span class="exchange-value">${formatUSDBlur(exchange.total_usd || 0)}</span>
                </div>
        `;

        if (exchange.error) {
            html += `
                <div class="exchange-error">
                    <p class="error-message">Error loading ${exchangeName}: ${exchange.error}</p>
                </div>
            `;
        } else if (exchange.assets && exchange.assets.length > 0) {
            html += '<div class="exchange-assets">';
            html += renderExchangeAssets(exchange.assets);
            html += '</div>';
        } else {
            html += '<div class="exchange-assets"><p class="empty-state connected-state"><span class="connected-dot"></span>Connected &mdash; no holdings above $1</p></div>';
        }

        html += '</div>';
    }

    setSafeHTML(exchangesList, html);

    // Attach event listeners after DOMPurify rendering (inline handlers are stripped)
    exchangesList.querySelectorAll('[data-exchange-sync]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            syncExchangeBalance(btn.getAttribute('data-exchange-sync'), btn);
        });
    });
    exchangesList.querySelectorAll('img.exchange-logo[data-fallback]').forEach(img => {
        img.addEventListener('error', () => {
            const fallback = img.getAttribute('data-fallback');
            const cls = img.getAttribute('data-exchange-class');
            const span = document.createElement('span');
            span.className = `exchange-icon ${cls}`;
            span.textContent = fallback;
            img.replaceWith(span);
        });
    });
    exchangesList.querySelectorAll('img.asset-logo').forEach(img => {
        img.addEventListener('error', () => { img.style.display = 'none'; });
    });
}

// Render exchange assets (helper function)
function renderExchangeAssets(assets) {
    let html = '';

    // Format balance helper
    const formatBalance = (val) => {
        if (val >= 1000) {
            return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        } else if (val >= 1) {
            return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
        } else {
            return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 });
        }
    };

    for (const asset of assets) {
        const balance = asset.balance;
        const available = asset.available_balance || balance;
        const held = asset.hold_balance || 0;
        const usdValue = asset.usd_value || 0;
        const price = asset.price || 0;

        const balanceFormatted = formatBalance(balance);
        const holdInfo = held > 0 ? `<span class="hold-indicator" title="In open orders">(${formatBalance(held)} in orders)</span>` : '';

        // Get token logo with fallback
        const tokenLogoUrl = getLogoKitUrl(asset.currency, 32);

        html += `
            <div class="exchange-asset-item">
                <div class="asset-info">
                    <img src="${tokenLogoUrl}" alt="${asset.currency}" class="asset-logo">
                    <div class="asset-text-info">
                        <span class="asset-currency">${asset.currency}</span>
                        <span class="asset-name-small">${asset.name !== asset.currency ? asset.name : ''}</span>
                    </div>
                </div>
                <div class="asset-balance">
                    <div class="balance-amount">${formatCryptoBlur(balanceFormatted, asset.currency)} ${holdInfo}</div>
                    <div class="balance-usd">${formatUSDBlur(usdValue)}</div>
                </div>
            </div>
        `;
    }

    return html;
}

// Sync exchange balances (force refresh from API)
async function syncExchangeBalance(exchangeId, btn) {
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="sync-icon spinning">&#8635;</span> Syncing...';

    // Map exchangeId to route segment (underscore → hyphen for URL)
    const routeName = exchangeId.replace(/_/g, '-');

    try {
        const response = await authFetch(`${API_BASE}/exchanges/${routeName}?refresh=true`);

        if (!response.ok) throw new Error('Refresh failed');

        const data = await response.json();

        // Update the exchange card in-place
        updateExchangeCardInPlace(exchangeId, data);

        // Update staked assets for this exchange
        exchangeStakedAssets = exchangeStakedAssets.filter(a => a.exchange !== exchangeId);
        if (data.assets) {
            const nameMap = { 'coinbase': 'Coinbase', 'binance': 'Binance', 'binance_us': 'Binance.US', 'okx': 'OKX', 'bitget': 'Bitget', 'gate': 'Gate.io', 'kucoin': 'KuCoin' };
            const name = nameMap[exchangeId] || exchangeId;
            for (const asset of data.assets) {
                if (asset.staked_balance && asset.staked_balance > 0) {
                    const price = asset.price || 0;
                    exchangeStakedAssets.push({
                        exchange: exchangeId, exchangeName: name, currency: asset.currency,
                        staked_balance: asset.staked_balance, usd_value: asset.staked_balance * price,
                        price: price, apy: asset.staking_apy || 0
                    });
                }
            }
        }

        // Recalculate exchangeTotals from all visible cards
        recalcExchangeTotals();
        updateTotalPortfolioValue();

        btn.innerHTML = '<span class="sync-icon">&#10003;</span> Done';
        setTimeout(() => {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }, 3000);
    } catch (err) {
        console.error('Sync exchange balance error:', err);
        btn.innerHTML = '<span class="sync-icon">&#10007;</span> Failed';
        setTimeout(() => {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }, 3000);
    }
}

// Update a single exchange card's value and assets in-place
function updateExchangeCardInPlace(exchangeId, data) {
    const card = document.querySelector(`.exchange-section[data-exchange="${exchangeId}"]`);
    if (!card) return;

    // Update total value
    const valueEl = card.querySelector('.exchange-value');
    if (valueEl) {
        setSafeHTML(valueEl, formatUSDBlur(data.total_usd || 0));
    }

    // Update assets list
    const assetsEl = card.querySelector('.exchange-assets');
    if (assetsEl && data.assets && data.assets.length > 0) {
        setSafeHTML(assetsEl, renderExchangeAssets(data.assets));
        // Re-attach error handlers for asset logos (DOMPurify strips onerror)
        assetsEl.querySelectorAll('img.asset-logo').forEach(img => {
            img.addEventListener('error', () => { img.style.display = 'none'; });
        });
    } else if (assetsEl && (!data.assets || data.assets.length === 0)) {
        setSafeHTML(assetsEl, '<p class="empty-state connected-state"><span class="connected-dot"></span>Connected &mdash; no holdings above $1</p>');
    }
}

// Recalculate exchangeTotals.usd from visible exchange cards
function recalcExchangeTotals() {
    let total = 0;
    document.querySelectorAll('.exchange-section .exchange-value').forEach(el => {
        const text = el.textContent.replace(/[^0-9.]/g, '');
        total += parseFloat(text) || 0;
    });
    exchangeTotals.usd = total;
}

// Load NFTs
async function loadNFTs(forceRefresh = false) {
    const nftsList = document.getElementById('nftsList');
    const nftsSummary = document.getElementById('nftsSummary');

    if (!nftsList) return;

    // Mark NFTs as loading
    document.body.classList.add('nft-loading');
    updateTotalPortfolioValue();

    setSafeHTML(nftsList, '<p class="loading-state">Loading NFTs... (this may take a moment)</p>');

    try {
        const url = forceRefresh ? `${API_BASE}/nfts?force_refresh=true` : `${API_BASE}/nfts`;
        const response = await authFetch(url);

        if (!response.ok) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading NFTs</p>');
            document.body.classList.remove('nft-loading');
            updateTotalPortfolioValue();
            return;
        }

        const data = await response.json();

        // Store Cardano NFT total and count for portfolio calculation
        nftTotals.cardano = data.total_value_usd || 0;
        nftCounts.cardano = data.total_count || 0;

        // Update Cardano chain tab stats
        const cardanoStats = document.getElementById('cardanoNftStats');
        if (cardanoStats) {
            setSafeHTML(cardanoStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary with combined totals
        updateNftSectionSummary();
        updateSummaryCardNftCounts();

        // Render NFTs
        renderNFTs(data.nfts, data.ada_price);

        // Mark NFTs as loaded and update portfolio total
        document.body.classList.remove('nft-loading');
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading NFTs:', error);
        setSafeHTML(nftsList, '<p class="empty-state">Error loading NFTs</p>');
        document.body.classList.remove('nft-loading');
        updateTotalPortfolioValue();
    }
}

// Toggle NFT collection expand/collapse
function toggleNftCollection(header) {
    const collection = header.closest('.nft-collection');
    if (collection) {
        collection.classList.toggle('collapsed');
    }
}

// Render NFTs list
function renderNFTs(nfts, adaPrice) {
    const nftsList = document.getElementById('nftsList');

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No NFTs found in your wallets.</p>');
        return;
    }

    // Group by collection - consolidate all collections WITHOUT floor prices into one "Unknown" group
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const policyId = nft.policy_id;
        const hasFloorPrice = nft.collection?.floor_price_ada && nft.collection.floor_price_ada > 0;

        // Only collections with floor prices are considered "known" - all others go to Unknown
        const isKnown = hasFloorPrice;

        // Use a single key for all unknown/unpriced collections
        const key = isKnown ? policyId : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? (nft.collection?.name || 'Unknown Collection') : 'Other NFTs (No Floor Price)',
                verified: isKnown ? (nft.collection?.verified || false) : false,
                found: isKnown,
                floor_price_ada: isKnown ? nft.collection?.floor_price_ada : null,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    // Sort collections by total value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        // Unknown collections always go to the end
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = a[1].nfts.reduce((sum, n) => sum + (n.price_usd || 0), 0);
        const valueB = b[1].nfts.reduce((sum, n) => sum + (n.price_usd || 0), 0);
        return valueB - valueA;
    });

    let html = '';

    for (const [key, collection] of sortedCollections) {
        const totalValue = collection.nfts.reduce((sum, n) => sum + (n.price_usd || 0), 0);
        const collectionClass = collection.found ? 'jpgstore' : 'unknown';
        const verifiedBadge = collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : '';

        // Collections are collapsed by default
        // NOTE: Do NOT use inline onclick - DOMPurify strips it out
        html += `
            <div class="nft-collection ${collectionClass} collapsed">
                <div class="nft-collection-header">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">${blurValue(collection.name)}${verifiedBadge}</span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${totalValue > 0 ? formatUSDBlur(totalValue) : '<span class="no-value">No value data</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const displayName = nft.asset_name || 'Unnamed NFT';
            const priceDisplay = nft.price_usd ? formatUSDBlur(nft.price_usd) : '';
            const priceSource = nft.price_source === 'listing' ? '(listed)' : nft.price_source === 'floor' ? '(floor)' : '';

            // Determine the best link
            let primaryLink = '';
            let linkIcon = '';
            if (nft.links?.jpgstore && collection.found) {
                primaryLink = nft.links.jpgstore;
                linkIcon = '<span class="nft-link-icon jpg">JPG</span>';
            } else {
                primaryLink = nft.links?.cexplorer || '';
                linkIcon = '<span class="nft-link-icon cex">CX</span>';
            }

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <span class="nft-name">${displayName}</span>
                        ${primaryLink ? `<a href="${primaryLink}" target="_blank" rel="noopener" class="nft-link" title="View NFT">${linkIcon}</a>` : ''}
                    </div>
                    <div class="nft-price">
                        ${priceDisplay ? `<span class="price-value">${priceDisplay}</span>` : ''}
                        ${priceSource ? `<span class="price-source">${priceSource}</span>` : ''}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);

    // Add click handlers after HTML is set (DOMPurify strips inline onclick)
    const headers = nftsList.querySelectorAll('.nft-collection-header');
    headers.forEach(header => {
        header.addEventListener('click', function() {
            toggleNftCollection(this);
        });
    });
}

// Sync wallet balances from blockchain
async function refreshBalances() {
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Syncing...';

    // Clear asset breakdown cache since we're syncing fresh data
    assetBreakdownCache.clear();
    console.log('Cleared asset breakdown cache');

    try {
        const response = await authFetch(`${API_BASE}/wallets/refresh`, {
            method: 'POST'
        });
        const data = await response.json();

        showStatus(data.message);
        await loadPrices();
        await loadPortfolioSummary();

        // Re-fetch asset breakdowns in background after sync
        preFetchAssetBreakdowns();
        // await loadNativeAssets(); // Now in Self-Custody Wallets
        await loadExchangeData();
        await loadDefiGovernance();
        // On overview page, loadDefiGovernance returns early (no UI element),
        // so refresh snapshot totals for staking/defi values
        if (!document.getElementById('defiGovernanceContent')) {
            await loadPortfolioTotals();
        }
        loadNFTs();

    } catch (error) {
        console.error('Error syncing wallets:', error);
        showStatus('Failed to sync wallets', true);
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = 'Sync Wallets';
    }
}

// Add new wallet
async function addWallet(event) {
    event.preventDefault();

    // Check if demo mode
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    const address = document.getElementById('walletAddress').value.trim();
    const label = document.getElementById('walletLabel').value.trim();

    if (!address) {
        showStatus('Please enter a wallet address', true);
        return;
    }

    try {
        const response = await authFetch(`${API_BASE}/wallets`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ address, label: label || null })
        });

        const data = await response.json();

        if (response.ok) {
            showStatus(`Added ${data.blockchain} wallet`);
            document.getElementById('walletAddress').value = '';
            document.getElementById('walletLabel').value = '';
            await loadPrices();
            await loadPortfolioSummary();
            // await loadNativeAssets(); // Now in Self-Custody Wallets
            await loadExchangeData();
            await loadDefiGovernance();
            loadNFTs();
        } else {
            showStatus(data.detail || 'Failed to add wallet', true);
        }

    } catch (error) {
        console.error('Error adding wallet:', error);
        showStatus('Failed to add wallet', true);
    }
}

// Edit wallet label
async function editWalletLabel(address, button) {
    const walletItem = button.closest('.wallet-item');
    const labelSpan = walletItem.querySelector('.wallet-label');
    const currentLabel = labelSpan.textContent;

    // Create input field
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentLabel;
    input.className = 'edit-label-input';
    input.maxLength = 50;

    // Replace span with input
    labelSpan.style.display = 'none';
    button.style.display = 'none';
    labelSpan.parentNode.insertBefore(input, labelSpan);
    input.focus();
    input.select();

    // Save on enter or blur
    const saveLabel = async () => {
        const newLabel = input.value.trim();
        if (newLabel && newLabel !== currentLabel) {
            try {
                const response = await authFetch(`${API_BASE}/wallets/${encodeURIComponent(address)}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: newLabel })
                });

                if (response.ok) {
                    labelSpan.textContent = newLabel;
                    showStatus('Wallet name updated');
                } else {
                    showStatus('Failed to update wallet name', true);
                }
            } catch (error) {
                console.error('Error updating wallet label:', error);
                showStatus('Failed to update wallet name', true);
            }
        }

        // Restore display
        input.remove();
        labelSpan.style.display = '';
        button.style.display = '';
    };

    input.addEventListener('blur', saveLabel);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            input.value = currentLabel;
            input.blur();
        }
    });
}

// Delete wallet
async function deleteWallet(address) {
    // Check if demo mode
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    // Confirm deletion
    const shortAddress = address.length > 14 ? address.slice(0, 8) + '...' + address.slice(-4) : address;
    if (!confirm(`Are you sure you want to delete this wallet?\n\n${shortAddress}\n\nThis will remove it from tracking and from wallets.txt.`)) {
        return;
    }

    try {
        showStatus('Deleting wallet...');

        const response = await authFetch(`${API_BASE}/wallets/${encodeURIComponent(address)}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            const data = await response.json();
            showStatus('Wallet deleted successfully');

            // Remove the wallet item from DOM
            const walletItem = document.querySelector(`.wallet-item[data-address="${address}"]`);
            if (walletItem) {
                // Check if this wallet is part of a group
                const walletGroup = walletItem.closest('.wallet-group');
                walletItem.remove();

                // If the group is now empty, remove it too
                if (walletGroup) {
                    const remainingWallets = walletGroup.querySelectorAll('.wallet-item');
                    if (remainingWallets.length === 0) {
                        walletGroup.remove();
                    }
                }
            }

            // Refresh portfolio summary to update totals
            await loadPortfolio();
        } else {
            const error = await response.json();
            showStatus(error.detail || 'Failed to delete wallet', true);
        }
    } catch (error) {
        console.error('Error deleting wallet:', error);
        showStatus('Failed to delete wallet', true);
    }
}

// Delete all wallets in a stake key group
async function deleteStakeGroup(stakeAddress) {
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    const group = document.querySelector(`.wallet-group[data-stake="${stakeAddress}"]`);
    const walletCount = group ? group.querySelectorAll('.wallet-item').length : 0;
    const shortStake = stakeAddress.length > 20 ? stakeAddress.slice(0, 12) + '...' + stakeAddress.slice(-8) : stakeAddress;

    if (!confirm(`Delete all ${walletCount} wallet(s) under this stake key?\n\n${shortStake}\n\nThis will remove them from tracking and from wallets.txt.`)) {
        return;
    }

    try {
        showStatus('Deleting stake group...');
        const response = await authFetch(`${API_BASE}/wallets/stake-group/${encodeURIComponent(stakeAddress)}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            const data = await response.json();
            showStatus(`Deleted ${data.deleted} wallet(s)`);
            if (group) group.remove();
            await loadPortfolio();
        } else {
            const error = await response.json();
            showStatus(error.detail || 'Failed to delete stake group', true);
        }
    } catch (error) {
        console.error('Error deleting stake group:', error);
        showStatus('Failed to delete stake group', true);
    }
}

// Edit stake group label (inline edit)
async function editStakeGroupLabel(stakeAddress, button) {
    const header = button.closest('.wallet-group-header');
    const labelSpan = header.querySelector('.group-label');
    // Extract just the label text (before the stake key short span)
    const stakeKeySpan = labelSpan.querySelector('.stake-key-short');
    const currentLabel = labelSpan.childNodes[0].textContent.replace(/:\s*$/, '').trim();

    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentLabel === 'Stake Key' ? '' : currentLabel;
    input.className = 'edit-label-input';
    input.maxLength = 50;
    input.placeholder = 'Enter group name...';

    labelSpan.style.display = 'none';
    button.style.display = 'none';
    labelSpan.parentNode.insertBefore(input, labelSpan);
    input.focus();
    input.select();

    const saveLabel = async () => {
        const newLabel = input.value.trim();
        if (newLabel && newLabel !== currentLabel) {
            try {
                const response = await authFetch(`${API_BASE}/wallets/stake-group/${encodeURIComponent(stakeAddress)}/label`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: newLabel })
                });

                if (response.ok) {
                    // Update the label text node (keep the stake key span)
                    labelSpan.childNodes[0].textContent = newLabel + ': ';
                    showStatus('Group name updated');
                } else {
                    showStatus('Failed to update group name', true);
                }
            } catch (error) {
                console.error('Error updating group label:', error);
                showStatus('Failed to update group name', true);
            }
        }

        input.remove();
        labelSpan.style.display = '';
        button.style.display = '';
    };

    input.addEventListener('blur', saveLabel);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            input.value = currentLabel;
            input.blur();
        }
    });
}

// Event Listeners
if (refreshBtn) {
    refreshBtn.addEventListener('click', refreshBalances);
}
if (addWalletForm) {
    addWalletForm.addEventListener('submit', addWallet);
}

// Section refresh functions
async function refreshWallets() {
    const btn = document.querySelector('.wallets-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    // Clear asset breakdown cache
    assetBreakdownCache.clear();

    try {
        // Force refresh the portfolio summary
        const response = await authFetch(`${API_BASE}/portfolio/summary?refresh=true`);
        const data = await response.json();

        walletTotals.ADA = data.cardano.total_ada;
        walletTotals.BTC = data.bitcoin.total_btc;
        walletTotals.ETH = data.ethereum?.total_eth || 0;
        walletTotals.SOL = data.solana?.total_sol || 0;
        walletTotals.MATIC = data.polygon?.total_matic || 0;
        walletTotals.ETH_BASE = data.base?.total_eth || 0;
        walletTotals.ALGO = data.algorand?.total_algo || 0;
        walletTotals.BNB = data.bsc?.total_bnb || 0;
        walletTotals.ETH_ARB = data.arbitrum?.total_eth || 0;
        walletTotals.AVAX = data.avalanche?.total_avax || 0;
        walletTotals.TRX = data.tron?.total_trx || 0;
        walletTotals.XRP = data.xrp?.total_xrp || 0;
        walletTotals.HBAR = data.hedera?.total_hbar || 0;
        walletTotals.EGLD = data.multiversx?.total_egld || 0;
        walletTotals.SUI = data.sui?.total_sui || 0;
        walletTotals.APT = data.aptos?.total_apt || 0;
        walletTotals.FIL = data.filecoin?.total_fil || 0;
        walletTotals.LTC = data.litecoin?.total_ltc || 0;
        walletTotals.DOGE = data.dogecoin?.total_doge || 0;
        walletTotals.ZEC = data.zcash?.total_zec || 0;
        walletTotals.XTZ = data.tezos?.total_xtz || 0;
        walletTotals.STX = data.stacks?.total_stx || 0;
        walletTotals.VET = data.vechain?.total_vet || 0;
        walletTotals.ATOM = data.cosmos?.total_atom || 0;
        walletTotals.NEAR = data.near?.total_near || 0;
        walletTotals.ICP = data.icp?.total_icp || 0;
        walletTotals.OSMO = data.osmosis?.total_osmo || 0;
        walletTotals.TIA = data.celestia?.total_tia || 0;
        walletTotals.INJ = data.injective?.total_inj || 0;
        walletTotals.DYDX = data.dydx?.total_dydx || 0;
        walletTotals.SEI = data.sei?.total_sei || 0;
        walletTotals.AKT = data.akash?.total_akt || 0;
        walletTotals.TON = data.ton?.total_ton || 0;
        walletTotals.DOT = data.polkadot?.total_dot || 0;
        walletTotals.KSM = data.kusama?.total_ksm || 0;
        walletTotals.XLM = data.stellar?.total_xlm || 0;
        walletTotals.KAS = data.kaspa?.total_kas || 0;
        walletTotals.KLAY = data.kaia?.total_klay || 0;
        walletTotals.ERG = data.ergo?.total_erg || 0;
        walletTotals.IOTA = data.iota?.total_iota || 0;
        walletTotals.WAVES = data.waves?.total_waves || 0;
        walletTotals.MINA = data.mina?.total_mina || 0;
        walletTotals.ZIL = data.zilliqa?.total_zil || 0;

        // Update summary cards (native coin + tokens)
        const adaUsd = data.cardano.total_ada * (prices.ADA || 0) + (data.cardano.native_assets_value_usd || 0);
        const btcUsd = data.bitcoin.total_btc * (prices.BTC || 0) + (data.bitcoin.native_assets_value_usd || 0);
        const ethUsd = (data.ethereum?.total_eth || 0) * (prices.ETH || 0) + (data.ethereum?.native_assets_value_usd || 0);

        adaBalance.textContent = `${data.cardano.total_ada.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 6})} ADA`;
        const adaBalanceUsd = document.getElementById('adaBalanceUsd');
        if (adaBalanceUsd) {
            adaBalanceUsd.textContent = formatUSD(adaUsd);
        }

        btcBalance.textContent = `${data.bitcoin.total_btc.toFixed(8)} BTC`;
        const btcBalanceUsd = document.getElementById('btcBalanceUsd');
        if (btcBalanceUsd) {
            btcBalanceUsd.textContent = formatUSD(btcUsd);
        }

        if (ethBalance) {
            ethBalance.textContent = `${(data.ethereum?.total_eth || 0).toFixed(8)} ETH`;
        }
        const ethBalanceUsdEl = document.getElementById('ethBalanceUsd');
        if (ethBalanceUsdEl) {
            ethBalanceUsdEl.textContent = formatUSD(ethUsd);
        }

        renderWalletsGrouped(data.cardano.stake_groups || [], data.bitcoin.wallets || [], data.ethereum?.wallets || [], data.solana?.wallets || [], data.polygon?.wallets || [], data.base?.wallets || [], data.algorand?.wallets || [], data.bsc?.wallets || [], data.arbitrum?.wallets || [], data.avalanche?.wallets || [], data.tron?.wallets || []);
        updateTotalPortfolioValue();
        showStatus('Wallets refreshed');
    } catch (error) {
        console.error('Error refreshing wallets:', error);
        showStatus('Failed to refresh wallets', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
    }
}

async function refreshExchanges() {
    const btn = document.querySelector('.exchanges-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    try {
        const response = await authFetch(`${API_BASE}/exchanges/all?refresh=true`);

        if (!response.ok) {
            throw new Error('Failed to fetch exchange data');
        }

        const data = await response.json();
        exchangeTotals.usd = data.total_usd || 0;

        // Extract staked assets for display in staking section
        extractExchangeStakedAssets(data.exchanges);

        const exchangesSummary = document.getElementById('exchangesSummary');
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, `
                <span class="exchange-count">${data.exchange_count || 0} exchange${data.exchange_count !== 1 ? 's' : ''} · ${data.total_assets || 0} assets</span>
                <span class="exchange-total">${formatUSD(data.total_usd || 0)}</span>
            `);
        }

        const exchangesList = document.getElementById('exchangesList');
        if (exchangesList) {
            renderAllExchanges(data.exchanges);
        }
        updateTotalPortfolioValue();
        showStatus('Exchange data refreshed');
    } catch (error) {
        console.error('Error refreshing exchanges:', error);
        showStatus('Failed to refresh exchange data', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
    }
}

async function refreshStaking() {
    const btn = document.querySelector('.staking-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    document.body.classList.add('staking-loading');
    updateTotalPortfolioValue();

    try {
        // Reload staking positions with refresh
        await loadStakingPositions();
        showStatus('Staking positions refreshed');
    } catch (error) {
        console.error('Error refreshing staking:', error);
        showStatus('Failed to refresh staking positions', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
    }
}

async function refreshDefi() {
    const btn = document.querySelector('.defi-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    document.body.classList.add('defi-loading');
    updateTotalPortfolioValue();

    try {
        const response = await authFetch(`${API_BASE}/defi/summary?refresh=true`);
        const data = await response.json();

        defiProtocolCount.textContent = `${data.protocols_used.length} protocol${data.protocols_used.length !== 1 ? 's' : ''}`;
        defiWalletCount.textContent = `${data.wallets_with_defi} wallet${data.wallets_with_defi !== 1 ? 's' : ''} with DeFi`;

        // Update DeFi totals
        defiTotals = {};
        if (data.positions_by_category) {
            for (const [category, positions] of Object.entries(data.positions_by_category)) {
                for (const pos of positions) {
                    // Use token (standard symbol from DEFI_PROTOCOLS) for price lookup
                    const token = pos.token || pos.asset_name || pos.symbol;
                    if (token && pos.quantity) {
                        if (!defiTotals[token]) {
                            defiTotals[token] = 0;
                        }
                        defiTotals[token] += pos.quantity;
                    }
                }
            }
        }

        renderDefiPositions(data);
        showStatus('DeFi positions refreshed');
    } catch (error) {
        console.error('Error refreshing DeFi:', error);
        showStatus('Failed to refresh DeFi positions', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();
    }
}

// Native assets section removed - now shown in Self-Custody Wallets
// async function refreshAssets() {
//     const btn = document.querySelector('.native-tokens-section .section-refresh-btn');
//     if (btn) {
//         btn.classList.add('refreshing');
//     }

//     try {
//         // Force refresh to get fresh data from blockchain
//         await loadNativeAssets(true);
//         showStatus('Native assets refreshed');
//     } catch (error) {
//         console.error('Error refreshing assets:', error);
//         showStatus('Failed to refresh assets', true);
//     } finally {
//         if (btn) {
//             btn.classList.remove('refreshing');
//         }
//     }
// }

async function refreshNFTs() {
    const btn = document.querySelector('.nfts-section .section-refresh-btn');
    if (btn) {
        btn.classList.add('refreshing');
    }

    // Mark NFTs as loading
    document.body.classList.add('nft-loading');
    updateTotalPortfolioValue();

    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Refreshing NFTs... (this may take a moment)</p>');
    }

    try {
        if (currentNFTChain === 'cardano') {
            // Force refresh Cardano NFTs
            const response = await authFetch(`${API_BASE}/nfts?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch NFTs');
            }

            const data = await response.json();

            // Update Cardano NFT totals and counts
            nftTotals.cardano = data.total_value_usd || 0;
            nftCounts.cardano = data.total_count || 0;

            // Update Cardano chain tab stats
            const cardanoStats = document.getElementById('cardanoNftStats');
            if (cardanoStats) {
                setSafeHTML(cardanoStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderNFTs(data.nfts, data.ada_price);
        } else if (currentNFTChain === 'ethereum') {
            // Force refresh Ethereum NFTs
            const response = await authFetch(`${API_BASE}/nfts/ethereum?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Ethereum NFTs');
            }

            const data = await response.json();

            // Update Ethereum NFT totals and counts
            nftTotals.ethereum = data.total_value_usd || 0;
            nftCounts.ethereum = data.total_count || 0;

            // Update Ethereum chain tab stats
            const ethereumStats = document.getElementById('ethereumNftStats');
            if (ethereumStats) {
                setSafeHTML(ethereumStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderEthereumNFTs(data.nfts, data.eth_price);
        } else if (currentNFTChain === 'solana') {
            // Force refresh Solana NFTs
            const response = await authFetch(`${API_BASE}/nfts/solana?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Solana NFTs');
            }

            const data = await response.json();

            // Update Solana NFT totals and counts
            nftTotals.solana = data.total_value_usd || 0;
            nftCounts.solana = data.total_count || 0;

            // Update Solana chain tab stats
            const solanaStats = document.getElementById('solanaNftStats');
            if (solanaStats) {
                setSafeHTML(solanaStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderSolanaNFTs(data.nfts, data.sol_price);
        } else if (currentNFTChain === 'polygon') {
            // Force refresh Polygon NFTs
            const response = await authFetch(`${API_BASE}/nfts/polygon?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Polygon NFTs');
            }

            const data = await response.json();

            // Update Polygon NFT totals and counts
            nftTotals.polygon = data.total_value_usd || 0;
            nftCounts.polygon = data.total_count || 0;

            // Update Polygon chain tab stats
            const polygonStats = document.getElementById('polygonNftStats');
            if (polygonStats) {
                setSafeHTML(polygonStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderPolygonNFTs(data.nfts, data.matic_price);
        } else if (currentNFTChain === 'base') {
            // Force refresh Base NFTs
            const response = await authFetch(`${API_BASE}/nfts/base?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Base NFTs');
            }

            const data = await response.json();

            // Update Base NFT totals and counts
            nftTotals.base = data.total_value_usd || 0;
            nftCounts.base = data.total_count || 0;

            // Update Base chain tab stats
            const baseStats = document.getElementById('baseNftStats');
            if (baseStats) {
                setSafeHTML(baseStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderBaseNFTs(data.nfts, data.eth_price);
        } else if (currentNFTChain === 'algorand') {
            // Force refresh Algorand NFTs
            const response = await authFetch(`${API_BASE}/nfts/algorand?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Algorand NFTs');
            }

            const data = await response.json();

            // Update Algorand NFT totals and counts
            nftTotals.algorand = data.total_value_usd || 0;
            nftCounts.algorand = data.total_count || 0;

            // Update Algorand chain tab stats
            const algorandStats = document.getElementById('algorandNftStats');
            if (algorandStats) {
                setSafeHTML(algorandStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderAlgorandNFTs(data.nfts);
        } else if (currentNFTChain === 'bsc') {
            // Force refresh BSC NFTs
            const response = await authFetch(`${API_BASE}/nfts/bsc?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch BSC NFTs');
            }

            const data = await response.json();

            // Update BSC NFT totals and counts
            nftTotals.bsc = data.total_value_usd || 0;
            nftCounts.bsc = data.total_count || 0;

            // Update BSC chain tab stats
            const bscStats = document.getElementById('bscNftStats');
            if (bscStats) {
                setSafeHTML(bscStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderBscNFTs(data.nfts, data.bnb_price);
        } else if (currentNFTChain === 'arbitrum') {
            // Force refresh Arbitrum NFTs
            const response = await authFetch(`${API_BASE}/nfts/arbitrum?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Arbitrum NFTs');
            }

            const data = await response.json();

            // Update Arbitrum NFT totals and counts
            nftTotals.arbitrum = data.total_value_usd || 0;
            nftCounts.arbitrum = data.total_count || 0;

            // Update Arbitrum chain tab stats
            const arbitrumStats = document.getElementById('arbitrumNftStats');
            if (arbitrumStats) {
                setSafeHTML(arbitrumStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderArbitrumNFTs(data.nfts, data.eth_price);
        } else if (currentNFTChain === 'avalanche') {
            // Force refresh Avalanche NFTs
            const response = await authFetch(`${API_BASE}/nfts/avalanche?force_refresh=true`);

            if (!response.ok) {
                throw new Error('Failed to fetch Avalanche NFTs');
            }

            const data = await response.json();

            // Update Avalanche NFT totals and counts
            nftTotals.avalanche = data.total_value_usd || 0;
            nftCounts.avalanche = data.total_count || 0;

            // Update Avalanche chain tab stats
            const avalancheStats = document.getElementById('avalancheNftStats');
            if (avalancheStats) {
                setSafeHTML(avalancheStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
            }

            // Update section summary with combined totals
            updateNftSectionSummary();
            updateSummaryCardNftCounts();

            renderAvalancheNFTs(data.nfts, data.avax_price);
        }
        showStatus('NFTs refreshed');
    } catch (error) {
        console.error('Error refreshing NFTs:', error);
        showStatus('Failed to refresh NFTs', true);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error refreshing NFTs</p>');
        }
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
        }
        document.body.classList.remove('nft-loading');
        updateTotalPortfolioValue();
    }
}

// Switch NFT chain tab
async function switchNFTChain(chain) {
    currentNFTChain = chain;

    // Update tab appearance
    document.querySelectorAll('.nft-chain-tabs .chain-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.chain === chain);
    });

    // Load NFTs for the selected chain (summaries already loaded at startup)
    if (chain === 'cardano') {
        loadNFTs();
    } else if (chain === 'ethereum') {
        loadEthereumNFTs();
    } else if (chain === 'solana') {
        loadSolanaNFTs();
    } else if (chain === 'polygon') {
        loadPolygonNFTs();
    } else if (chain === 'base') {
        loadBaseNFTs();
    } else if (chain === 'algorand') {
        loadAlgorandNFTs();
    } else if (chain === 'bsc') {
        loadBscNFTs();
    } else if (chain === 'arbitrum') {
        loadArbitrumNFTs();
    } else if (chain === 'avalanche') {
        loadAvalancheNFTs();
    }
}

// Load Ethereum NFTs
async function loadEthereumNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Ethereum NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/ethereum`);

        if (!response.ok) {
            throw new Error('Failed to fetch Ethereum NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Ethereum NFT support.</p>');
            }
            // Update Ethereum stats to show not configured
            const ethereumStats = document.getElementById('ethereumNftStats');
            if (ethereumStats) {
                ethereumStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Ethereum NFT total and count for portfolio calculation
        nftTotals.ethereum = data.total_value_usd || 0;
        nftCounts.ethereum = data.total_count || 0;

        // Update Ethereum chain tab stats
        const ethereumStats = document.getElementById('ethereumNftStats');
        if (ethereumStats) {
            setSafeHTML(ethereumStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary with combined totals
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderEthereumNFTs(data.nfts, data.eth_price);

    } catch (error) {
        console.error('Error loading Ethereum NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Ethereum NFTs</p>');
        }
    }
}

// Render Ethereum NFTs
function renderEthereumNFTs(nfts, ethPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Ethereum NFTs found</p>');
        return;
    }

    // Group NFTs by collection - consolidate all collections WITHOUT floor prices into one "Unknown" group
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_eth && nft.collection.floor_price_eth > 0;

        // Only collections with floor prices are considered "known"
        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_eth: isKnown ? (nft.collection?.floor_price_eth || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        // Unknown collections always go to the end
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_eth || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_eth || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueEth = (collection.floor_price_eth || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueEth * (ethPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection ethereum collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_eth || 0) * (ethPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Update NFT section summary with combined totals from all chains
function updateNftSectionSummary() {
    const nftsSummary = document.getElementById('nftsSummary');
    if (!nftsSummary) return;

    // Calculate combined totals
    const totalValue = getNftTotalUsd();

    // Sum counts from all chains
    const totalCount = (nftCounts.cardano || 0) + (nftCounts.ethereum || 0) + (nftCounts.solana || 0) + (nftCounts.polygon || 0) + (nftCounts.base || 0) + (nftCounts.algorand || 0) + (nftCounts.bsc || 0) + (nftCounts.arbitrum || 0) + (nftCounts.avalanche || 0);

    setSafeHTML(nftsSummary, `
        <span class="nft-count">${totalCount} NFT${totalCount !== 1 ? 's' : ''}</span>
        <span class="nft-value">${formatUSDBlur(totalValue)}</span>
    `);
}

// ============================================================================
// NFT IMAGE CACHE FUNCTIONS
// ============================================================================

// Initialize the image cache toggle from server state
async function initImageCacheToggle() {
    // Only fetch config if the toggle exists on this page (NFTs page)
    const toggle = document.getElementById('imageCacheToggle');
    if (!toggle) return;

    try {
        const response = await authFetch(`${API_BASE}/nfts/images/config`);
        const config = await response.json();

        imageCacheEnabled = config.enabled || false;
        toggle.checked = imageCacheEnabled;
    } catch (error) {
        console.error('Error initializing image cache toggle:', error);
    }
}

// Toggle image caching on/off
async function toggleImageCache(enabled) {
    try {
        const endpoint = enabled ? '/nfts/images/enable' : '/nfts/images/disable';
        const response = await authFetch(`${API_BASE}${endpoint}`, { method: 'POST' });
        const data = await response.json();

        imageCacheEnabled = data.enabled;
        showStatus(`NFT image caching ${imageCacheEnabled ? 'enabled' : 'disabled'}`);

        // Update toggle state in case server returned different value
        const toggle = document.getElementById('imageCacheToggle');
        if (toggle) {
            toggle.checked = imageCacheEnabled;
        }
    } catch (error) {
        console.error('Error toggling image cache:', error);
        showStatus('Failed to toggle image cache', true);

        // Revert the checkbox on error
        const toggle = document.getElementById('imageCacheToggle');
        if (toggle) {
            toggle.checked = !enabled;
        }
    }
}

// Get the URL for an NFT image (cached or original)
function getNftImageUrl(nft, chain) {
    if (!nft) return '/static/img/nft-placeholder.png';

    // If caching is enabled and we might have a cached image, use the API
    if (imageCacheEnabled) {
        const assetId = nft.asset_id || nft.token_id || nft.unit;
        if (assetId) {
            return `${API_BASE}/nfts/images/${chain}/${encodeURIComponent(assetId)}/thumbnail`;
        }
    }

    // Fallback to original URL
    return nft.image_url || nft.image || '/static/img/nft-placeholder.png';
}

// Sync Cardano NFT floor prices using all available sources
async function syncNFTPrices() {
    // Check if demo mode
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    const btn = document.querySelector('.btn-sync-prices');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Syncing...';
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/prices/sync`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            // Build a user-friendly message
            let msg = `Synced ${data.synced}/${data.total_collections} collections`;
            if (data.failed > 0 && data.rate_limited) {
                msg += ` \u00b7 ${data.failed} unavailable (rate limit)`;
            } else if (data.failed > 0) {
                msg += ` \u00b7 ${data.failed} unavailable`;
            }
            showStatus(msg);

            // Reload NFTs with force refresh to pick up new prices
            if (currentNFTChain === 'cardano') {
                loadNFTs(true);
            }
            loadNFTPriceCoverage();
        } else if (!data.has_sources) {
            showStatus('No pricing sources available \u2014 configure TapTools API key in Settings', true);
        } else {
            showStatus(data.message || 'Failed to sync prices', true);
        }
    } catch (error) {
        console.error('Error syncing NFT prices:', error);
        showStatus('Failed to sync NFT prices', true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Sync Prices';
        }
    }
}

// Load NFT pricing coverage stats
async function loadNFTPriceCoverage() {
    const coverageEl = document.getElementById('priceCoverage');
    if (!coverageEl) return;

    try {
        const response = await authFetch(`${API_BASE}/nfts/prices/coverage`);
        if (!response.ok) return;

        const data = await response.json();
        if (data.total_nfts === 0) {
            coverageEl.textContent = '';
            return;
        }

        if (data.priced_nfts === data.total_nfts) {
            coverageEl.textContent = `All ${data.total_nfts} NFTs priced`;
        } else {
            coverageEl.textContent = `${data.priced_nfts}/${data.total_nfts} priced`;
        }
        coverageEl.title = `${data.priced_collections}/${data.total_collections} collections have floor prices`;
    } catch (error) {
        console.error('Error loading NFT price coverage:', error);
    }
}

// Load Solana NFTs
async function loadSolanaNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Solana NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/solana`);

        if (!response.ok) {
            throw new Error('Failed to fetch Solana NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Helius API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Solana NFT support.</p>');
            }
            const solanaStats = document.getElementById('solanaNftStats');
            if (solanaStats) {
                solanaStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Solana NFT total and count for portfolio calculation
        nftTotals.solana = data.total_value_usd || 0;
        nftCounts.solana = data.total_count || 0;

        // Update Solana chain tab stats
        const solanaStats = document.getElementById('solanaNftStats');
        if (solanaStats) {
            setSafeHTML(solanaStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderSolanaNFTs(data.nfts, data.sol_price);

    } catch (error) {
        console.error('Error loading Solana NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Solana NFTs</p>');
        }
    }
}

// Render Solana NFTs
function renderSolanaNFTs(nfts, solPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Solana NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || 'Unknown Collection';

        if (!collections[collectionName]) {
            collections[collectionName] = {
                name: collectionName,
                floor_price_sol: nft.collection?.floor_price_sol || 0,
                nfts: []
            };
        }
        collections[collectionName].nfts.push(nft);
    }

    let html = '';

    // Sort collections by count (since floor prices may not be available)
    const sortedCollections = Object.values(collections).sort((a, b) => b.nfts.length - a.nfts.length);

    for (const collection of sortedCollections) {
        const collectionValueSol = (collection.floor_price_sol || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueSol * (solPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection solana collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">${blurValue(collection.name)}</span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const isCompressed = nft.is_compressed ? '<span class="compressed-badge" title="Compressed NFT">cNFT</span>' : '';

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.magiceden || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Magic Eden">
                            <span class="nft-link-icon magiceden">ME</span>
                        </a>
                        <a href="${nft.links?.solscan || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Solscan">
                            <span class="nft-link-icon solscan">SS</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'} ${isCompressed}</span>
                    </div>
                    <div class="nft-price">
                        <span class="price-value no-price">--</span>
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load Polygon NFTs
async function loadPolygonNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Polygon NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/polygon`);

        if (!response.ok) {
            throw new Error('Failed to fetch Polygon NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Polygon NFT support.</p>');
            }
            const polygonStats = document.getElementById('polygonNftStats');
            if (polygonStats) {
                polygonStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Polygon NFT total and count for portfolio calculation
        nftTotals.polygon = data.total_value_usd || 0;
        nftCounts.polygon = data.total_count || 0;

        // Update Polygon chain tab stats
        const polygonStats = document.getElementById('polygonNftStats');
        if (polygonStats) {
            setSafeHTML(polygonStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderPolygonNFTs(data.nfts, data.matic_price);

    } catch (error) {
        console.error('Error loading Polygon NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Polygon NFTs</p>');
        }
    }
}

// Render Polygon NFTs
function renderPolygonNFTs(nfts, maticPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Polygon NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_matic && nft.collection.floor_price_matic > 0;

        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_matic: isKnown ? (nft.collection?.floor_price_matic || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_matic || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_matic || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueMatic = (collection.floor_price_matic || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueMatic * (maticPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection polygon collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_matic || 0) * (maticPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <a href="${nft.links?.polygonscan || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Polygonscan">
                            <span class="nft-link-icon polygonscan">PS</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load Base NFTs
async function loadBaseNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Base NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/base`);

        if (!response.ok) {
            throw new Error('Failed to fetch Base NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Base NFT support.</p>');
            }
            const baseStats = document.getElementById('baseNftStats');
            if (baseStats) {
                baseStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Base NFT total and count for portfolio calculation
        nftTotals.base = data.total_value_usd || 0;
        nftCounts.base = data.total_count || 0;

        // Update Base chain tab stats
        const baseStats = document.getElementById('baseNftStats');
        if (baseStats) {
            setSafeHTML(baseStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderBaseNFTs(data.nfts, data.eth_price);

    } catch (error) {
        console.error('Error loading Base NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Base NFTs</p>');
        }
    }
}

// Render Base NFTs
function renderBaseNFTs(nfts, ethPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Base NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_eth && nft.collection.floor_price_eth > 0;

        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_eth: isKnown ? (nft.collection?.floor_price_eth || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_eth || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_eth || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueEth = (collection.floor_price_eth || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueEth * (ethPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection base collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_eth || 0) * (ethPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <a href="${nft.links?.basescan || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Basescan">
                            <span class="nft-link-icon basescan">BS</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load Algorand NFTs
async function loadAlgorandNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Algorand NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/algorand`);

        if (!response.ok) {
            throw new Error('Failed to fetch Algorand NFTs');
        }

        const data = await response.json();

        // Store Algorand NFT total and count for portfolio calculation
        nftTotals.algorand = data.total_value_usd || 0;
        nftCounts.algorand = data.total_count || 0;

        // Update Algorand chain tab stats
        const algorandStats = document.getElementById('algorandNftStats');
        if (algorandStats) {
            setSafeHTML(algorandStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderAlgorandNFTs(data.nfts);

    } catch (error) {
        console.error('Error loading Algorand NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Algorand NFTs</p>');
        }
    }
}

// Render Algorand NFTs
function renderAlgorandNFTs(nfts) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Algorand NFTs found</p>');
        return;
    }

    // Group NFTs by collection (unit_name)
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const key = collectionName || UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: collectionName || 'Other NFTs',
                isUnknown: !collectionName,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by count, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;
        return b[1].nfts.length - a[1].nfts.length;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        html += `
            <div class="nft-collection algorand collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        <span class="no-value">No pricing</span>
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        ${nft.image_url ? `<img src="${nft.image_url}" class="nft-thumbnail" alt="${nft.name}" onerror="this.style.display='none'">` : ''}
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                        <span class="nft-id">#${nft.asset_id}</span>
                    </div>
                    <div class="nft-price">
                        <span class="price-value no-price">--</span>
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load BSC NFTs
async function loadBscNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading BSC NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/bsc`);

        if (!response.ok) {
            throw new Error('Failed to fetch BSC NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable BSC NFT support.</p>');
            }
            const bscStats = document.getElementById('bscNftStats');
            if (bscStats) {
                bscStats.textContent = 'Not configured';
            }
            return;
        }

        // Store BSC NFT total and count for portfolio calculation
        nftTotals.bsc = data.total_value_usd || 0;
        nftCounts.bsc = data.total_count || 0;

        // Update BSC chain tab stats
        const bscStats = document.getElementById('bscNftStats');
        if (bscStats) {
            setSafeHTML(bscStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderBscNFTs(data.nfts, data.bnb_price);

    } catch (error) {
        console.error('Error loading BSC NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading BSC NFTs</p>');
        }
    }
}

// Render BSC NFTs
function renderBscNFTs(nfts, bnbPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No BSC NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_bnb && nft.collection.floor_price_bnb > 0;

        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_bnb: isKnown ? (nft.collection?.floor_price_bnb || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_bnb || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_bnb || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueBnb = (collection.floor_price_bnb || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueBnb * (bnbPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection bsc collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_bnb || 0) * (bnbPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <a href="${nft.links?.bscscan || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on BscScan">
                            <span class="nft-link-icon bscscan">BC</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load Arbitrum NFTs
async function loadArbitrumNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Arbitrum NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/arbitrum`);

        if (!response.ok) {
            throw new Error('Failed to fetch Arbitrum NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Arbitrum NFT support.</p>');
            }
            const arbitrumStats = document.getElementById('arbitrumNftStats');
            if (arbitrumStats) {
                arbitrumStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Arbitrum NFT total and count for portfolio calculation
        nftTotals.arbitrum = data.total_value_usd || 0;
        nftCounts.arbitrum = data.total_count || 0;

        // Update Arbitrum chain tab stats
        const arbitrumStats = document.getElementById('arbitrumNftStats');
        if (arbitrumStats) {
            setSafeHTML(arbitrumStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderArbitrumNFTs(data.nfts, data.eth_price);

    } catch (error) {
        console.error('Error loading Arbitrum NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Arbitrum NFTs</p>');
        }
    }
}

// Render Arbitrum NFTs
function renderArbitrumNFTs(nfts, ethPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Arbitrum NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_eth && nft.collection.floor_price_eth > 0;

        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_eth: isKnown ? (nft.collection?.floor_price_eth || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_eth || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_eth || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueEth = (collection.floor_price_eth || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueEth * (ethPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection arbitrum collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_eth || 0) * (ethPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <a href="${nft.links?.arbiscan || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Arbiscan">
                            <span class="nft-link-icon arbiscan">AS</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load Avalanche NFTs
async function loadAvalancheNFTs() {
    const nftsList = document.getElementById('nftsList');
    if (nftsList) {
        setSafeHTML(nftsList, '<p class="loading-state">Loading Avalanche NFTs...</p>');
    }

    try {
        const response = await authFetch(`${API_BASE}/nfts/avalanche`);

        if (!response.ok) {
            throw new Error('Failed to fetch Avalanche NFTs');
        }

        const data = await response.json();

        if (!data.configured) {
            if (nftsList) {
                setSafeHTML(nftsList, '<p class="empty-state">Alchemy API not configured. <a href="/apis.html" style="color: #667eea;">Configure it in Manage APIs</a> to enable Avalanche NFT support.</p>');
            }
            const avalancheStats = document.getElementById('avalancheNftStats');
            if (avalancheStats) {
                avalancheStats.textContent = 'Not configured';
            }
            return;
        }

        // Store Avalanche NFT total and count for portfolio calculation
        nftTotals.avalanche = data.total_value_usd || 0;
        nftCounts.avalanche = data.total_count || 0;

        // Update Avalanche chain tab stats
        const avalancheStats = document.getElementById('avalancheNftStats');
        if (avalancheStats) {
            setSafeHTML(avalancheStats, `${data.total_count} · ${formatUSDBlur(data.total_value_usd)}`);
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

        renderAvalancheNFTs(data.nfts, data.avax_price);

    } catch (error) {
        console.error('Error loading Avalanche NFTs:', error);
        if (nftsList) {
            setSafeHTML(nftsList, '<p class="empty-state">Error loading Avalanche NFTs</p>');
        }
    }
}

// Render Avalanche NFTs
function renderAvalancheNFTs(nfts, avaxPrice) {
    const nftsList = document.getElementById('nftsList');
    if (!nftsList) return;

    if (!nfts || nfts.length === 0) {
        setSafeHTML(nftsList, '<p class="empty-state">No Avalanche NFTs found</p>');
        return;
    }

    // Group NFTs by collection
    const collections = {};
    const UNKNOWN_KEY = '__unknown__';

    for (const nft of nfts) {
        const collectionName = nft.collection?.name || '';
        const hasFloorPrice = nft.collection?.floor_price_avax && nft.collection.floor_price_avax > 0;

        const isKnown = hasFloorPrice;
        const key = isKnown ? collectionName : UNKNOWN_KEY;

        if (!collections[key]) {
            collections[key] = {
                name: isKnown ? collectionName : 'Other NFTs (No Floor Price)',
                floor_price_avax: isKnown ? (nft.collection?.floor_price_avax || 0) : 0,
                verified: isKnown ? (nft.collection?.verified || false) : false,
                isUnknown: !isKnown,
                nfts: []
            };
        }
        collections[key].nfts.push(nft);
    }

    let html = '';

    // Sort collections by value, with unknown at the end
    const sortedCollections = Object.entries(collections).sort((a, b) => {
        if (a[0] === UNKNOWN_KEY) return 1;
        if (b[0] === UNKNOWN_KEY) return -1;

        const valueA = (a[1].floor_price_avax || 0) * a[1].nfts.length;
        const valueB = (b[1].floor_price_avax || 0) * b[1].nfts.length;
        return valueB - valueA;
    }).map(([_, v]) => v);

    for (const collection of sortedCollections) {
        const collectionValueAvax = (collection.floor_price_avax || 0) * collection.nfts.length;
        const collectionValueUsd = collectionValueAvax * (avaxPrice || 0);

        // Collections are collapsed by default
        html += `
            <div class="nft-collection avalanche collapsed">
                <div class="nft-collection-header" onclick="toggleNftCollection(this)">
                    <span class="collapse-indicator">▶</span>
                    <div class="collection-info">
                        <span class="collection-name">
                            ${blurValue(collection.name)}
                            ${collection.verified ? '<span class="verified-badge" title="Verified Collection">✓</span>' : ''}
                        </span>
                        <span class="collection-count">${collection.nfts.length} NFT${collection.nfts.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="collection-value">
                        ${collectionValueUsd > 0 ? formatUSDBlur(collectionValueUsd) : '<span class="no-value">No floor price</span>'}
                    </div>
                </div>
                <div class="nft-items">
        `;

        for (const nft of collection.nfts) {
            const floorPriceUsd = (nft.collection?.floor_price_avax || 0) * (avaxPrice || 0);

            html += `
                <div class="nft-item">
                    <div class="nft-info">
                        <a href="${nft.links?.opensea || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on OpenSea">
                            <span class="nft-link-icon opensea">OS</span>
                        </a>
                        <a href="${nft.links?.snowtrace || '#'}" target="_blank" rel="noopener" class="nft-link" title="View on Snowtrace">
                            <span class="nft-link-icon snowtrace">ST</span>
                        </a>
                        <span class="nft-name">${nft.name || 'Unnamed NFT'}</span>
                    </div>
                    <div class="nft-price">
                        ${floorPriceUsd > 0 ? `
                            <span class="price-value">${formatUSDBlur(floorPriceUsd)}</span>
                            <span class="price-source">(floor)</span>
                        ` : '<span class="price-value no-price">--</span>'}
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    setSafeHTML(nftsList, html);
}

// Load NFT summaries for all chains (for combined totals on page load)
async function loadAllNftSummaries() {
    try {
        const response = await authFetch(`${API_BASE}/nfts/all/summary`);
        if (!response.ok) return;

        const data = await response.json();

        // Update totals and counts from combined summary
        if (data.chains) {
            if (data.chains.cardano) {
                nftTotals.cardano = data.chains.cardano.total_value_usd || 0;
                nftCounts.cardano = data.chains.cardano.total_count || 0;
                const cardanoStats = document.getElementById('cardanoNftStats');
                if (cardanoStats) {
                    setSafeHTML(cardanoStats, `${data.chains.cardano.total_count || 0} · ${formatUSDBlur(data.chains.cardano.total_value_usd || 0)}`);
                }
            }
            if (data.chains.ethereum && data.chains.ethereum.configured) {
                nftTotals.ethereum = data.chains.ethereum.total_value_usd || 0;
                nftCounts.ethereum = data.chains.ethereum.total_count || 0;
                const ethereumStats = document.getElementById('ethereumNftStats');
                if (ethereumStats) {
                    setSafeHTML(ethereumStats, `${data.chains.ethereum.total_count || 0} · ${formatUSDBlur(data.chains.ethereum.total_value_usd || 0)}`);
                }
            } else {
                // Explicitly set to 0 for unconfigured chains
                nftTotals.ethereum = 0;
                nftCounts.ethereum = 0;
                const ethereumStats = document.getElementById('ethereumNftStats');
                if (ethereumStats) {
                    ethereumStats.textContent = 'Not configured';
                }
            }
            if (data.chains.solana && data.chains.solana.configured) {
                nftTotals.solana = data.chains.solana.total_value_usd || 0;
                nftCounts.solana = data.chains.solana.total_count || 0;
                const solanaStats = document.getElementById('solanaNftStats');
                if (solanaStats) {
                    setSafeHTML(solanaStats, `${data.chains.solana.total_count || 0} · ${formatUSDBlur(data.chains.solana.total_value_usd || 0)}`);
                }
            } else {
                // Explicitly set to 0 for unconfigured chains
                nftTotals.solana = 0;
                nftCounts.solana = 0;
                const solanaStats = document.getElementById('solanaNftStats');
                if (solanaStats) {
                    solanaStats.textContent = 'Not configured';
                }
            }
            if (data.chains.polygon && data.chains.polygon.configured) {
                nftTotals.polygon = data.chains.polygon.total_value_usd || 0;
                nftCounts.polygon = data.chains.polygon.total_count || 0;
                const polygonStats = document.getElementById('polygonNftStats');
                if (polygonStats) {
                    setSafeHTML(polygonStats, `${data.chains.polygon.total_count || 0} · ${formatUSDBlur(data.chains.polygon.total_value_usd || 0)}`);
                }
            } else {
                // Explicitly set to 0 for unconfigured chains
                nftTotals.polygon = 0;
                nftCounts.polygon = 0;
                const polygonStats = document.getElementById('polygonNftStats');
                if (polygonStats) {
                    polygonStats.textContent = 'Not configured';
                }
            }
            if (data.chains.base && data.chains.base.configured) {
                nftTotals.base = data.chains.base.total_value_usd || 0;
                nftCounts.base = data.chains.base.total_count || 0;
                const baseStats = document.getElementById('baseNftStats');
                if (baseStats) {
                    setSafeHTML(baseStats, `${data.chains.base.total_count || 0} · ${formatUSDBlur(data.chains.base.total_value_usd || 0)}`);
                }
            } else {
                // Explicitly set to 0 for unconfigured chains
                nftTotals.base = 0;
                nftCounts.base = 0;
                const baseStats = document.getElementById('baseNftStats');
                if (baseStats) {
                    baseStats.textContent = 'Not configured';
                }
            }
            if (data.chains.algorand) {
                nftTotals.algorand = data.chains.algorand.total_value_usd || 0;
                nftCounts.algorand = data.chains.algorand.total_count || 0;
                const algorandStats = document.getElementById('algorandNftStats');
                if (algorandStats) {
                    setSafeHTML(algorandStats, `${data.chains.algorand.total_count || 0} · ${formatUSDBlur(data.chains.algorand.total_value_usd || 0)}`);
                }
            }
            if (data.chains.bsc && data.chains.bsc.configured) {
                nftTotals.bsc = data.chains.bsc.total_value_usd || 0;
                nftCounts.bsc = data.chains.bsc.total_count || 0;
                const bscStats = document.getElementById('bscNftStats');
                if (bscStats) {
                    setSafeHTML(bscStats, `${data.chains.bsc.total_count || 0} · ${formatUSDBlur(data.chains.bsc.total_value_usd || 0)}`);
                }
            } else {
                nftTotals.bsc = 0;
                nftCounts.bsc = 0;
                const bscStats = document.getElementById('bscNftStats');
                if (bscStats) {
                    bscStats.textContent = 'Not configured';
                }
            }
            if (data.chains.arbitrum && data.chains.arbitrum.configured) {
                nftTotals.arbitrum = data.chains.arbitrum.total_value_usd || 0;
                nftCounts.arbitrum = data.chains.arbitrum.total_count || 0;
                const arbitrumStats = document.getElementById('arbitrumNftStats');
                if (arbitrumStats) {
                    setSafeHTML(arbitrumStats, `${data.chains.arbitrum.total_count || 0} · ${formatUSDBlur(data.chains.arbitrum.total_value_usd || 0)}`);
                }
            } else {
                nftTotals.arbitrum = 0;
                nftCounts.arbitrum = 0;
                const arbitrumStats = document.getElementById('arbitrumNftStats');
                if (arbitrumStats) {
                    arbitrumStats.textContent = 'Not configured';
                }
            }
            if (data.chains.avalanche && data.chains.avalanche.configured) {
                nftTotals.avalanche = data.chains.avalanche.total_value_usd || 0;
                nftCounts.avalanche = data.chains.avalanche.total_count || 0;
                const avalancheStats = document.getElementById('avalancheNftStats');
                if (avalancheStats) {
                    setSafeHTML(avalancheStats, `${data.chains.avalanche.total_count || 0} · ${formatUSDBlur(data.chains.avalanche.total_value_usd || 0)}`);
                }
            } else {
                nftTotals.avalanche = 0;
                nftCounts.avalanche = 0;
                const avalancheStats = document.getElementById('avalancheNftStats');
                if (avalancheStats) {
                    avalancheStats.textContent = 'Not configured';
                }
            }
        }

        // Update section summary and summary card counts
        updateNftSectionSummary();
        updateSummaryCardNftCounts();
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading NFT summaries:', error);
    }
}

// Global refresh all data with force refresh
async function globalRefreshAll() {
    const btn = document.getElementById('globalRefreshBtn');
    if (btn) {
        btn.classList.add('refreshing');
        btn.disabled = true;
    }

    showStatus('Refreshing all data...');

    try {
        // Refresh prices first
        await loadPrices();

        // Refresh all sections with force refresh parameter
        const refreshPromises = [
            authFetch(`${API_BASE}/portfolio/summary?refresh=true`).then(r => r.json()),
            authFetch(`${API_BASE}/defi/summary?refresh=true`).then(r => r.json()),
            authFetch(`${API_BASE}/exchanges/coinbase?refresh=true`).then(r => r.json()).catch(() => null),
            authFetch(`${API_BASE}/nfts?force_refresh=true`).then(r => r.json()).catch(() => null)
        ];

        // Get wallets to refresh staking
        const walletsResponse = await authFetch(`${API_BASE}/wallets`);
        const walletsData = await walletsResponse.json();
        const cardanoWallets = walletsData.wallets.filter(w => w.blockchain === 'cardano');

        // Refresh staking for all wallets with force refresh
        for (const wallet of cardanoWallets) {
            refreshPromises.push(
                authFetch(`${API_BASE}/defi/staking/${wallet.address}?refresh=true`).then(r => r.json()).catch(() => null)
            );
        }

        await Promise.all(refreshPromises);

        // Also refresh Ethereum, Solana, Polygon, Base, BSC, Arbitrum, and Avalanche NFTs
        authFetch(`${API_BASE}/nfts/ethereum?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/solana?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/polygon?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/base?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/bsc?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/arbitrum?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/avalanche?force_refresh=true`).catch(() => null);

        // Reload all UI components (force refresh for global refresh)
        await loadPortfolioSummary();
        await loadExchangeData();
        // On assets page, load full DeFi UI; on dashboard, just load totals
        if (document.getElementById('defiGovernanceContent')) {
            await loadDefiGovernance();
        } else {
            await loadPortfolioTotals();
        }

        // Load NFT summaries for all chains, then load current chain's list
        await loadAllNftSummaries();
        if (currentNFTChain === 'cardano') {
            loadNFTs();
        } else if (currentNFTChain === 'ethereum') {
            loadEthereumNFTs();
        } else if (currentNFTChain === 'solana') {
            loadSolanaNFTs();
        } else if (currentNFTChain === 'polygon') {
            loadPolygonNFTs();
        } else if (currentNFTChain === 'base') {
            loadBaseNFTs();
        } else if (currentNFTChain === 'algorand') {
            loadAlgorandNFTs();
        } else if (currentNFTChain === 'bsc') {
            loadBscNFTs();
        } else if (currentNFTChain === 'arbitrum') {
            loadArbitrumNFTs();
        } else if (currentNFTChain === 'avalanche') {
            loadAvalancheNFTs();
        }

        // Refresh portfolio card stats (fire-and-forget)
        load7DayPortfolioChange();
        load7DayTransactionCount();

        showStatus('All data refreshed successfully');
    } catch (error) {
        console.error('Error during global refresh:', error);
        showStatus('Some data failed to refresh', true);
    } finally {
        if (btn) {
            btn.classList.remove('refreshing');
            btn.disabled = false;
        }
    }
}

// ============================================
// Portfolio History Chart (V1 Legacy — preserved for rollback)
// The unified chart endpoint (/portfolio/chart/unified) is now primary.
// ============================================

// Chart instance and data storage
let portfolioChart = null;
let portfolioHistoryData = null;
let currentChartRange = '7d';

// Get selected chart categories
function getChartCategories() {
    return {
        wallets: document.getElementById('chartWallets')?.checked ?? true,
        exchanges: document.getElementById('chartExchanges')?.checked ?? true,
        staking: document.getElementById('chartStaking')?.checked ?? true,
        defi: document.getElementById('chartDefi')?.checked ?? true,
        nfts: document.getElementById('chartNfts')?.checked ?? true,
        trackedTokens: document.getElementById('chartTrackedTokens')?.checked ?? true
    };
}

// Calculate chart values based on selected categories
function calculateChartValues(historyData, categories) {
    return historyData.map(d => {
        let value = 0;
        const breakdown = d.breakdown || {};

        if (categories.wallets) value += breakdown.wallets || 0;
        if (categories.exchanges) value += breakdown.exchange || 0;
        if (categories.staking) value += breakdown.staking || 0;
        if (categories.defi) value += breakdown.defi || 0;
        if (categories.nfts) value += breakdown.nfts || 0;
        if (categories.trackedTokens) value += breakdown.tracked_tokens || 0;

        return value;
    });
}

// Update chart when category toggles change
function updateChartCategories() {
    if (portfolioHistoryData && portfolioHistoryData.length > 0) {
        renderPortfolioChart(portfolioHistoryData, currentChartRange);
    }
}

// Load and render portfolio history chart
// Helper functions to get current portfolio values for chart
function getCurrentPortfolioTotal() {
    // Calculate current total from in-memory data (same logic as updateTotalPortfolioValue)
    const walletPriceMap = {
        ADA: 'ADA', BTC: 'BTC', ETH: 'ETH', SOL: 'SOL', MATIC: 'MATIC',
        ETH_BASE: 'ETH', ALGO: 'ALGO', BNB: 'BNB', ETH_ARB: 'ETH',
        AVAX: 'AVAX', TRX: 'TRX', XRP: 'XRP', HBAR: 'HBAR', EGLD: 'EGLD',
        SUI: 'SUI', APT: 'APT', FIL: 'FIL', LTC: 'LTC', DOGE: 'DOGE',
        ZEC: 'ZEC', XTZ: 'XTZ', STX: 'STX', VET: 'VET', ATOM: 'ATOM',
        NEAR: 'NEAR', ICP: 'ICP'
    };
    let walletsTotal = 0;
    for (const [walletKey, priceKey] of Object.entries(walletPriceMap)) {
        walletsTotal += (walletTotals[walletKey] || 0) * (prices[priceKey] || 0);
    }

    let stakingTotal = 0;
    for (const [token, amount] of Object.entries(stakingTotals)) {
        stakingTotal += amount * (prices[token] || 0);
    }

    let defiTotal = 0;
    for (const [token, amount] of Object.entries(defiTotals)) {
        defiTotal += amount * (prices[token] || 0);
    }

    const exchangesTotal = exchangeTotals.usd || 0;
    const nftsTotal = getNftTotalUsd();
    const trackedTokensTotal = trackedTokensValue || 0;
    const customTokensTotal = customTokensValue || 0;

    return walletsTotal + exchangesTotal + stakingTotal + defiTotal + nftsTotal + trackedTokensTotal + customTokensTotal;
}

function getCurrentPortfolioBreakdown() {
    // Return breakdown for chart (matches snapshot format)
    const walletPriceMap = {
        ADA: 'ADA', BTC: 'BTC', ETH: 'ETH', SOL: 'SOL', MATIC: 'MATIC',
        ETH_BASE: 'ETH', ALGO: 'ALGO', BNB: 'BNB', ETH_ARB: 'ETH',
        AVAX: 'AVAX', TRX: 'TRX', XRP: 'XRP', HBAR: 'HBAR', EGLD: 'EGLD',
        SUI: 'SUI', APT: 'APT', FIL: 'FIL', LTC: 'LTC', DOGE: 'DOGE',
        ZEC: 'ZEC', XTZ: 'XTZ', STX: 'STX', VET: 'VET', ATOM: 'ATOM',
        NEAR: 'NEAR', ICP: 'ICP'
    };
    let walletsTotal = 0;
    for (const [walletKey, priceKey] of Object.entries(walletPriceMap)) {
        walletsTotal += (walletTotals[walletKey] || 0) * (prices[priceKey] || 0);
    }

    let stakingTotal = 0;
    for (const [token, amount] of Object.entries(stakingTotals)) {
        stakingTotal += amount * (prices[token] || 0);
    }

    let defiTotal = 0;
    for (const [token, amount] of Object.entries(defiTotals)) {
        defiTotal += amount * (prices[token] || 0);
    }

    const exchangesTotal = exchangeTotals.usd || 0;
    const nftsTotal = getNftTotalUsd();
    const trackedTokensTotal = trackedTokensValue || 0;
    const customTokensTotal = customTokensValue || 0;

    return {
        wallets: walletsTotal,
        staking: stakingTotal,
        defi: defiTotal,
        exchange: exchangesTotal,
        nfts: nftsTotal,
        tracked_tokens: trackedTokensTotal + customTokensTotal
    };
}

async function loadPortfolioHistory(range = '7d') {
    const chartContainer = document.getElementById('portfolioHistoryChart');
    const emptyState = document.getElementById('chartEmptyState');
    const lastUpdate = document.getElementById('historyLastUpdate');

    if (!chartContainer) return;

    currentChartRange = range;

    try {
        const response = await authFetch(`${API_BASE}/portfolio/history?range=${range}`);
        const data = await response.json();

        if (data.data && data.data.length > 0) {
            // For hourly data (1d), use current timestamp; for daily data, use today's date
            const now = new Date();
            const today = now.toISOString().split('T')[0];
            const isHourly = range === '1d';

            const historyData = data.data.map(entry => {
                // For hourly: check if entry is recent (within last hour)
                // For daily: check if entry is today
                let isCurrent = false;
                if (isHourly) {
                    const entryTime = new Date(entry.date);
                    const hoursDiff = (now - entryTime) / (1000 * 60 * 60);
                    isCurrent = hoursDiff < 1; // Within last hour
                } else {
                    isCurrent = entry.date === today;
                }

                if (isCurrent) {
                    // Calculate current total value from in-memory data
                    const currentTotal = getCurrentPortfolioTotal();
                    return {
                        ...entry,
                        value: currentTotal,
                        // Update breakdown with current values if available
                        breakdown: getCurrentPortfolioBreakdown()
                    };
                }
                return entry;
            });

            // Add current data point if not present
            let hasCurrentData = false;
            if (isHourly) {
                // For hourly, check if we have data from the last hour
                hasCurrentData = historyData.some(entry => {
                    const entryTime = new Date(entry.date);
                    const hoursDiff = (now - entryTime) / (1000 * 60 * 60);
                    return hoursDiff < 1;
                });
            } else {
                hasCurrentData = historyData.some(entry => entry.date === today);
            }

            if (!hasCurrentData) {
                historyData.push({
                    date: isHourly ? now.toISOString() : today,
                    value: getCurrentPortfolioTotal(),
                    breakdown: getCurrentPortfolioBreakdown()
                });
            }

            // Store data globally for category toggle updates
            portfolioHistoryData = historyData;

            // Hide empty state, show chart
            if (emptyState) emptyState.style.display = 'none';
            chartContainer.style.display = 'block';
            renderPortfolioChart(historyData, range);
        } else {
            // Show empty state, hide chart
            portfolioHistoryData = null;
            if (emptyState) {
                emptyState.style.display = 'flex';
                setSafeHTML(emptyState, '<p>No historical data yet.</p><p class="chart-empty-hint">Run a data collection from the On-Chain (v2) tab, or use the Rebuild button to regenerate history.</p>');
            }
            chartContainer.style.display = 'none';
            if (portfolioChart) {
                portfolioChart.destroy();
                portfolioChart = null;
            }
        }

        // Update last snapshot time
        if (lastUpdate && data.latest_snapshot) {
            lastUpdate.textContent = `Last snapshot: ${data.latest_snapshot}`;
        } else if (lastUpdate) {
            lastUpdate.textContent = 'Last snapshot: No data yet';
        }
    } catch (error) {
        console.error('Error loading portfolio history:', error);
        portfolioHistoryData = null;
        if (emptyState) {
            emptyState.style.display = 'flex';
            setSafeHTML(emptyState, '<p>Error loading history data.</p>');
        }
    }
}

// V1 history generation removed — these are no-op stubs for backward compat
async function generatePortfolioHistory() { /* V1 removed */ }
async function checkRunningHistoryGeneration() { /* V1 removed */ }

// Get theme colors for chart
function getChartColors() {
    const style = getComputedStyle(document.documentElement);
    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';

    // All themes share: gradient line, no point dots, crosshair hover
    const shared = { useGradientLine: true, hidePoints: true };

    if (theme === 'light') {
        return { ...shared,
            lineColor: '#00b894',
            fillColor: 'rgba(0, 184, 148, 0.08)',
            pointColor: '#00b894',
            pointBorderColor: '#ffffff',
            gridColor: 'rgba(229, 231, 235, 0.8)',
            tickColor: '#6b7280',
            tooltipBg: '#ffffff',
            tooltipTitle: '#1a1a2e',
            tooltipBody: '#00b894',
            tooltipBorder: '#e5e7eb',
            crosshairColor: 'rgba(107, 114, 128, 0.4)',
            gradientStops: ['#6366f1', '#06b6d4', '#10b981', '#22c55e']
        };
    }

    if (theme === 'cypherpunk1') {
        return { ...shared,
            lineColor: '#00d4ff',
            fillColor: 'rgba(0, 212, 255, 0.12)',
            pointColor: '#00d4ff',
            pointBorderColor: '#030308',
            gridColor: 'rgba(124, 58, 237, 0.2)',
            tickColor: '#8ec8ff',
            tooltipBg: '#0c0c24',
            tooltipTitle: '#e0f0ff',
            tooltipBody: '#00d4ff',
            tooltipBorder: '#7c3aed',
            crosshairColor: 'rgba(0, 212, 255, 0.4)',
            gradientStops: ['#00d4ff', '#7c3aed', '#d946ef', '#00d4ff']
        };
    }

    if (theme === 'ocean-depths') {
        return { ...shared,
            lineColor: '#00b4d8',
            fillColor: 'rgba(0, 180, 216, 0.12)',
            pointColor: '#00b4d8',
            pointBorderColor: '#0a1628',
            gridColor: 'rgba(26, 74, 110, 0.3)',
            tickColor: '#7ec8e3',
            tooltipBg: '#0d2137',
            tooltipTitle: '#e0f4ff',
            tooltipBody: '#00b4d8',
            tooltipBorder: '#1a4a6e',
            crosshairColor: 'rgba(0, 180, 216, 0.3)',
            gradientStops: ['#7c3aed', '#0077b6', '#00b4d8', '#48cae4']
        };
    }

    if (theme === 'sunset-horizon') {
        return { ...shared,
            lineColor: '#ff6b35',
            fillColor: 'rgba(255, 107, 53, 0.12)',
            pointColor: '#ff6b35',
            pointBorderColor: '#1a0a1a',
            gridColor: 'rgba(92, 42, 92, 0.3)',
            tickColor: '#ffb4a2',
            tooltipBg: '#2d1233',
            tooltipTitle: '#ffe4e1',
            tooltipBody: '#ff6b35',
            tooltipBorder: '#5c2a5c',
            crosshairColor: 'rgba(255, 107, 53, 0.3)',
            gradientStops: ['#a855f7', '#ff3366', '#ff6b35', '#ffc145']
        };
    }

    if (theme === 'cypher3') {
        return { ...shared,
            lineColor: '#7c3aed',
            fillColor: 'rgba(124, 58, 237, 0.06)',
            pointColor: '#7c3aed',
            pointBorderColor: '#0d0f1a',
            gridColor: 'rgba(100, 100, 200, 0.08)',
            tickColor: '#5a5d70',
            tooltipBg: '#1a1d2e',
            tooltipTitle: '#e8e8f0',
            tooltipBody: '#4ade80',
            tooltipBorder: 'rgba(100, 100, 200, 0.15)',
            crosshairColor: 'rgba(124, 58, 237, 0.3)',
            gradientStops: ['#a855f7', '#ec4899', '#4ade80', '#22d3ee']
        };
    }

    if (theme === 'cypher' || theme === 'cypher2') {
        return { ...shared,
            lineColor: '#a855f7',
            fillColor: 'rgba(168, 85, 247, 0.05)',
            pointColor: '#a855f7',
            pointBorderColor: '#000000',
            gridColor: '#1a1a1a',
            tickColor: '#666666',
            tooltipBg: '#141414',
            tooltipTitle: '#ffffff',
            tooltipBody: '#a855f7',
            tooltipBorder: '#2a2a2a',
            crosshairColor: '#444444',
            gradientStops: ['#a855f7', '#ec4899', '#f97316', '#facc15']
        };
    }

    // Default (dark-mode) theme colors
    return { ...shared,
        lineColor: '#00d26a',
        fillColor: 'rgba(0, 210, 106, 0.08)',
        pointColor: '#00d26a',
        pointBorderColor: '#1a1a2e',
        gridColor: 'rgba(42, 42, 74, 0.5)',
        tickColor: '#a0a0a0',
        tooltipBg: '#0f3460',
        tooltipTitle: '#eaeaea',
        tooltipBody: '#00d26a',
        tooltipBorder: '#2a2a4a',
        crosshairColor: 'rgba(0, 210, 106, 0.3)',
        gradientStops: ['#a855f7', '#ec4899', '#f97316', '#00d26a']
    };
}

// Render the portfolio chart with Chart.js
function renderPortfolioChart(historyData, range) {
    const ctx = document.getElementById('portfolioHistoryChart');
    if (!ctx) return;

    // Destroy existing chart if it exists
    if (portfolioChart) {
        portfolioChart.destroy();
    }

    // Get theme-appropriate colors
    const colors = getChartColors();

    // Get selected categories and calculate values
    const categories = getChartCategories();
    const labels = historyData.map(d => formatChartDate(d.date, range));

    // Use breakdown values if available, otherwise fall back to total value
    let values;
    const hasBreakdown = historyData.some(d => d.breakdown);
    if (hasBreakdown) {
        values = calculateChartValues(historyData, categories);
    } else {
        // Fallback for old data without breakdown
        values = historyData.map(d => d.value);
    }

    // Calculate min/max for better Y-axis scaling
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const padding = (maxValue - minValue) * 0.1 || maxValue * 0.1;

    // Plugin: rebuild gradient using actual chart area dimensions after layout
    // (canvas.width before Chart.js init is CSS width, but Chart.js may resize
    //  for devicePixelRatio, making pre-built gradients cover only a fraction)
    const gradientPlugin = {
        id: 'dynamicGradient',
        afterLayout: (chart) => {
            if (!colors.useGradientLine || !colors.gradientStops) return;
            const area = chart.chartArea;
            if (!area) return;
            const drawCtx = chart.ctx;
            // Horizontal gradient spanning the full chart area
            const lineGrad = drawCtx.createLinearGradient(area.left, 0, area.right, 0);
            const stops = colors.gradientStops;
            for (let i = 0; i < stops.length; i++) {
                lineGrad.addColorStop(i / (stops.length - 1), stops[i]);
            }
            chart.data.datasets[0].borderColor = lineGrad;
            // Vertical fill gradient (top fade to transparent)
            const fillGrad = drawCtx.createLinearGradient(0, area.top, 0, area.bottom);
            fillGrad.addColorStop(0, colors.fillColor);
            fillGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            chart.data.datasets[0].backgroundColor = fillGrad;
        }
    };

    // Crosshair plugin
    const crosshairPlugin = {
        id: 'crosshairLine',
        afterDraw: (chart) => {
            if (!colors.crosshairColor) return;
            const activeElements = chart.tooltip?.getActiveElements();
            if (activeElements && activeElements.length > 0) {
                const x = activeElements[0].element.x;
                const yAxis = chart.scales.y;
                const drawCtx = chart.ctx;
                drawCtx.save();
                drawCtx.beginPath();
                drawCtx.setLineDash([4, 4]);
                drawCtx.strokeStyle = colors.crosshairColor;
                drawCtx.lineWidth = 1;
                drawCtx.moveTo(x, yAxis.top);
                drawCtx.lineTo(x, yAxis.bottom);
                drawCtx.stroke();
                drawCtx.restore();
            }
        }
    };

    portfolioChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Portfolio Value',
                data: values,
                borderColor: colors.lineColor,
                backgroundColor: colors.fillColor,
                fill: true,
                tension: 0.3,
                borderWidth: 3,
                pointRadius: colors.hidePoints ? 0 : 5,
                pointHoverRadius: colors.hidePoints ? 0 : 10,
                pointBackgroundColor: colors.pointColor,
                pointBorderColor: colors.pointBorderColor,
                pointBorderWidth: 2,
                pointHoverBackgroundColor: colors.lineColor,
                pointHoverBorderColor: '#ffffff',
                pointHoverBorderWidth: 2
            }]
        },
        plugins: [gradientPlugin, crosshairPlugin],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: colors.tooltipBg,
                    titleColor: colors.tooltipTitle,
                    bodyColor: colors.tooltipBody,
                    borderColor: colors.tooltipBorder,
                    borderWidth: 2,
                    padding: 14,
                    displayColors: false,
                    callbacks: {
                        title: function(context) {
                            // Show formatted date in tooltip
                            const dataIndex = context[0].dataIndex;
                            const dateStr = historyData[dataIndex].date;
                            if (range === '1d') {
                                const d = new Date(dateStr);
                                return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
                            }
                            const d = new Date(dateStr + 'T12:00:00');
                            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                        },
                        label: function(context) {
                            // Total value (large/primary text)
                            return formatUSD(context.parsed.y);
                        },
                        footer: function(context) {
                            const dataIndex = context[0].dataIndex;
                            const dataPoint = historyData[dataIndex];
                            const lines = [];

                            // Add breakdown if available
                            if (dataPoint.breakdown) {
                                const breakdown = dataPoint.breakdown;

                                if (breakdown.wallets > 0) {
                                    lines.push(`Wallets: ${formatUSD(breakdown.wallets)}`);
                                }
                                if (breakdown.exchange > 0) {
                                    lines.push(`Exchanges: ${formatUSD(breakdown.exchange)}`);
                                }
                                if (breakdown.staking > 0) {
                                    lines.push(`Staking: ${formatUSD(breakdown.staking)}`);
                                }
                                if (breakdown.defi > 0) {
                                    lines.push(`DeFi: ${formatUSD(breakdown.defi)}`);
                                }
                                if (breakdown.nfts > 0) {
                                    lines.push(`NFTs: ${formatUSD(breakdown.nfts)}`);
                                }
                                if (breakdown.tracked_tokens > 0) {
                                    lines.push(`Tokens: ${formatUSD(breakdown.tracked_tokens)}`);
                                }
                            }

                            return lines;
                        }
                    },
                    // Style for the main label (total value) - large and bold
                    bodyFont: {
                        size: 18,
                        weight: 'bold'
                    },
                    // Style for the breakdown (footer) - smaller text
                    footerFont: {
                        size: 11,
                        weight: 'normal'
                    },
                    footerColor: colors.tooltipBody,
                    footerAlign: 'left',
                    footerSpacing: 4,
                    footerMarginTop: 8
                }
            },
            scales: {
                x: {
                    grid: {
                        color: colors.gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: colors.tickColor,
                        font: {
                            size: 11
                        },
                        maxRotation: 45,
                        minRotation: 0
                    }
                },
                y: {
                    min: Math.max(0, minValue - padding),
                    max: maxValue + padding,
                    grid: {
                        color: colors.gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: colors.tickColor,
                        font: {
                            size: 11
                        },
                        callback: function(value) {
                            return formatUSD(value);
                        }
                    }
                }
            }
        }
    });
}

// Initialize range button click handlers
function initHistoryRangeButtons() {
    // Only bind v1 range buttons (not v2 which use onclick)
    const buttons = document.querySelectorAll('#v1RangeSelector .range-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadPortfolioHistory(btn.dataset.range);
        });
    });
}

// Format date for chart display based on range
function formatChartDate(dateStr, range) {
    // For 1d range, dateStr is an ISO timestamp (hourly data)
    if (range === '1d') {
        const date = new Date(dateStr);
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    }

    // For other ranges, dateStr is a date string (daily data)
    const date = new Date(dateStr + 'T12:00:00'); // Add time to avoid timezone issues
    if (range === '7d') {
        return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    } else if (range === '4w') {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
}

// ============================================================================
// V2 ON-CHAIN BALANCE HISTORY
// ============================================================================

let v2Chart = null;
let v2ChartMode = 'combined'; // 'combined' or 'by_chain'
let v2PollInterval = null;

const chartDataCache = {
    _store: {},
    ttl: 5 * 60 * 1000, // 5 minutes
    key(range, mode) { return `${range}_${mode}`; },
    get(range, mode) {
        const entry = this._store[this.key(range, mode)];
        if (!entry) return null;
        if (Date.now() - entry.ts > this.ttl) { delete this._store[this.key(range, mode)]; return null; }
        return entry.data;
    },
    set(range, mode, data) { this._store[this.key(range, mode)] = { data, ts: Date.now() }; },
    clear() { this._store = {}; },
};

function toggleChartMode() {
    v2ChartMode = v2ChartMode === 'combined' ? 'by_chain' : 'combined';
    const btn = document.getElementById('chartModeToggle');
    if (btn) {
        btn.textContent = v2ChartMode === 'combined' ? 'By Chain' : 'Combined';
        btn.classList.toggle('active', v2ChartMode === 'by_chain');
    }
    const activeBtn = document.querySelector('.v2-range.active');
    const range = activeBtn ? activeBtn.dataset.range : '1w';
    loadV2BalanceHistory(range);
}

async function loadV2BalanceHistory(range) {
    // Update active v2 range button
    document.querySelectorAll('.v2-range').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.range === range);
    });

    const chartCanvas = document.getElementById('v2HistoryChart');
    const emptyState = document.getElementById('v2ChartEmptyState');
    const loadingState = document.getElementById('v2ChartLoadingState');
    const coverageText = document.getElementById('v2CoverageText');

    // Show loading spinner (unless we have a cached result)
    const cached = chartDataCache.get(range, v2ChartMode);
    if (!cached && loadingState) {
        if (emptyState) emptyState.style.display = 'none';
        loadingState.style.display = 'flex';
    }

    try {
        // Check client-side cache first
        let result = cached;
        if (!result) {
            let url;
            url = `${API_BASE}/portfolio/chart/unified?range=${range}`;
            if (v2ChartMode === 'by_chain') url += '&by_chain=true';

            const response = await authFetch(url);
            if (!response.ok) {
                console.error('V2 balance history API returned', response.status);
                throw new Error(`API error ${response.status}`);
            }
            result = await response.json();
            if (result.data && result.data.length > 0) {
                chartDataCache.set(range, v2ChartMode, result);
            }
        }

        // Hide loading spinner
        if (loadingState) loadingState.style.display = 'none';

        if (result.data && result.data.length > 0) {
            if (emptyState) emptyState.style.display = 'none';
            if (chartCanvas) chartCanvas.style.display = 'block';

            if (v2ChartMode === 'by_chain' && result.chains) {
                renderV2ChartByChain(result.data, result.chains, range);
            } else {
                renderV2Chart(result.data, range);
            }

            // Update coverage info
            if (coverageText && result.coverage) {
                const c = result.coverage;
                if (c.oldest_date && c.newest_date) {
                    const unit = range === '24h' ? 'hours' : 'days';
                    coverageText.textContent = `Coverage: ${c.oldest_date} to ${c.newest_date} (${c.total_days} ${unit})`;
                }
            }
        } else {
            if (emptyState) emptyState.style.display = 'flex';
            if (chartCanvas) chartCanvas.style.display = 'none';
            if (v2Chart) {
                v2Chart.destroy();
                v2Chart = null;
            }
        }
    } catch (error) {
        console.error('Error loading v2 balance history:', error);
        if (loadingState) loadingState.style.display = 'none';
        if (emptyState) {
            emptyState.style.display = 'flex';
            setSafeHTML(emptyState, '<p>Error loading on-chain history.</p><button class="btn btn-primary" data-action="collect">Collect Historical Balances</button>');
            emptyState.querySelector('[data-action="collect"]')?.addEventListener('click', startBalanceCollection);
        }
    }
}

function renderV2Chart(data, range) {
    const ctx = document.getElementById('v2HistoryChart');
    if (!ctx) return;

    if (v2Chart) {
        v2Chart.destroy();
    }

    const colors = getChartColors();
    const labels = data.map(d => {
        if (d.date.includes('T')) {
            // Hourly data: show "2:00 PM" format
            const [datePart, timePart] = d.date.split('T');
            const date = new Date(datePart + 'T' + timePart + ':00Z');
            return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        const date = new Date(d.date + 'T12:00:00');
        if (range === '24h' || range === '1w') {
            return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
        }
        if (range === '1m' || range === '3m') {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    });
    const values = data.map(d => d.total_value ?? d.value ?? 0);

    // Calculate Y axis range with padding
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const valueRange = maxValue - minValue || 1;
    const padding = valueRange * 0.1;

    // Plugin: rebuild gradient using actual chart area after layout
    const v2GradientPlugin = {
        id: 'v2DynamicGradient',
        afterLayout: (chart) => {
            if (!colors.useGradientLine || !colors.gradientStops) return;
            const area = chart.chartArea;
            if (!area) return;
            const drawCtx = chart.ctx;
            const lineGrad = drawCtx.createLinearGradient(area.left, 0, area.right, 0);
            const stops = colors.gradientStops;
            for (let i = 0; i < stops.length; i++) {
                lineGrad.addColorStop(i / (stops.length - 1), stops[i]);
            }
            chart.data.datasets[0].borderColor = lineGrad;
            const fillGrad = drawCtx.createLinearGradient(0, area.top, 0, area.bottom);
            fillGrad.addColorStop(0, colors.fillColor);
            fillGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
            chart.data.datasets[0].backgroundColor = fillGrad;
        }
    };

    v2Chart = new Chart(ctx, {
        type: 'line',
        plugins: [v2GradientPlugin],
        data: {
            labels: labels,
            datasets: [{
                label: 'Portfolio Value',
                data: values,
                borderColor: colors.lineColor,
                backgroundColor: colors.fillColor,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: colors.pointColor,
                pointHoverBorderColor: colors.pointBorderColor,
                pointHoverBorderWidth: 2,
                borderWidth: 3,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: colors.tooltipBg,
                    titleColor: colors.tooltipTitle,
                    bodyColor: colors.tooltipBody,
                    borderColor: colors.tooltipBorder,
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return formatUSD(context.parsed.y);
                        },
                        afterBody: function(tooltipItems) {
                            const idx = tooltipItems[0].dataIndex;
                            const point = data[idx];
                            if (!point) return [];
                            const lines = [];
                            // Component breakdown
                            const comps = point.breakdown?.components;
                            if (comps) {
                                const compLabels = {wallets: 'Wallets', exchange: 'Exchange', staking: 'Staking', defi: 'DeFi', nfts: 'NFTs', tracked_tokens: 'Tracked'};
                                for (const [key, label] of Object.entries(compLabels)) {
                                    const val = comps[key] || 0;
                                    if (val > 0) lines.push(`  ${label}: ${formatUSD(val)}`);
                                }
                            }
                            // Chain breakdown
                            const chains = point.breakdown?.chains || point.chains;
                            if (chains && Object.keys(chains).length > 0) {
                                lines.push('  ───');
                                for (const [chain, val] of Object.entries(chains)) {
                                    if (val > 0) lines.push(`  ${chain}: ${formatUSD(val)}`);
                                }
                            }
                            return lines;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: colors.gridColor, drawBorder: false },
                    ticks: {
                        color: colors.tickColor,
                        font: { size: 11 },
                        maxRotation: 45,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    min: Math.max(0, minValue - padding),
                    max: maxValue + padding,
                    grid: { color: colors.gridColor, drawBorder: false },
                    ticks: {
                        color: colors.tickColor,
                        font: { size: 11 },
                        callback: function(value) { return formatUSD(value); }
                    }
                }
            }
        }
    });
}

const CHAIN_COLORS = {
    cardano: '#3366FF', bitcoin: '#FF9F1A', ethereum: '#879BFF',
    solana: '#00FFB2', polygon: '#A36BFF', base: '#4D8AFF',
    algorand: '#6DC8C8', bnb: '#FFD84D', arbitrum: '#4DB8FF',
    avalanche: '#FF5B5B', tron: '#FF4D4D',
};
let v2HighlightedChainIdx = null; // track which dataset is highlighted

function getChainColor(chain) {
    return CHAIN_COLORS[chain.toLowerCase()] || '#' + (chain.charCodeAt(0) * 123456 % 0xFFFFFF).toString(16).padStart(6, '0');
}

function renderV2ChartByChain(data, chainList, range) {
    const ctx = document.getElementById('v2HistoryChart');
    if (!ctx) return;
    if (v2Chart) v2Chart.destroy();

    const colors = getChartColors();

    const labels = data.map(d => {
        if (d.date.includes('T')) {
            const [datePart, timePart] = d.date.split('T');
            const date = new Date(datePart + 'T' + timePart + ':00Z');
            return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        const date = new Date(d.date + 'T12:00:00');
        if (range === '24h' || range === '1w') {
            return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
        }
        if (range === '1m' || range === '3m') {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    });

    // Build per-chain datasets
    v2HighlightedChainIdx = null;
    const datasets = [];
    for (const chain of chainList) {
        const chainColor = getChainColor(chain);
        datasets.push({
            label: chain.charAt(0).toUpperCase() + chain.slice(1),
            data: data.map(d => (d.chains && d.chains[chain]) || 0),
            borderColor: chainColor,
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: chainColor,
            borderWidth: 2.5,
            _origColor: chainColor,
            _origWidth: 2.5,
        });
    }

    // Y-axis range based on per-chain values only
    const allChainValues = datasets.flatMap(ds => ds.data);
    const minValue = Math.min(...allChainValues);
    const maxValue = Math.max(...allChainValues);
    const valueRange = maxValue - minValue || 1;
    const padding = valueRange * 0.1;

    v2Chart = new Chart(ctx, {
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
                    labels: {
                        color: colors.tickColor,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 16,
                        font: { size: 11 },
                    },
                    onClick: function(e, legendItem, legend) {
                        const chart = legend.chart;
                        const idx = legendItem.datasetIndex;
                        const dimColor = (c) => typeof c === 'string' ? c + '30' : c;
                        if (v2HighlightedChainIdx === idx) {
                            v2HighlightedChainIdx = null;
                            chart.data.datasets.forEach(ds => {
                                ds.borderColor = ds._origColor;
                                ds.borderWidth = ds._origWidth;
                            });
                        } else {
                            v2HighlightedChainIdx = idx;
                            chart.data.datasets.forEach((ds, i) => {
                                if (i === idx) {
                                    ds.borderColor = ds._origColor;
                                    ds.borderWidth = 4;
                                } else {
                                    ds.borderColor = dimColor(ds._origColor);
                                    ds.borderWidth = 1;
                                }
                            });
                        }
                        chart.update();
                    }
                },
                tooltip: {
                    backgroundColor: colors.tooltipBg,
                    titleColor: colors.tooltipTitle,
                    bodyColor: colors.tooltipBody,
                    borderColor: colors.tooltipBorder,
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const val = context.parsed.y;
                            if (val === 0) return null;
                            return `  ${label}: ${formatUSD(val)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: colors.gridColor, drawBorder: false },
                    ticks: {
                        color: colors.tickColor,
                        font: { size: 11 },
                        maxRotation: 45,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    min: Math.max(0, minValue - padding),
                    max: maxValue + padding,
                    grid: { color: colors.gridColor, drawBorder: false },
                    ticks: {
                        color: colors.tickColor,
                        font: { size: 11 },
                        callback: function(value) { return formatUSD(value); }
                    }
                }
            }
        }
    });
}

async function startBalanceCollection() {
    const emptyState = document.getElementById('v2ChartEmptyState');
    const loadingState = document.getElementById('v2ChartLoadingState');
    const progress = document.getElementById('v2CollectionProgress');

    if (emptyState) emptyState.style.display = 'none';
    if (loadingState) loadingState.style.display = 'none';
    if (progress) progress.style.display = 'block';

    try {
        const response = await authFetch(`${API_BASE}/balance-history/collect?force=true`, {
            method: 'POST'
        });
        if (!response.ok) {
            console.error('V2 collect API returned', response.status);
            throw new Error(`API error ${response.status}`);
        }
        const data = await response.json();

        if (data.status === 'started') {
            pollV2CollectionStatus();
        }
    } catch (error) {
        console.error('Error starting balance collection:', error);
        if (progress) progress.style.display = 'none';
        if (emptyState) {
            emptyState.style.display = 'flex';
            setSafeHTML(emptyState, '<p>Error starting collection.</p><button class="btn btn-primary" data-action="collect">Retry</button>');
            emptyState.querySelector('[data-action="collect"]')?.addEventListener('click', startBalanceCollection);
        }
    }
}

function pollV2CollectionStatus() {
    if (v2PollInterval) clearInterval(v2PollInterval);

    v2PollInterval = setInterval(async () => {
        try {
            const response = await authFetch(`${API_BASE}/balance-history/collect/status`);
            const data = await response.json();

            const stepEl = document.getElementById('v2ProgressStep');
            const barEl = document.getElementById('v2ProgressBar');
            const pctEl = document.getElementById('v2ProgressPct');

            if (stepEl) stepEl.textContent = data.step || 'Working...';
            if (barEl) barEl.style.width = (data.progress || 0) + '%';
            if (pctEl) pctEl.textContent = (data.progress || 0) + '%';

            if (data.status === 'completed') {
                clearInterval(v2PollInterval);
                v2PollInterval = null;
                const progress = document.getElementById('v2CollectionProgress');
                if (progress) progress.style.display = 'none';
                // Clear cache and reload chart with fresh data
                chartDataCache.clear();
                const activeBtn = document.querySelector('.v2-range.active');
                const range = activeBtn ? activeBtn.dataset.range : '1y';
                await loadV2BalanceHistory(range);
                loadV2LastRun();
            } else if (data.status === 'error' || data.status === 'cancelled') {
                clearInterval(v2PollInterval);
                v2PollInterval = null;
                const progress = document.getElementById('v2CollectionProgress');
                if (progress) progress.style.display = 'none';
                const emptyState = document.getElementById('v2ChartEmptyState');
                if (emptyState) {
                    emptyState.style.display = 'flex';
                    const msg = data.status === 'cancelled' ? 'Collection cancelled.' : (data.error_message || 'Collection failed.');
                    setSafeHTML(emptyState, '<p>' + msg + '</p><button class="btn btn-primary" data-action="collect">Retry</button>');
                    emptyState.querySelector('[data-action="collect"]')?.addEventListener('click', startBalanceCollection);
                }
            }
        } catch (error) {
            console.error('Error polling v2 collection status:', error);
        }
    }, 3000);
}

async function cancelBalanceCollection() {
    try {
        await authFetch(`${API_BASE}/balance-history/collect/cancel`, { method: 'POST' });
    } catch (error) {
        console.error('Error cancelling collection:', error);
    }
}

async function checkV2CollectionStatus() {
    try {
        const response = await authFetch(`${API_BASE}/balance-history/collect/status`);
        const data = await response.json();

        if (data.status === 'running') {
            const emptyState = document.getElementById('v2ChartEmptyState');
            const progress = document.getElementById('v2CollectionProgress');
            if (emptyState) emptyState.style.display = 'none';
            if (progress) progress.style.display = 'block';
            pollV2CollectionStatus();
        }
    } catch (error) {
        // Silently ignore
    }
}

// V2 Balance History Scheduler Config
async function loadV2Schedule() {
    try {
        const response = await authFetch(`${API_BASE}/balance-history/schedule`);
        const data = await response.json();
        const select = document.getElementById('v2ScheduleSelect');
        if (select) {
            select.value = data.enabled ? String(data.interval_hours) : '0';
        }
    } catch (error) {
        console.error('Error loading v2 schedule:', error);
    }
}

async function saveV2Schedule() {
    const select = document.getElementById('v2ScheduleSelect');
    const statusEl = document.getElementById('v2ScheduleStatus');
    if (!select) return;

    const hours = parseInt(select.value, 10);
    const enabled = hours > 0;

    try {
        const response = await authFetch(`${API_BASE}/balance-history/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled, interval_hours: hours }),
        });
        const data = await response.json();
        if (statusEl) {
            statusEl.textContent = enabled ? `Saved — collecting every ${hours}h` : 'Saved — auto-collect off';
            setTimeout(() => { statusEl.textContent = ''; }, 3000);
        }
        loadV2LastRun();
    } catch (error) {
        console.error('Error saving v2 schedule:', error);
        if (statusEl) {
            statusEl.textContent = 'Error saving schedule';
            setTimeout(() => { statusEl.textContent = ''; }, 3000);
        }
    }
}

// V2 Last Run / Next Run Info
async function loadV2LastRun() {
    const infoDiv = document.getElementById('v2LastRunInfo');
    const lastText = document.getElementById('v2LastRunText');
    const nextText = document.getElementById('v2NextRunText');
    if (!infoDiv || !lastText) return;

    try {
        const response = await authFetch(`${API_BASE}/balance-history/last-run`);
        const data = await response.json();

        if (data.run) {
            infoDiv.style.display = '';
            const run = data.run;
            const ago = timeAgo(run.started_at);
            const trigger = run.trigger_type === 'scheduled' ? 'scheduled' : 'manual';
            const status = run.status || 'unknown';
            let detail = '';
            if (run.total_work_units) {
                detail = ` — ${run.completed_work_units || 0}/${run.total_work_units} work units`;
            }
            lastText.textContent = `Last run: ${ago} (${trigger}, ${status}${detail})`;
        } else {
            infoDiv.style.display = 'none';
        }

        if (nextText) {
            if (data.next_run) {
                const nextDt = new Date(data.next_run);
                const now = new Date();
                const diffMs = nextDt - now;
                if (diffMs > 0) {
                    const hours = Math.floor(diffMs / 3600000);
                    const mins = Math.floor((diffMs % 3600000) / 60000);
                    nextText.textContent = hours > 0 ? `Next run: in ${hours}h ${mins}m` : `Next run: in ${mins}m`;
                } else {
                    nextText.textContent = 'Next run: soon';
                }
            } else {
                nextText.textContent = '';
            }
        }
    } catch (error) {
        console.error('Error loading v2 last run:', error);
    }
}

function timeAgo(isoStr) {
    if (!isoStr) return 'unknown';
    const dt = new Date(isoStr);
    const now = new Date();
    const diffMs = now - dt;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

// ============================================================================
// CUSTOM TOKEN MANAGEMENT
// ============================================================================

// Store for custom tokens
let customTokens = [];

// Switch between Add Wallet and Add Token tabs
function switchAddTab(tabName) {
    const tabs = document.querySelectorAll('.add-tab');
    const forms = document.querySelectorAll('.add-form-content');

    tabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    forms.forEach(form => {
        if (form.id === 'addWalletForm' && tabName === 'wallet') {
            form.classList.add('active');
        } else if (form.id === 'addTokenForm' && tabName === 'token') {
            form.classList.add('active');
        } else {
            form.classList.remove('active');
        }
    });
}

// Handle token form submission
async function handleTokenFormSubmit(e) {
    e.preventDefault();

    const tokenInput = document.getElementById('tokenInput').value.trim();
    const quantity = document.getElementById('tokenQuantity').value.trim();
    const label = document.getElementById('tokenLabel').value.trim();

    if (!tokenInput || !quantity) {
        showStatus('Please enter token identifier and quantity', 'error');
        return;
    }

    // Check if it looks like a policy ID (56 chars hex) or contract address (0x...)
    const isCardanoPolicy = /^[a-fA-F0-9]{56}$/.test(tokenInput);
    const isEthContract = /^0x[a-fA-F0-9]{40}$/.test(tokenInput);

    if (isCardanoPolicy || isEthContract) {
        // Direct policy ID / contract address - add directly
        await addTokenDirect(tokenInput, isEthContract ? 'ethereum' : 'cardano', quantity, label);
    } else {
        // Looks like a ticker - show modal for policy ID
        openTokenModal(tokenInput, quantity, label);
    }
}

// Open the token policy ID modal
function openTokenModal(ticker = '', quantity = '', label = '') {
    const modal = document.getElementById('tokenPolicyModal');
    const quantityInput = document.getElementById('modalQuantity');
    const labelInput = document.getElementById('modalLabel');
    const resultDiv = document.getElementById('tokenLookupResult');

    // Pre-fill fields
    if (quantity) quantityInput.value = quantity;
    if (label) labelInput.value = label;
    document.getElementById('modalPolicyId').value = '';

    // Clear previous lookup results
    resultDiv.classList.add('hidden');
    setSafeHTML(resultDiv, '');

    // Show modal
    modal.classList.remove('hidden');
}

// Close the token modal
function closeTokenModal() {
    const modal = document.getElementById('tokenPolicyModal');
    modal.classList.add('hidden');

    // Clear form
    document.getElementById('modalPolicyId').value = '';
    document.getElementById('modalQuantity').value = '';
    document.getElementById('modalLabel').value = '';
    document.getElementById('tokenLookupResult').classList.add('hidden');
}

// Submit manual token from modal
async function submitManualToken() {
    // Check if demo mode
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    const chain = document.getElementById('modalChainSelect').value;
    const policyId = document.getElementById('modalPolicyId').value.trim();
    const quantity = document.getElementById('modalQuantity').value.trim();
    const label = document.getElementById('modalLabel').value.trim();
    const resultDiv = document.getElementById('tokenLookupResult');

    if (!policyId) {
        setSafeHTML(resultDiv, '<span>Please enter a Policy ID or Contract Address</span>');
        resultDiv.className = 'token-lookup-result error';
        resultDiv.classList.remove('hidden');
        return;
    }

    if (!quantity) {
        setSafeHTML(resultDiv, '<span>Please enter a quantity</span>');
        resultDiv.className = 'token-lookup-result error';
        resultDiv.classList.remove('hidden');
        return;
    }

    // Validate format
    if (chain === 'cardano' && !/^[a-fA-F0-9]{56}$/.test(policyId)) {
        setSafeHTML(resultDiv, '<span>Cardano Policy ID must be 56 hex characters</span>');
        resultDiv.className = 'token-lookup-result error';
        resultDiv.classList.remove('hidden');
        return;
    }

    if (chain === 'ethereum' && !/^0x[a-fA-F0-9]{40}$/.test(policyId)) {
        setSafeHTML(resultDiv, '<span>Ethereum contract address must be 42 characters starting with 0x</span>');
        resultDiv.className = 'token-lookup-result error';
        resultDiv.classList.remove('hidden');
        return;
    }

    await addTokenDirect(policyId, chain, quantity, label);
}

// Add a token directly with policy ID
async function addTokenDirect(policyId, blockchain, quantity, label) {
    const resultDiv = document.getElementById('tokenLookupResult');

    try {
        // First, try to look up token info
        const lookupResponse = await fetch(
            `${API_BASE}/custom-tokens/lookup?policy_id=${encodeURIComponent(policyId)}&blockchain=${blockchain}`
        );
        const lookupData = await lookupResponse.json();

        // Prepare token data
        const tokenData = {
            policy_id: policyId,
            blockchain: blockchain,
            quantity: parseFloat(quantity),
            label: label || null,
            ticker: lookupData.found ? lookupData.ticker : null
        };

        // Add the token
        const response = await authFetch(`${API_BASE}/custom-tokens`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(tokenData)
        });

        const result = await response.json();

        if (response.ok) {
            // Success
            if (lookupData.found) {
                setSafeHTML(resultDiv, `
                    <div class="token-info">
                        <span class="token-name">${lookupData.name || 'Token'} added successfully!</span>
                        ${lookupData.price_usd ? `<span class="token-price">Price: $${lookupData.price_usd.toFixed(4)}</span>` : ''}
                    </div>
                `);
                resultDiv.className = 'token-lookup-result success';
            } else {
                setSafeHTML(resultDiv, '<span>Token added successfully (ID not recognized, no pricing available)</span>');
                resultDiv.className = 'token-lookup-result success';
            }
            resultDiv.classList.remove('hidden');

            // Clear forms
            document.getElementById('tokenInput').value = '';
            document.getElementById('tokenQuantity').value = '';
            document.getElementById('tokenLabel').value = '';

            // Reload custom tokens
            await loadCustomTokens();

            // Close modal after a delay
            setTimeout(() => {
                closeTokenModal();
            }, 2000);

        } else {
            setSafeHTML(resultDiv, `<span>${result.detail || 'Error adding token'}</span>`);
            resultDiv.className = 'token-lookup-result error';
            resultDiv.classList.remove('hidden');
        }

    } catch (error) {
        console.error('Error adding token:', error);
        setSafeHTML(resultDiv, '<span>Error adding token. Please try again.</span>');
        resultDiv.className = 'token-lookup-result error';
        resultDiv.classList.remove('hidden');
    }
}

// Load custom tokens from API
async function loadCustomTokens() {
    try {
        const response = await authFetch(`${API_BASE}/custom-tokens`);
        const data = await response.json();
        customTokens = data.tokens || [];

        // Update tracked custom tokens value for portfolio total
        customTokensValue = data.tracked_total_usd || 0;

        // Update the custom tokens section in the UI
        displayCustomTokens(data);

    } catch (error) {
        console.error('Error loading custom tokens:', error);
    }
}

// Display custom tokens in the UI
function displayCustomTokens(data) {
    const tokensList = document.getElementById('customTokensList');
    const tokensSummary = document.getElementById('customTokensSummary');

    if (!tokensList) return;

    // Update summary - show tracked total
    if (tokensSummary) {
        const count = data.tokens?.length || 0;
        const trackedValue = data.tracked_total_usd || 0;
        setSafeHTML(tokensSummary, `
            <span>${count} token${count !== 1 ? 's' : ''}</span>
            ${trackedValue > 0 ? `<span class="tracked-value">Tracked: ${formatUSD(trackedValue)}</span>` : ''}
        `);
    }

    // If no custom tokens, show empty state
    if (!data.tokens || data.tokens.length === 0) {
        setSafeHTML(tokensList, '<p class="empty-state">No custom tokens added. Use "Add Token" below to track tokens manually.</p>');
        return;
    }

    // Build tokens HTML
    let tokensHtml = '';
    for (const token of data.tokens) {
        const displayName = token.token_name || token.ticker || token.label || 'Unknown Token';
        const quantity = parseFloat(token.quantity).toLocaleString();
        const valueUsd = token.value_usd ? formatUSD(token.value_usd) : 'N/A';
        const priceUsd = token.current_price ? `$${token.current_price.toFixed(4)}` : '';
        const isTracked = token.include_in_total === 1;

        const tokenValueNum = token.value_usd || 0;
        tokensHtml += `
            <div class="custom-token-item ${token.blockchain} ${isTracked ? 'tracked' : ''}"
                 data-token-id="${token.id}"
                 data-value="${tokenValueNum}">
                <div class="token-toggle">
                    <label class="toggle-switch">
                        <input type="checkbox" ${isTracked ? 'checked' : ''}
                               onchange="toggleCustomTokenTracking(${token.id}, this.checked, ${tokenValueNum})">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="token-info">
                    <div class="token-name">${displayName}</div>
                    <div class="token-meta">
                        <span class="token-chain">${token.blockchain.toUpperCase()}</span>
                        ${priceUsd ? `<span class="token-price">${priceUsd}</span>` : ''}
                        ${token.label ? `<span class="token-label">${token.label}</span>` : ''}
                    </div>
                </div>
                <div class="token-values">
                    <div class="token-quantity">${quantity} ${token.ticker || ''}</div>
                    <div class="token-usd">${valueUsd}</div>
                </div>
                <button class="delete-token-btn" onclick="deleteCustomToken(${token.id})" title="Remove token">×</button>
            </div>
        `;
    }

    setSafeHTML(tokensList, tokensHtml);

    // Update portfolio total
    updateTotalPortfolioValue();
}

// Flag to prevent race conditions during custom token toggle
let isTogglingCustomToken = false;

// Toggle custom token tracking for portfolio total with real-time update
async function toggleCustomTokenTracking(tokenId, include, tokenValue) {
    // Prevent concurrent toggles - revert checkbox if blocked
    if (isTogglingCustomToken) {
        // Revert the checkbox since it changed before this handler fired
        const tokenItem = document.querySelector(`.custom-token-item[data-token-id="${tokenId}"]`);
        if (tokenItem) {
            const checkbox = tokenItem.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = !include;
        }
        return;
    }
    isTogglingCustomToken = true;

    // Immediately update visual state
    const tokenItem = document.querySelector(`.custom-token-item[data-token-id="${tokenId}"]`);
    if (tokenItem) {
        tokenItem.classList.toggle('tracked', include);
    }

    // Immediately update customTokensValue for real-time feedback
    const previousCustomValue = customTokensValue;
    if (include) {
        customTokensValue += tokenValue;
    } else {
        customTokensValue -= tokenValue;
    }

    // Update summary display immediately
    const tokensSummary = document.getElementById('customTokensSummary');
    if (tokensSummary) {
        const countSpan = tokensSummary.querySelector('span:first-child');
        const countText = countSpan ? countSpan.outerHTML : '<span>0 tokens</span>';
        setSafeHTML(tokensSummary, `
            ${countText}
            ${customTokensValue > 0 ? `<span class="tracked-value">Tracked: ${formatUSD(customTokensValue)}</span>` : ''}
        `);
    }

    // Update portfolio total immediately
    updateTotalPortfolioValue();

    // Then persist to backend
    try {
        const response = await authFetch(`${API_BASE}/custom-tokens/${tokenId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ include_in_total: include })
        });

        if (!response.ok) {
            console.error('Failed to toggle custom token tracking');
            // Revert visual state on failure
            if (tokenItem) {
                tokenItem.classList.toggle('tracked', !include);
                const checkbox = tokenItem.querySelector('input[type="checkbox"]');
                if (checkbox) checkbox.checked = !include;
            }
            customTokensValue = previousCustomValue;
            updateTotalPortfolioValue();
        }
    } catch (error) {
        console.error('Error toggling custom token tracking:', error);
        // Revert visual state on error
        if (tokenItem) {
            tokenItem.classList.toggle('tracked', !include);
            const checkbox = tokenItem.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = !include;
        }
        customTokensValue = previousCustomValue;
        updateTotalPortfolioValue();
    } finally {
        isTogglingCustomToken = false;
    }
}

// Delete a custom token
async function deleteCustomToken(tokenId) {
    // Check if demo mode
    if (window.isDemoMode && window.isDemoMode()) {
        window.showDemoModeAlert();
        return;
    }

    if (!confirm('Are you sure you want to remove this token?')) {
        return;
    }

    try {
        const response = await authFetch(`${API_BASE}/custom-tokens/${tokenId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            await loadCustomTokens();
            showStatus('Token removed successfully', 'success');
        } else {
            showStatus('Error removing token', 'error');
        }
    } catch (error) {
        console.error('Error deleting token:', error);
        showStatus('Error removing token', 'error');
    }
}

// ============================================================================
// STARTUP STATUS
// ============================================================================

// Check startup status and show loading indicator if services are initializing
async function checkStartupStatus() {
    const indicator = document.getElementById('startupIndicator');
    const message = document.getElementById('startupMessage');

    if (!indicator) return;

    try {
        const response = await authFetch(`${API_BASE}/api/startup-status`);
        const status = await response.json();

        if (status.ready) {
            // All services ready, hide indicator
            indicator.style.display = 'none';
            return true;
        }

        // Show what's loading
        if (status.nft_prices === 'loading') {
            message.textContent = 'Loading NFT floor prices...';
            indicator.style.display = 'flex';
        } else if (status.snapshot_check === 'loading') {
            message.textContent = 'Checking portfolio snapshot...';
            indicator.style.display = 'flex';
        }

        return false;
    } catch (e) {
        // Server might still be starting
        indicator.style.display = 'none';
        return true; // Don't keep polling if there's an error
    }
}

// Poll startup status until ready
async function monitorStartupStatus() {
    let ready = await checkStartupStatus();
    if (!ready) {
        // Poll every 2 seconds until ready
        const interval = setInterval(async () => {
            ready = await checkStartupStatus();
            if (ready) {
                clearInterval(interval);
            }
        }, 2000);
    }
}

// ============================================================================
// DEMO ACCOUNT POPULATION
// ============================================================================

/**
 * Check if this is a demo account and if it needs population.
 * Shows modal with progress if population needed.
 */
async function checkDemoPopulation() {
    // Skip API call for non-demo users
    if (localStorage.getItem('is_demo') !== 'true') return;

    try {
        const response = await authFetch('/api/demo/status');
        if (!response.ok) {
            // Not a demo account or error - just return
            return;
        }

        const data = await response.json();

        if (data.is_populated) {
            // Already populated, nothing to do
            console.log('[Demo] Account already populated');
            return;
        }

        // Show population modal and start streaming progress
        console.log('[Demo] Starting population...');
        await showDemoPopulationModal();

    } catch (error) {
        // Silently fail - not critical for non-demo accounts
        console.debug('[Demo] Not a demo account or error checking status:', error);
    }
}

/**
 * Show demo population modal and stream progress from backend.
 */
async function showDemoPopulationModal() {
    const modal = document.getElementById('demoPopulationModal');
    const progressCircle = document.getElementById('demoProgressCircle');
    const progressPercent = document.getElementById('demoProgressPercent');
    const statusText = document.getElementById('demoStatusText');

    if (!modal) return;

    // Show modal
    modal.classList.remove('hidden');

    // Connect to SSE stream (EventSource can't send headers, pass token as query param)
    const token = localStorage.getItem('abct_token');
    const sseUrl = '/api/demo/populate/stream' + (token ? '?token=' + encodeURIComponent(token) : '');
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            // Update progress circle
            updateDemoProgress(data.progress);

            // Update status text
            statusText.textContent = data.current_step || 'Processing...';

            // Check if complete
            if (data.status === 'completed' || data.progress === 100) {
                console.log('[Demo] Population complete!');
                eventSource.close();

                // Close modal after a brief delay
                setTimeout(() => {
                    modal.classList.add('hidden');
                    // Reload the page to show populated data
                    window.location.reload();
                }, 1500);
            }

            // Check for errors
            if (data.status === 'error') {
                console.error('[Demo] Population error:', data.current_step);
                statusText.textContent = 'Error: ' + data.current_step;
                eventSource.close();

                // Close modal after delay on error
                setTimeout(() => {
                    modal.classList.add('hidden');
                }, 3000);
            }

        } catch (error) {
            console.error('[Demo] Error parsing progress:', error);
        }
    };

    eventSource.onerror = (error) => {
        console.error('[Demo] SSE connection error:', error);
        eventSource.close();
        statusText.textContent = 'Connection error. Please refresh the page.';

        // Close modal after delay
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 3000);
    };
}

/**
 * Update the progress circle based on percentage.
 * @param {number} percent - Progress percentage (0-100)
 */
function updateDemoProgress(percent) {
    const progressCircle = document.getElementById('demoProgressCircle');
    const progressPercent = document.getElementById('demoProgressPercent');

    if (!progressCircle || !progressPercent) return;

    // Update percentage text
    progressPercent.textContent = Math.round(percent) + '%';

    // Update circle stroke-dashoffset
    // Circumference = 2 * PI * radius = 2 * PI * 54 = 339.292
    const circumference = 339.292;
    const offset = circumference - (percent / 100) * circumference;
    progressCircle.style.strokeDashoffset = offset;
}

// ============================================================================
// GLOBAL SEARCH
// ============================================================================

const SEARCH_PAGE_INDEX = [
    { name: 'Dashboard',     url: '/',                       keywords: ['dashboard','overview','portfolio','total','home'] },
    { name: 'Assets',        url: '/assets.html',            keywords: ['assets','tokens','holdings','coins','governance'] },
    { name: 'Wallets',       url: '/data.html',              keywords: ['wallets','addresses','manage'] },
    { name: 'NFTs',          url: '/nfts.html',              keywords: ['nft','nfts','collectibles','gallery'] },
    { name: 'Data & Analytics', url: '/data.html',           keywords: ['data','analytics','transactions','charts','history'] },
    { name: 'Staking/DeFi',  url: '/assets.html#defiTab',   keywords: ['staking','defi','yield','rewards','indigo'] },
    { name: 'Exchanges',     url: '/assets.html#exchangesTab', keywords: ['exchange','binance','coinbase','okx','kucoin','kraken'] },
    { name: 'Settings',      url: '/settings.html',          keywords: ['settings','preferences','configuration'] },
    { name: 'Security',      url: '/settings.html#security', keywords: ['security','password','auth','login'] },
    { name: 'API Keys',      url: '/settings.html#apis',     keywords: ['api','keys','coingecko','moralis','etherscan'] },
    { name: 'Help',          url: '/help.html',              keywords: ['help','guide','faq','documentation'] },
    { name: 'Logs',          url: '/settings.html#logs',     keywords: ['logs','activity','debug'] },
    { name: 'Backup',        url: '/settings.html#backup',   keywords: ['backup','export','import','restore'] },
];

let _searchDebounce = null;
let _searchOpen = false;

function initGlobalSearch() {
    const controls = document.querySelector('.header-right-controls');
    if (!controls) return;

    const container = document.createElement('div');
    container.className = 'global-search-container';
    container.innerHTML = `
        <button class="global-search-btn" id="globalSearchBtn" title="Search (Ctrl+K)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
        </button>
        <div class="global-search-bar" id="globalSearchBar">
            <input type="text" class="global-search-input" id="globalSearchInput"
                   placeholder="Search tokens, wallets, pages..." autocomplete="off" />
            <button class="global-search-close" id="globalSearchClose" title="Close">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
        </div>
        <div class="global-search-results" id="globalSearchResults"></div>
    `;

    const avatar = controls.querySelector('.user-avatar-container');
    if (avatar) {
        controls.insertBefore(container, avatar);
    } else {
        controls.appendChild(container);
    }

    const btn = document.getElementById('globalSearchBtn');
    const bar = document.getElementById('globalSearchBar');
    const input = document.getElementById('globalSearchInput');
    const closeBtn = document.getElementById('globalSearchClose');
    const results = document.getElementById('globalSearchResults');

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openSearch();
    });

    closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeSearch();
    });

    input.addEventListener('input', () => {
        const q = input.value.trim();
        if (q.length < 2) {
            results.classList.remove('visible');
            return;
        }
        clearTimeout(_searchDebounce);
        _searchDebounce = setTimeout(() => runSearch(q), 300);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSearch();
        }
    });

    document.addEventListener('click', (e) => {
        if (_searchOpen && !container.contains(e.target)) {
            closeSearch();
        }
    });

    // Keyboard shortcut: Ctrl/Cmd + K
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (_searchOpen) closeSearch(); else openSearch();
        }
    });

    function openSearch() {
        _searchOpen = true;
        btn.style.display = 'none';
        bar.classList.add('open');
        setTimeout(() => input.focus(), 50);
    }

    function closeSearch() {
        _searchOpen = false;
        bar.classList.remove('open');
        btn.style.display = '';
        results.classList.remove('visible');
        input.value = '';
    }

    function searchResultItem(href, iconHtml, name, sub) {
        return `<a class="search-result-item" href="${href}" data-search-nav="${href}">
            <div class="search-result-icon">${iconHtml}</div>
            <div class="search-result-text">
                <div class="search-result-name">${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(name) : name}</div>
                <div class="search-result-sub">${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(sub) : sub}</div>
            </div>
            <span class="search-result-arrow">&rsaquo;</span>
        </a>`;
    }

    const ICON_TOKEN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v12M6 12h12"/></svg>';
    const ICON_WALLET = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M2 10h20"/><path d="M16 14h2"/></svg>';
    const ICON_DEFI = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>';
    const ICON_STAKING = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M2 12h20"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="10"/></svg>';
    const ICON_EXCHANGE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>';
    const ICON_PAGE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';

    async function runSearch(query) {
        const q = query.toLowerCase();

        // Show spinner
        results.innerHTML = '<div class="search-spinner"></div>';
        results.classList.add('visible');

        // Search pages locally (instant)
        const pageResults = SEARCH_PAGE_INDEX.filter(p =>
            p.name.toLowerCase().includes(q) ||
            p.keywords.some(k => k.includes(q))
        ).slice(0, 3);

        // Search backend (tokens, wallets, defi, staking, exchanges)
        let tokens = [], walletResults = [], defiResults = [], stakingResults = [], exchangeResults = [];
        try {
            const resp = await authFetch(`/search?q=${encodeURIComponent(query)}`);
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

        // Build results HTML
        let html = '';

        if (tokens.length > 0) {
            html += '<div class="search-category-label">Tokens</div>';
            for (const t of tokens) {
                const logoHtml = t.logo_url
                    ? `<img src="${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(t.logo_url) : t.logo_url}" alt="" />`
                    : ICON_TOKEN;
                const val = t.total_value_usd ? `$${Number(t.total_value_usd).toLocaleString(undefined, {maximumFractionDigits: 2})}` : '';
                const sub = (t.blockchain || '') + (val ? ' \u00b7 ' + val : '');
                html += searchResultItem('/assets.html', logoHtml, t.ticker || t.name, sub);
            }
        }

        if (defiResults.length > 0) {
            html += '<div class="search-category-label">DeFi / Governance</div>';
            for (const d of defiResults) {
                const logoHtml = d.logo_url
                    ? `<img src="${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(d.logo_url) : d.logo_url}" alt="" />`
                    : ICON_DEFI;
                const sub = d.protocol + (d.type ? ' \u00b7 ' + d.type : '') + (d.quantity ? ' \u00b7 ' + d.quantity : '');
                html += searchResultItem('/assets.html#defiTab', logoHtml, d.token || d.name, sub);
            }
        }

        if (stakingResults.length > 0) {
            html += '<div class="search-category-label">Staking</div>';
            for (const s of stakingResults) {
                const logoHtml = s.logo_url
                    ? `<img src="${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(s.logo_url) : s.logo_url}" alt="" />`
                    : ICON_STAKING;
                const sub = s.protocol + (s.quantity ? ' \u00b7 ' + s.quantity : '');
                html += searchResultItem('/assets.html#defiTab', logoHtml, s.token || s.name, sub);
            }
        }

        if (exchangeResults.length > 0) {
            html += '<div class="search-category-label">Exchanges</div>';
            for (const ex of exchangeResults) {
                const val = ex.usd_value ? `$${Number(ex.usd_value).toLocaleString(undefined, {maximumFractionDigits: 2})}` : '';
                const sub = ex.exchange + (val ? ' \u00b7 ' + val : '');
                html += searchResultItem('/assets.html#exchangesTab', ICON_EXCHANGE, ex.currency, sub);
            }
        }

        if (walletResults.length > 0) {
            html += '<div class="search-category-label">Wallets</div>';
            for (const w of walletResults) {
                const addr = w.address.length > 20 ? w.address.slice(0, 10) + '...' + w.address.slice(-8) : w.address;
                const sub = w.blockchain + ' \u00b7 ' + addr;
                html += searchResultItem('/data.html', ICON_WALLET, w.label || addr, sub);
            }
        }

        if (pageResults.length > 0) {
            html += '<div class="search-category-label">Pages</div>';
            for (const p of pageResults) {
                html += searchResultItem(p.url, ICON_PAGE, p.name, p.url);
            }
        }

        if (!html) {
            html = '<div class="search-no-results">No results found</div>';
        }

        if (typeof DOMPurify !== 'undefined') {
            results.innerHTML = DOMPurify.sanitize(html, { ADD_ATTR: ['data-search-nav'] });
        } else {
            results.innerHTML = html;
        }

        // Attach click handlers (DOMPurify strips inline handlers)
        results.querySelectorAll('[data-search-nav]').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                const url = el.getAttribute('data-search-nav');
                closeSearch();
                window.location.href = url;
            });
        });

        results.classList.add('visible');
    }
}

// ============================================================================
// ASSET DETAIL MODAL (per-asset chart + enriched token data)
// ============================================================================

let _assetDetailChart = null;
let _assetDetailChartSeries = null;
let _assetDetailResizeObserver = null;
let _assetDetailTimeframe = '7D';
let _assetDetailCurrentSymbol = null;
let _assetDetailCurrentCgId = null;

function openAssetDetail(symbol, cgId, holdingData) {
    const modal = document.getElementById('assetDetailModal');
    if (!modal) return;

    _assetDetailCurrentSymbol = symbol;
    _assetDetailCurrentCgId = cgId || null;
    _assetDetailTimeframe = '7D';

    // Show modal
    modal.classList.remove('hidden');

    // Reset timeframe buttons
    modal.querySelectorAll('.asset-tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tf === '7D');
    });

    // Instant: populate from holdingData (zero latency)
    const logoEl = document.getElementById('assetDetailLogo');
    const nameEl = document.getElementById('assetDetailName');
    const symbolEl = document.getElementById('assetDetailSymbol');
    const priceEl = document.getElementById('assetDetailPrice');
    const changeEl = document.getElementById('assetDetailChange24h');
    if (logoEl) {
        logoEl.src = holdingData.logo_url || getLogoKitUrl(symbol);
        logoEl.alt = symbol;
        logoEl.onerror = function() {
            this.style.display = 'none';
        };
    }
    if (nameEl) nameEl.textContent = holdingData.name || symbol;
    if (symbolEl) symbolEl.textContent = symbol;
    if (priceEl) priceEl.textContent = holdingData.price_usd ? formatUSD(holdingData.price_usd) : '--';

    const change24h = holdingData.price_change_24h || 0;
    if (changeEl) {
        const sign = change24h > 0 ? '+' : '';
        changeEl.textContent = `${sign}${change24h.toFixed(2)}%`;
        changeEl.className = 'asset-detail-change ' + (change24h > 0 ? 'positive' : change24h < 0 ? 'negative' : 'neutral');
    }

    // Reset sections that need API data
    document.getElementById('assetDetailRank').textContent = '';
    document.getElementById('assetDetailMcap').textContent = holdingData.market_cap ? _formatCompactNumber(holdingData.market_cap) : '--';
    document.getElementById('assetDetailVolume').textContent = holdingData.volume_24h ? _formatCompactNumber(holdingData.volume_24h) : '--';
    document.getElementById('assetDetailHigh').textContent = '--';
    document.getElementById('assetDetailLow').textContent = '--';
    document.getElementById('assetDetailSupplySection').style.display = 'none';
    document.getElementById('assetDetailAthAtl').style.display = 'none';
    document.getElementById('assetDetailDescSection').style.display = 'none';

    // Reset change pills
    ['assetChange1h', 'assetChange24h', 'assetChange7d', 'assetChange30d'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.querySelector('.pill-value').textContent = '--';
            el.className = 'change-pill neutral';
        }
    });

    // Init chart after small delay (let modal render)
    setTimeout(() => {
        initAssetDetailChart();
        loadAssetChartData(symbol, cgId, '7D');
    }, 50);

    // Fetch enriched detail in parallel
    fetchAssetDetail(symbol, cgId);
}

function initAssetDetailChart() {
    const container = document.getElementById('assetDetailChart');
    if (!container || !window.LightweightCharts) return;

    destroyAssetDetailChart();

    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
    const colors = getModalPriceChartColors(theme);

    const crosshairOpts2 = { mode: colors.crosshairMode != null ? colors.crosshairMode : LightweightCharts.CrosshairMode.Normal };
    if (colors.crosshairColor) { crosshairOpts2.vertLine = { color: colors.crosshairColor }; crosshairOpts2.horzLine = { color: colors.crosshairColor }; }

    _assetDetailChart = LightweightCharts.createChart(container, {
        layout: {
            background: { color: colors.background },
            textColor: colors.text
        },
        grid: {
            vertLines: { color: colors.gridLines },
            horzLines: { color: colors.gridLines }
        },
        crosshair: crosshairOpts2,
        rightPriceScale: { borderColor: colors.border },
        timeScale: {
            borderColor: colors.border,
            timeVisible: true,
            secondsVisible: false
        },
        width: container.clientWidth,
        height: container.clientHeight
    });

    const seriesOpts2 = { lineColor: colors.lineColor, lineWidth: colors.lineWidth || 2 };
    if (colors.lineStyle != null) seriesOpts2.lineStyle = colors.lineStyle;
    if (colors.lineType != null) seriesOpts2.lineType = colors.lineType;

    if (colors.seriesType === 'line') {
        seriesOpts2.color = colors.lineColor;
        _assetDetailChartSeries = _assetDetailChart.addLineSeries(seriesOpts2);
    } else {
        seriesOpts2.topColor = colors.areaTop;
        seriesOpts2.bottomColor = colors.areaBottom;
        _assetDetailChartSeries = _assetDetailChart.addAreaSeries(seriesOpts2);
    }

    _assetDetailResizeObserver = new ResizeObserver(() => {
        if (_assetDetailChart && container) {
            _assetDetailChart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight
            });
        }
    });
    _assetDetailResizeObserver.observe(container);
}

async function loadAssetChartData(symbol, cgId, timeframe) {
    if (!_assetDetailChartSeries) return;

    const params = new URLSearchParams({ symbol, timeframe });
    if (cgId) params.set('coingecko_id', cgId);

    try {
        const response = await authFetch(`${API_BASE}/portfolio/charts/asset?${params}`);
        if (!response.ok) return;
        const data = await response.json();

        if (data.data && data.data.length > 0) {
            _assetDetailChartSeries.setData(data.data);
            _assetDetailChart.timeScale().fitContent();
        }

        // Update CG ID if resolved by backend
        if (data.coingecko_id && !_assetDetailCurrentCgId) {
            _assetDetailCurrentCgId = data.coingecko_id;
        }
    } catch (e) {
        console.warn('[AssetDetail] Chart data fetch failed:', e);
    }
}

async function fetchAssetDetail(symbol, cgId) {
    const params = new URLSearchParams({ symbol });
    if (cgId) params.set('coingecko_id', cgId);

    try {
        const response = await authFetch(`${API_BASE}/portfolio/asset-detail?${params}`);
        if (!response.ok) return;
        const d = await response.json();

        // Update header with richer data
        if (d.name) document.getElementById('assetDetailName').textContent = d.name;
        if (d.image) {
            const logo = document.getElementById('assetDetailLogo');
            if (logo) { logo.src = d.image; logo.style.display = ''; }
        }
        if (d.market_cap_rank) {
            document.getElementById('assetDetailRank').textContent = `#${d.market_cap_rank}`;
        }
        if (d.current_price) {
            document.getElementById('assetDetailPrice').textContent = formatUSD(d.current_price);
        }

        // Market data
        if (d.market_cap) document.getElementById('assetDetailMcap').textContent = _formatCompactNumber(d.market_cap);
        if (d.total_volume) document.getElementById('assetDetailVolume').textContent = _formatCompactNumber(d.total_volume);
        if (d.high_24h) document.getElementById('assetDetailHigh').textContent = formatUSD(d.high_24h);
        if (d.low_24h) document.getElementById('assetDetailLow').textContent = formatUSD(d.low_24h);

        // Price change pills
        _setChangePill('assetChange1h', d.price_change_1h);
        _setChangePill('assetChange24h', d.price_change_24h);
        _setChangePill('assetChange7d', d.price_change_7d);
        _setChangePill('assetChange30d', d.price_change_30d);

        // Supply
        if (d.circulating_supply || d.total_supply || d.max_supply) {
            document.getElementById('assetDetailSupplySection').style.display = '';
            const circ = d.circulating_supply || 0;
            const max = d.max_supply || d.total_supply || 0;
            const pct = max > 0 ? Math.min((circ / max) * 100, 100) : 0;
            document.getElementById('assetDetailSupplyBar').style.width = pct.toFixed(1) + '%';
            document.getElementById('assetDetailCirculating').textContent = `Circulating: ${_formatCompactNumber(circ, '')}`;
            document.getElementById('assetDetailMaxSupply').textContent = max > 0 ? `Max: ${_formatCompactNumber(max, '')}` : 'Max: ∞';
        }

        // ATH / ATL
        if (d.ath || d.atl) {
            document.getElementById('assetDetailAthAtl').style.display = '';
            document.getElementById('assetDetailAth').textContent = d.ath ? formatUSD(d.ath) : '--';
            document.getElementById('assetDetailAthDate').textContent = d.ath_date ? new Date(d.ath_date).toLocaleDateString() : '';
            const athChange = d.ath_change_pct || 0;
            const athEl = document.getElementById('assetDetailAthChange');
            athEl.textContent = `${athChange > 0 ? '+' : ''}${athChange.toFixed(1)}%`;
            athEl.className = 'ath-atl-change ' + (athChange >= 0 ? 'positive' : 'negative');

            document.getElementById('assetDetailAtl').textContent = d.atl ? formatUSD(d.atl) : '--';
            document.getElementById('assetDetailAtlDate').textContent = d.atl_date ? new Date(d.atl_date).toLocaleDateString() : '';
            const atlChange = d.atl_change_pct || 0;
            const atlEl = document.getElementById('assetDetailAtlChange');
            atlEl.textContent = `+${atlChange.toFixed(1)}%`;
            atlEl.className = 'ath-atl-change positive';
        }

        // Description
        if (d.description) {
            document.getElementById('assetDetailDescSection').style.display = '';
            document.getElementById('assetDetailDesc').textContent = d.description;
        }

    } catch (e) {
        console.warn('[AssetDetail] Detail fetch failed:', e);
    }
}

function _setChangePill(elementId, value) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const val = value || 0;
    const pillValue = el.querySelector('.pill-value');
    if (pillValue) {
        const sign = val > 0 ? '+' : '';
        pillValue.textContent = `${sign}${val.toFixed(2)}%`;
    }
    el.className = 'change-pill ' + (val > 0 ? 'positive' : val < 0 ? 'negative' : 'neutral');
}

function selectAssetTimeframe(tf) {
    if (!_assetDetailCurrentSymbol) return;
    _assetDetailTimeframe = tf;

    // Update button states
    document.querySelectorAll('.asset-tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tf === tf);
    });

    // Re-fetch chart only (detail stays)
    loadAssetChartData(_assetDetailCurrentSymbol, _assetDetailCurrentCgId, tf);
}

function closeAssetDetailModal() {
    const modal = document.getElementById('assetDetailModal');
    if (modal) modal.classList.add('hidden');
    destroyAssetDetailChart();
    _assetDetailCurrentSymbol = null;
    _assetDetailCurrentCgId = null;
}

function destroyAssetDetailChart() {
    if (_assetDetailResizeObserver) {
        _assetDetailResizeObserver.disconnect();
        _assetDetailResizeObserver = null;
    }
    if (_assetDetailChart) {
        _assetDetailChart.remove();
        _assetDetailChart = null;
        _assetDetailChartSeries = null;
    }
}


// ============================================================================
// INITIALIZATION
// ============================================================================

// Initial load
document.addEventListener('DOMContentLoaded', async () => {
    // Load LogoKit token from backend (non-blocking, must be early)
    initLogokitToken();

    // Load saved theme preference
    loadSavedTheme();

    // Initialize privacy mode from localStorage
    initializePrivacyMode();

    // Initialize global search in header
    initGlobalSearch();

    // Show last known portfolio total instantly (before any API calls)
    restoreCachedPortfolioTotal();

    // Check if demo account needs population (non-blocking)
    checkDemoPopulation();

    // Start monitoring startup status (non-blocking)
    monitorStartupStatus();

    // Initialize NFT image cache toggle state (non-blocking — can be slow)
    initImageCacheToggle();

    // Initialize portfolio history chart range buttons
    initHistoryRangeButtons();

    // Initialize holdings column settings button
    const holdingsSettingsBtn = document.getElementById('holdingsSettingsBtn');
    if (holdingsSettingsBtn) {
        holdingsSettingsBtn.addEventListener('click', toggleHoldingsSettings);
        holdingsSettingsBtn._listenerAdded = true;
    }

    // Initialize token form handler
    const tokenForm = document.getElementById('addTokenForm');
    if (tokenForm) {
        tokenForm.addEventListener('submit', handleTokenFormSubmit);
    }

    // Asset Detail Modal event listeners
    const assetDetailOverlay = document.getElementById('assetDetailOverlay');
    if (assetDetailOverlay) assetDetailOverlay.addEventListener('click', closeAssetDetailModal);
    const assetDetailCloseBtn = document.getElementById('assetDetailCloseBtn');
    if (assetDetailCloseBtn) assetDetailCloseBtn.addEventListener('click', closeAssetDetailModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('assetDetailModal');
            if (modal && !modal.classList.contains('hidden')) closeAssetDetailModal();
        }
    });
    document.querySelectorAll('.asset-tf-btn').forEach(btn => {
        btn.addEventListener('click', () => selectAssetTimeframe(btn.dataset.tf));
    });

    // ========================================
    // PAGE-SPECIFIC DATA LOADING
    // ========================================
    const isOverview = !!document.getElementById('totalPortfolioValue');
    const isAssetsPage = !!document.querySelector('.assets-tab-nav');
    const isNftsPage = !!document.querySelector('.nfts-tab-nav');

    if (isOverview) {
        // OVERVIEW PAGE: Load prices + snapshot totals first, then portfolio summary
        try {
            await Promise.all([
                loadPrices(),
                loadPortfolioTotals()  // Must resolve before first updateTotalPortfolioValue()
            ]);
        } catch (e) {
            console.error('[Overview] Failed to load prices/totals:', e);
        }
        try {
            await loadPortfolioSummary();
        } catch (e) {
            console.error('[Overview] Failed to load portfolio summary:', e);
        }

        // Fire chart + holdings immediately (no longer gated by background batch)
        loadV2BalanceHistory('1w');
        loadAllHoldings();

        // Background updates - load exchange data + remaining data
        Promise.allSettled([
            loadExchangeData(),
            loadCustomTokens(),
            loadAllNftSummaries(),
            loadPortfolioAnalytics(true),
            load7DayPortfolioChange(),
            load7DayTransactionCount(),
            loadGlobalMarketCap(),
            loadStakingTotalsForOverview()
        ]).then(() => {
            console.log('[Overview] Background data loading complete');
            initCardanoPriceStream();
            updateTotalPortfolioValue();
            checkV2CollectionStatus();
            preFetchAssetBreakdowns();
        });
    } else if (isAssetsPage) {
        // ASSETS PAGE: Load prices + portfolio summary in parallel, then background updates
        try {
            await Promise.all([
                loadPrices(),
                loadPortfolioSummary()
            ]);
        } catch (e) {
            console.error('[Assets] Failed to load prices/summary:', e);
        }

        // Fire pre-fetch immediately (doesn't depend on exchange/defi data)
        preFetchAssetBreakdowns();

        // Background updates
        Promise.allSettled([
            loadExchangeData(),
            loadDefiGovernance(),
            loadCustomTokens()
        ]).then(() => {
            console.log('[Assets] Data loading complete');
        });
    } else if (isNftsPage) {
        // NFTS PAGE: Load prices, NFT summaries, NFT list, and price coverage in parallel
        await Promise.allSettled([
            loadPrices(),
            loadAllNftSummaries(),
            loadNFTs(),
            loadNFTPriceCoverage()
        ]);
    }
});

// ===========================
// Asset Breakdown Modal
// ===========================
let assetBreakdownChart = null;

// Cache for asset breakdown data - pre-fetched for instant modal opening
const assetBreakdownCache = {
    data: {}, // blockchain -> { assets, timestamp }
    defiLlama: {}, // blockchain -> { mcap, tvl, stablecoins, volume, timestamp }
    ttl: 5 * 60 * 1000, // 5 minutes
    isStale(blockchain, cacheType = 'data') {
        const cache = cacheType === 'data' ? this.data : this.defiLlama;
        const cached = cache[blockchain];
        if (!cached || !cached.timestamp) return true;
        return Date.now() - cached.timestamp > this.ttl;
    },
    get(blockchain, cacheType = 'data') {
        const cache = cacheType === 'data' ? this.data : this.defiLlama;
        return cache[blockchain];
    },
    set(blockchain, value, cacheType = 'data') {
        const cache = cacheType === 'data' ? this.data : this.defiLlama;
        cache[blockchain] = { ...value, timestamp: Date.now() };
    },
    clear() {
        this.data = {};
        this.defiLlama = {};
    }
};

// ========================================
// ALL HOLDINGS OVERVIEW (Overview page)
// ========================================

let _holdingsSortField = 'value_usd';
let _holdingsSortAsc = false;
let _holdingsData = null;

// ========================================
// ALL ASSETS COLUMN CUSTOMIZATION
// ========================================

const HOLDINGS_DEFAULT_COLUMNS = [
    { id: 'name', label: 'Name', sortable: true, fixed: true, visible: true },
    { id: 'amount', label: 'Amount', sortable: true, visible: true },
    { id: 'price_change_24h', label: '24h', sortable: true, visible: true },
    { id: 'sparkline', label: 'Price Graph', sortable: false, visible: true },
    { id: 'price_usd', label: 'Price', sortable: true, visible: true },
    { id: 'value_usd', label: 'Total', sortable: true, visible: true },
    { id: 'market_cap', label: 'MCap', sortable: true, visible: false },
    { id: 'volume_24h', label: '24h Vol', sortable: true, visible: false },
    { id: 'allocation_pct', label: 'Alloc %', sortable: true, visible: false },
];

let _holdingsColumnConfig = null;
let _holdingsSettingsPanel = null;

function getHoldingsColumnConfig() {
    if (!_holdingsColumnConfig) {
        try {
            const saved = localStorage.getItem('holdingsColumnConfig');
            if (saved) {
                const parsed = JSON.parse(saved);
                // Merge with defaults to handle new columns added in updates
                const savedIds = new Set(parsed.map(c => c.id));
                const merged = [...parsed];
                for (const def of HOLDINGS_DEFAULT_COLUMNS) {
                    if (!savedIds.has(def.id)) merged.push({...def});
                }
                // Ensure fixed columns retain their properties
                for (const col of merged) {
                    const def = HOLDINGS_DEFAULT_COLUMNS.find(d => d.id === col.id);
                    if (def) {
                        col.sortable = def.sortable;
                        col.fixed = def.fixed || false;
                        if (col.fixed) col.visible = true;
                    }
                }
                _holdingsColumnConfig = merged;
            }
        } catch (e) { /* ignore corrupt localStorage */ }
        if (!_holdingsColumnConfig) {
            _holdingsColumnConfig = HOLDINGS_DEFAULT_COLUMNS.map(c => ({...c}));
        }
    }
    return _holdingsColumnConfig;
}

function saveHoldingsColumnConfig() {
    localStorage.setItem('holdingsColumnConfig', JSON.stringify(_holdingsColumnConfig));
}

function _formatCompactNumber(n, prefix = '$') {
    if (!n || n === 0) return '--';
    if (n >= 1e12) return prefix + (n / 1e12).toFixed(2) + 'T';
    if (n >= 1e9) return prefix + (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return prefix + (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return prefix + (n / 1e3).toFixed(1) + 'K';
    return prefix + n.toFixed(2);
}

function _holdingCellHtml(colId, h) {
    const symbol = h.symbol || '?';
    const name = h.name || symbol;
    const letter = symbol.charAt(0).toUpperCase();

    switch (colId) {
        case 'name': {
            const logoUrl = h.logo_url || getLogoKitUrl(symbol);
            const logoHtml = logoUrl
                ? `<img src="${logoUrl}" alt="${symbol}" class="holding-logo" data-fallback="${letter}">`
                : `<div class="holding-logo-fallback">${letter}</div>`;
            return `<td><div class="holding-name-cell">${logoHtml}<div class="holding-name-text"><span class="holding-ticker">${symbol}</span><span class="holding-full-name">${name}</span></div></div></td>`;
        }
        case 'amount': {
            const amount = h.amount || 0;
            let amountStr;
            if (amount >= 1000000) amountStr = (amount / 1000000).toFixed(2) + 'M';
            else if (amount >= 10000) amountStr = amount.toLocaleString('en-US', { maximumFractionDigits: 2 });
            else if (amount >= 1) amountStr = amount.toLocaleString('en-US', { maximumFractionDigits: 4 });
            else amountStr = amount.toLocaleString('en-US', { maximumFractionDigits: 6 });
            return `<td class="text-right"><span class="holding-amount">${blurValue(amountStr)}</span></td>`;
        }
        case 'price_change_24h': {
            const change = h.price_change_24h || 0;
            const changeClass = change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral';
            const changeSign = change > 0 ? '+' : '';
            return `<td class="text-right"><span class="holding-change ${changeClass}">${changeSign}${change.toFixed(2)}%</span></td>`;
        }
        case 'sparkline':
            return `<td><div class="holding-sparkline-slot" data-symbol="${symbol}"></div></td>`;
        case 'price_usd': {
            const price = h.price_usd || 0;
            let priceStr;
            if (price >= 1) priceStr = '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            else if (price >= 0.01) priceStr = '$' + price.toFixed(4);
            else if (price > 0) priceStr = '$' + price.toFixed(6);
            else priceStr = '--';
            return `<td class="text-right"><span class="holding-price">${blurValue(priceStr)}</span></td>`;
        }
        case 'value_usd':
            return `<td class="text-right"><span class="holding-total">${blurValue(formatUSD(h.value_usd || 0))}</span></td>`;
        case 'market_cap':
            return `<td class="text-right">${_formatCompactNumber(h.market_cap)}</td>`;
        case 'volume_24h':
            return `<td class="text-right">${_formatCompactNumber(h.volume_24h)}</td>`;
        case 'allocation_pct': {
            const pct = h.allocation_pct || 0;
            return `<td class="text-right">${pct > 0 ? pct.toFixed(2) + '%' : '--'}</td>`;
        }
        default:
            return '<td>--</td>';
    }
}

// Settings panel (created programmatically to avoid DOMPurify issues)
function toggleHoldingsSettings() {
    if (_holdingsSettingsPanel) {
        _holdingsSettingsPanel.remove();
        _holdingsSettingsPanel = null;
        return;
    }
    const btn = document.getElementById('holdingsSettingsBtn');
    if (!btn) return;
    _holdingsSettingsPanel = _createHoldingsSettingsPanel();
    btn.parentElement.appendChild(_holdingsSettingsPanel);

    // Close on outside click
    const closeHandler = (e) => {
        if (_holdingsSettingsPanel && !_holdingsSettingsPanel.contains(e.target) && e.target !== btn) {
            _holdingsSettingsPanel.remove();
            _holdingsSettingsPanel = null;
            document.removeEventListener('click', closeHandler);
        }
    };
    setTimeout(() => document.addEventListener('click', closeHandler), 0);
}

function _createHoldingsSettingsPanel() {
    const config = getHoldingsColumnConfig();
    const panel = document.createElement('div');
    panel.className = 'column-settings-panel';

    const title = document.createElement('div');
    title.className = 'column-settings-title';
    title.textContent = 'Columns';
    panel.appendChild(title);

    const list = document.createElement('div');
    list.className = 'column-settings-list';

    let dragSrcEl = null;

    config.forEach((col, idx) => {
        const item = document.createElement('div');
        item.className = 'column-settings-item';
        item.draggable = !col.fixed;
        item.dataset.colIdx = idx;

        // Drag handle
        const handle = document.createElement('span');
        handle.className = 'column-drag-handle';
        handle.textContent = col.fixed ? '' : '⠿';
        item.appendChild(handle);

        // Checkbox
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = col.visible;
        cb.disabled = col.fixed;
        cb.addEventListener('change', () => {
            col.visible = cb.checked;
            saveHoldingsColumnConfig();
            _rerenderHoldings();
        });
        item.appendChild(cb);

        // Label
        const label = document.createElement('span');
        label.className = 'column-settings-label';
        label.textContent = col.label;
        item.appendChild(label);

        // Drag events (only for non-fixed columns)
        if (!col.fixed) {
            item.addEventListener('dragstart', (e) => {
                dragSrcEl = item;
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                const target = e.currentTarget;
                if (target !== dragSrcEl && !config[target.dataset.colIdx]?.fixed) {
                    target.classList.add('drag-over');
                }
            });
            item.addEventListener('dragleave', (e) => {
                e.currentTarget.classList.remove('drag-over');
            });
            item.addEventListener('drop', (e) => {
                e.preventDefault();
                e.currentTarget.classList.remove('drag-over');
                if (dragSrcEl === item) return;
                const fromIdx = parseInt(dragSrcEl.dataset.colIdx);
                const toIdx = parseInt(item.dataset.colIdx);
                if (config[toIdx]?.fixed) return;
                // Reorder config array
                const [moved] = _holdingsColumnConfig.splice(fromIdx, 1);
                _holdingsColumnConfig.splice(toIdx, 0, moved);
                saveHoldingsColumnConfig();
                // Rebuild the panel and re-render table
                const parent = panel.parentElement;
                panel.remove();
                _holdingsSettingsPanel = _createHoldingsSettingsPanel();
                parent.appendChild(_holdingsSettingsPanel);
                _rerenderHoldings();
            });
            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                list.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
            });
        }

        list.appendChild(item);
    });

    panel.appendChild(list);

    // Reset button
    const resetBtn = document.createElement('button');
    resetBtn.className = 'column-settings-reset';
    resetBtn.textContent = 'Reset to defaults';
    resetBtn.addEventListener('click', () => {
        _holdingsColumnConfig = HOLDINGS_DEFAULT_COLUMNS.map(c => ({...c}));
        saveHoldingsColumnConfig();
        const parent = panel.parentElement;
        panel.remove();
        _holdingsSettingsPanel = _createHoldingsSettingsPanel();
        parent.appendChild(_holdingsSettingsPanel);
        _rerenderHoldings();
    });
    panel.appendChild(resetBtn);

    return panel;
}

function _rerenderHoldings() {
    if (!_holdingsData) return;
    const body = document.getElementById('holdingsOverviewBody');
    if (body) renderAllHoldings(_holdingsData.holdings, body);
}

async function loadAllHoldings() {
    const section = document.getElementById('holdingsOverviewSection');
    if (!section) return;

    const body = document.getElementById('holdingsOverviewBody');
    const loading = document.getElementById('holdingsLoading');

    // Attach settings button handler
    const settingsBtn = document.getElementById('holdingsSettingsBtn');
    if (settingsBtn && !settingsBtn._listenerAdded) {
        settingsBtn.addEventListener('click', toggleHoldingsSettings);
        settingsBtn._listenerAdded = true;
    }

    try {
        if (loading) loading.style.display = 'flex';
        const response = await authFetch(`${API_BASE}/portfolio/all-holdings`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        _holdingsData = data;

        // Show toggle if there are any zero-balance holdings
        const hasZero = data.holdings.some(h => (h.value_usd || 0) <= 0);
        const toggleWrap = document.getElementById('zeroBalanceToggle');
        if (toggleWrap) toggleWrap.style.display = hasZero ? '' : 'none';

        const checkbox = document.getElementById('showZeroBalances');
        if (checkbox && !checkbox._holdingsListenerAdded) {
            checkbox.addEventListener('change', () => renderAllHoldings(_holdingsData.holdings, body));
            checkbox._holdingsListenerAdded = true;
        }

        renderAllHoldings(data.holdings, body);
    } catch (e) {
        console.error('[Holdings] Failed to load all holdings:', e);
        if (body) {
            setSafeHTML(body, '<p style="text-align:center;color:var(--text-secondary);padding:20px 0;">Failed to load assets.</p>');
        }
    }
}

function renderAllHoldings(holdings, container) {
    if (!holdings || holdings.length === 0) {
        setSafeHTML(container, '<p style="text-align:center;color:var(--text-secondary);padding:20px 0;">No assets found.</p>');
        return;
    }

    // Filter out zero-balance holdings unless toggle is checked
    const showZero = document.getElementById('showZeroBalances')?.checked || false;
    const filtered = showZero ? holdings : holdings.filter(h => (h.value_usd || 0) > 0);

    if (filtered.length === 0) {
        setSafeHTML(container, '<p style="text-align:center;color:var(--text-secondary);padding:20px 0;">No assets with value found.</p>');
        return;
    }

    // Get visible columns from config
    const columns = getHoldingsColumnConfig().filter(c => c.visible);

    // Sort
    const sorted = [...filtered].sort((a, b) => {
        let va, vb;
        switch (_holdingsSortField) {
            case 'name':
                va = (a.symbol || '').toLowerCase();
                vb = (b.symbol || '').toLowerCase();
                return _holdingsSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
            case 'amount': va = a.amount || 0; vb = b.amount || 0; break;
            case 'price_change_24h': va = a.price_change_24h || 0; vb = b.price_change_24h || 0; break;
            case 'price_usd': va = a.price_usd || 0; vb = b.price_usd || 0; break;
            case 'market_cap': va = a.market_cap || 0; vb = b.market_cap || 0; break;
            case 'volume_24h': va = a.volume_24h || 0; vb = b.volume_24h || 0; break;
            case 'allocation_pct': va = a.allocation_pct || 0; vb = b.allocation_pct || 0; break;
            case 'value_usd': default: va = a.value_usd || 0; vb = b.value_usd || 0; break;
        }
        return _holdingsSortAsc ? va - vb : vb - va;
    });

    const arrow = (field) => {
        if (_holdingsSortField !== field) return '<span class="sort-arrow"></span>';
        return `<span class="sort-arrow">${_holdingsSortAsc ? '▲' : '▼'}</span>`;
    };
    const cls = (field) => _holdingsSortField === field ? 'sorted' : '';

    // Build header from column config (with drag handles for reorder)
    let headerHtml = '';
    for (let ci = 0; ci < columns.length; ci++) {
        const col = columns[ci];
        const align = col.id === 'name' ? '' : 'text-right';
        const sortAttr = col.sortable ? `data-sort="${col.id}"` : 'data-sort=""';
        const sortCls = col.sortable ? cls(col.id) : '';
        const sortArrow = col.sortable ? ' ' + arrow(col.id) : '';
        const dragHandle = col.fixed ? '' : `<span class="th-drag-handle" data-col-idx="${ci}" draggable="true" title="Drag to reorder">⠿</span>`;
        headerHtml += `<th class="${`${align} ${sortCls}`.trim()}" ${sortAttr} data-col-id="${col.id}">${col.label}${sortArrow}${dragHandle}</th>`;
    }

    let html = `
        <div class="assets-table-wrapper">
            <table class="holdings-overview-table">
                <thead><tr>${headerHtml}</tr></thead>
                <tbody>`;

    // Build rows from column config
    for (const h of sorted) {
        const sym = h.symbol || '';
        const cgId = h.coingecko_id || '';
        html += `<tr data-symbol="${sym}" data-cg-id="${cgId}">`;
        for (const col of columns) {
            html += _holdingCellHtml(col.id, h);
        }
        html += '</tr>';
    }

    html += '</tbody></table></div>';

    setSafeHTML(container, html);

    // Post-render: attach image error handlers (DOMPurify strips onerror)
    container.querySelectorAll('img.holding-logo[data-fallback]').forEach(img => {
        img.addEventListener('error', () => {
            const letter = img.getAttribute('data-fallback') || '?';
            const fallback = document.createElement('div');
            fallback.className = 'holding-logo-fallback';
            fallback.textContent = letter;
            img.replaceWith(fallback);
        });
    });

    // Post-render: attach sort header click handlers
    container.querySelectorAll('.holdings-overview-table th[data-sort]').forEach(th => {
        const field = th.getAttribute('data-sort');
        if (!field) return;
        th.addEventListener('click', (e) => {
            // Don't sort when clicking the drag handle
            if (e.target.classList.contains('th-drag-handle')) return;
            if (_holdingsSortField === field) {
                _holdingsSortAsc = !_holdingsSortAsc;
            } else {
                _holdingsSortField = field;
                _holdingsSortAsc = field === 'name'; // A-Z default for name
            }
            renderAllHoldings(_holdingsData.holdings, container);
        });
    });

    // Post-render: attach column drag handles for reordering
    let _dragColIdx = null;
    container.querySelectorAll('.th-drag-handle').forEach(handle => {
        handle.addEventListener('dragstart', (e) => {
            _dragColIdx = parseInt(handle.dataset.colIdx);
            e.dataTransfer.effectAllowed = 'move';
            handle.closest('th').classList.add('col-dragging');
        });
        handle.addEventListener('dragend', () => {
            _dragColIdx = null;
            container.querySelectorAll('.col-dragging, .col-drag-over').forEach(el => {
                el.classList.remove('col-dragging', 'col-drag-over');
            });
        });
    });
    container.querySelectorAll('.holdings-overview-table th[data-col-id]').forEach(th => {
        th.addEventListener('dragover', (e) => {
            if (_dragColIdx === null) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            th.classList.add('col-drag-over');
        });
        th.addEventListener('dragleave', () => th.classList.remove('col-drag-over'));
        th.addEventListener('drop', (e) => {
            e.preventDefault();
            th.classList.remove('col-drag-over');
            if (_dragColIdx === null) return;
            const config = getHoldingsColumnConfig();
            const visibleCols = config.filter(c => c.visible);
            const targetColId = th.dataset.colId;
            const targetCol = visibleCols.find(c => c.id === targetColId);
            if (!targetCol || targetCol.fixed) return;
            const fromCol = visibleCols[_dragColIdx];
            if (!fromCol || fromCol.fixed) return;
            // Find indices in full config array
            const fromFullIdx = config.indexOf(fromCol);
            const toFullIdx = config.indexOf(targetCol);
            if (fromFullIdx === toFullIdx) return;
            config.splice(fromFullIdx, 1);
            config.splice(toFullIdx, 0, fromCol);
            saveHoldingsColumnConfig();
            renderAllHoldings(_holdingsData.holdings, container);
        });
    });

    // Post-render: draw sparklines
    drawAllSparklines(sorted, container);

    // Post-render: attach row click handlers for asset detail modal
    container.querySelectorAll('.holdings-overview-table tbody tr[data-symbol]').forEach(tr => {
        tr.addEventListener('click', (e) => {
            // Don't open modal when clicking links or buttons
            if (e.target.closest('a, button')) return;
            const sym = tr.dataset.symbol;
            const cgId = tr.dataset.cgId || null;
            const holding = sorted.find(h => h.symbol === sym);
            if (holding) openAssetDetail(sym, cgId, holding);
        });
    });
}

function drawAllSparklines(holdings, container) {
    for (const h of holdings) {
        const sparkline = h.sparkline_7d;
        if (!sparkline || sparkline.length < 2) continue;

        const slot = container.querySelector(`.holding-sparkline-slot[data-symbol="${h.symbol}"]`);
        if (!slot) continue;

        // Create canvas dynamically (DOMPurify strips <canvas>)
        const canvas = document.createElement('canvas');
        canvas.className = 'holding-sparkline';
        slot.replaceWith(canvas);

        // Need a frame for offsetWidth/Height to resolve
        requestAnimationFrame(() => {
            const dpr = window.devicePixelRatio || 1;
            const cw = canvas.offsetWidth || 100;
            const ch = canvas.offsetHeight || 32;
            canvas.width = cw * dpr;
            canvas.height = ch * dpr;

            const ctx = canvas.getContext('2d');
            ctx.scale(dpr, dpr);

            const min = Math.min(...sparkline);
            const max = Math.max(...sparkline);
            const range = max - min || 1;

            const up = sparkline[sparkline.length - 1] >= sparkline[0];
            ctx.strokeStyle = up ? '#27ae60' : '#e74c3c';
            ctx.lineWidth = 1.5;
            ctx.lineJoin = 'round';

            ctx.beginPath();
            for (let i = 0; i < sparkline.length; i++) {
                const x = (i / (sparkline.length - 1)) * cw;
                const y = ch - ((sparkline[i] - min) / range) * (ch - 4) - 2;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        });
    }
}

// Pre-fetch all blockchain breakdowns for instant modal opening
async function preFetchAssetBreakdowns() {
    console.log('Pre-fetching asset breakdowns for all blockchains...');

    const blockchains = ['cardano', 'ethereum', 'bitcoin', 'solana', 'polygon', 'base'];

    // Fetch all in parallel
    const promises = blockchains.map(async (blockchain) => {
        try {
            // Fetch asset data
            const response = await authFetch(`${API_BASE}/portfolio/assets/${blockchain}`);
            if (response.ok) {
                const data = await response.json();
                assetBreakdownCache.set(blockchain, data, 'data');
                console.log(`✓ Cached breakdown for ${blockchain}`);
            }

            // Fetch DeFillama metrics
            const metrics = await fetchDeFiLlamaMetrics(blockchain);
            if (metrics) {
                assetBreakdownCache.set(blockchain, metrics, 'defiLlama');
            }
        } catch (error) {
            console.warn(`Failed to pre-fetch ${blockchain}:`, error);
        }
    });

    await Promise.all(promises);
    console.log('Asset breakdown pre-fetching complete');
}

// DeFillama API Integration (proxied through backend)
async function fetchDeFiLlamaMetrics(blockchain) {
    try {
        // Check cache first
        const cached = assetBreakdownCache.get(blockchain, 'defiLlama');
        if (cached && !assetBreakdownCache.isStale(blockchain, 'defiLlama')) {
            return cached;
        }

        let mcap = null, tvl = null, stablecoins = null, volume = null;

        // Use market cap from backend price data (loaded via /prices/all endpoint)
        const blockchainToSymbol = {
            'cardano': 'ADA',
            'ethereum': 'ETH',
            'bitcoin': 'BTC',
            'solana': 'SOL',
            'polygon': 'MATIC',
            'base': 'ETH'
        };

        const priceSymbol = blockchainToSymbol[blockchain];
        if (priceSymbol && priceData[priceSymbol] && priceData[priceSymbol].market_cap) {
            mcap = priceData[priceSymbol].market_cap;
        }

        // Fetch TVL, stablecoin supply, and DEX volume from backend proxy
        try {
            const resp = await authFetch(`/analytics/chain-breakdown/${encodeURIComponent(blockchain)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.success) {
                tvl = data.tvl || null;
                volume = data.dex_volume_24h || null;
                if (blockchain === 'bitcoin') {
                    stablecoins = 'N/A';
                } else {
                    stablecoins = data.stablecoin_supply > 0 ? data.stablecoin_supply : null;
                }
            }
        } catch (e) {
            console.error('Backend chain breakdown error:', e);
        }

        return { mcap, tvl, stablecoins, volume };
    } catch (error) {
        console.error('Error fetching DeFillama metrics:', error);
        return null;
    }
}

function updateDeFiLlamaMetrics(metrics) {
    const mcapEl = document.getElementById('chainMcap');
    const tvlEl = document.getElementById('chainTvl');
    const stablesEl = document.getElementById('chainStables');
    const volumeEl = document.getElementById('chainVolume');

    if (!metrics) {
        mcapEl.textContent = 'Loading...';
        tvlEl.textContent = 'Loading...';
        stablesEl.textContent = 'Loading...';
        volumeEl.textContent = 'Loading...';
        return;
    }

    // Handle each metric - use N/A for explicitly unavailable data, show value or N/A for null
    mcapEl.textContent = metrics.mcap === 'N/A' ? 'N/A' : (metrics.mcap ? formatCompactUSD(metrics.mcap) : 'N/A');
    tvlEl.textContent = metrics.tvl === 'N/A' ? 'N/A' : (metrics.tvl ? formatCompactUSD(metrics.tvl) : 'N/A');
    stablesEl.textContent = metrics.stablecoins === 'N/A' ? 'N/A' : (metrics.stablecoins ? formatCompactUSD(metrics.stablecoins) : 'N/A');
    volumeEl.textContent = metrics.volume === 'N/A' ? 'N/A' : (metrics.volume ? formatCompactUSD(metrics.volume) : 'N/A');
}

function formatCompactUSD(value) {
    if (!value || value === 0 || value === 'N/A') return 'N/A';

    const numValue = parseFloat(value);
    if (isNaN(numValue)) return 'N/A';

    if (numValue >= 1e12) {
        return '$' + (numValue / 1e12).toFixed(2) + 'T';
    } else if (numValue >= 1e9) {
        return '$' + (numValue / 1e9).toFixed(2) + 'B';
    } else if (numValue >= 1e6) {
        return '$' + (numValue / 1e6).toFixed(2) + 'M';
    } else if (numValue >= 1e3) {
        return '$' + (numValue / 1e3).toFixed(2) + 'K';
    } else {
        return formatUSD(numValue);
    }
}

function formatLargeNumber(value) {
    if (!value || value === 0) return '-';
    const num = parseFloat(value);
    if (isNaN(num)) return '-';
    if (num >= 1e12) return (num / 1e12).toFixed(2) + 'T';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toLocaleString();
}

// Helper function to render breakdown data (used for both cached and fresh data)
function renderBreakdownData(data) {
    const totalValue = document.getElementById('breakdownTotalValue');
    const assetCount = document.getElementById('breakdownAssetCount');

    // Get blockchain from current modal title (a bit hacky but works)
    const chainName = document.getElementById('breakdownChainName').textContent;
    const blockchain = chainName.split(' ')[0].toLowerCase();

    // Update values
    totalValue.textContent = formatUSD(data.total_value_usd);
    assetCount.textContent = 1 + data.tokens.length + (data.nfts.count > 0 ? 1 : 0);

    const labels = [];
    const values = [];
    const colors = [];
    const legendItems = [];

    // Add native coin
    if (data.native_coin.value_usd > 0) {
        labels.push(data.native_coin.symbol);
        values.push(data.native_coin.value_usd);
        colors.push(getBlockchainColor(blockchain));
        legendItems.push({
            color: getBlockchainColor(blockchain),
            symbol: data.native_coin.symbol,
            name: 'Native Coin',
            value_usd: data.native_coin.value_usd,
            percentage: data.native_coin.percentage
        });
    }

    // Add tokens
    data.tokens.forEach((token, idx) => {
        if (token.value_usd > 0) {
            labels.push(token.symbol);
            values.push(token.value_usd);
            colors.push(generateColorForToken(idx));
            legendItems.push({
                color: generateColorForToken(idx),
                symbol: token.symbol,
                name: token.name,
                value_usd: token.value_usd,
                percentage: token.percentage,
                logo_url: token.logo_url || null
            });
        }
    });

    // Add NFTs
    if (data.nfts.count > 0 && data.nfts.value_usd > 0) {
        labels.push('NFTs');
        values.push(data.nfts.value_usd);
        colors.push('#9B59B6');
        legendItems.push({
            color: '#9B59B6',
            symbol: 'NFTs',
            name: `${data.nfts.count} NFTs`,
            value_usd: data.nfts.value_usd,
            percentage: data.nfts.percentage
        });
    }

    renderAssetBreakdownChart(labels, values, colors);
    renderBreakdownLegend(legendItems);

    // Populate supply metrics if available
    const supplyRow = document.getElementById('supplyMetricsRow');
    if (supplyRow && data.supply && (data.supply.circulating_supply || data.supply.total_supply || data.supply.max_supply)) {
        document.getElementById('supplyCirculating').textContent = formatLargeNumber(data.supply.circulating_supply);
        document.getElementById('supplyTotal').textContent = formatLargeNumber(data.supply.total_supply);
        document.getElementById('supplyMax').textContent = data.supply.max_supply ? formatLargeNumber(data.supply.max_supply) : 'No Cap';
        supplyRow.classList.remove('hidden');
    } else if (supplyRow) {
        supplyRow.classList.add('hidden');
    }
}

async function openAssetBreakdown(blockchain) {
    try {
        // Open modal immediately
        const modal = document.getElementById('assetBreakdownModal');
        const chainName = document.getElementById('breakdownChainName');
        const totalValue = document.getElementById('breakdownTotalValue');
        const assetCount = document.getElementById('breakdownAssetCount');
        const legendDiv = document.getElementById('breakdownLegend');

        modal.classList.remove('hidden');
        chainName.textContent = `${blockchain.charAt(0).toUpperCase() + blockchain.slice(1)} Asset Breakdown`;

        // Clear any existing doughnut chart
        if (assetBreakdownChart) {
            assetBreakdownChart.destroy();
            assetBreakdownChart = null;
        }

        // Initialize modal price chart (slight delay for container to become visible)
        setTimeout(() => initModalPriceChart(blockchain), 50);

        // Check cache for instant display
        const cachedData = assetBreakdownCache.get(blockchain, 'data');
        const cachedMetrics = assetBreakdownCache.get(blockchain, 'defiLlama');
        const hasCache = cachedData && !assetBreakdownCache.isStale(blockchain, 'data');

        if (hasCache) {
            renderBreakdownData(cachedData);

            // Show cached DeFillama metrics if available
            if (cachedMetrics && !assetBreakdownCache.isStale(blockchain, 'defiLlama')) {
                updateDeFiLlamaMetrics(cachedMetrics);
            } else {
                // Fetch fresh metrics in background
                updateDeFiLlamaMetrics(null);
                fetchDeFiLlamaMetrics(blockchain).then(metrics => {
                    if (metrics) {
                        assetBreakdownCache.set(blockchain, metrics, 'defiLlama');
                        updateDeFiLlamaMetrics(metrics);
                    }
                });
            }

            // Don't fetch fresh data - cache is good
            return;
        }

        // No cache or stale - show loading state
        totalValue.textContent = 'Loading...';
        assetCount.textContent = '...';
        legendDiv.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-secondary);">Loading asset data...</div>';
        updateDeFiLlamaMetrics(null);

        // Fetch DeFillama metrics in parallel
        fetchDeFiLlamaMetrics(blockchain).then(metrics => {
            if (metrics) {
                assetBreakdownCache.set(blockchain, metrics, 'defiLlama');
                updateDeFiLlamaMetrics(metrics);
            }
        });

        // Fetch fresh data
        const response = await authFetch(`${API_BASE}/portfolio/assets/${blockchain}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();

        // Cache the fresh data
        assetBreakdownCache.set(blockchain, data, 'data');

        // Render the data
        renderBreakdownData(data);

    } catch (error) {
        console.error('Error loading asset breakdown:', error);

        // Show error in modal instead of closing it
        legendDiv.innerHTML = `
            <div style="text-align: center; padding: 20px; color: #dc3545;">
                <h3>Error Loading Asset Breakdown</h3>
                <p>${error.message || 'Unknown error occurred'}</p>
                <button onclick="closeAssetBreakdownModal()" style="margin-top: 15px; padding: 8px 16px; background: var(--accent-color); border: none; border-radius: 4px; color: white; cursor: pointer;">Close</button>
            </div>
        `;
        totalValue.textContent = 'Error';
        assetCount.textContent = '-';
    }
}

function renderAssetBreakdownChart(labels, values, colors) {
    const ctx = document.getElementById('assetBreakdownChart').getContext('2d');
    if (assetBreakdownChart) assetBreakdownChart.destroy();

    assetBreakdownChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 3,
                borderColor: getComputedStyle(document.body).getPropertyValue('--bg-primary'),
                hoverBorderWidth: 1,
                hoverBorderColor: '#00d26a',
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(26, 26, 46, 0.95)',
                    titleColor: '#e0e0e0',
                    bodyColor: '#e0e0e0',
                    borderColor: 'rgba(0, 210, 106, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${context.label}: ${formatUSD(context.parsed)} (${percentage}%)`;
                        }
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    selectBreakdownSegment(index);
                }
            },
            onHover: (event, elements) => {
                event.native.target.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            }
        }
    });
}

function renderBreakdownLegend(items) {
    const legendDiv = document.getElementById('breakdownLegend');

    // Render compact legend items matching slider 2 style
    legendDiv.innerHTML = items.map((item, index) => {
        const logoHtml = item.logo_url
            ? `<img src="${item.logo_url}" alt="${item.symbol}" class="breakdown-token-logo" onerror="this.style.display='none';">`
            : '';

        return `
            <div class="breakdown-legend-item-compact" data-index="${index}" onclick="selectBreakdownSegment(${index})">
                ${logoHtml}
                <div class="breakdown-legend-info">
                    <div class="breakdown-legend-symbol">${item.symbol}</div>
                    <div class="breakdown-legend-value">${formatUSD(item.value_usd)}</div>
                </div>
                <div class="breakdown-legend-percentage">${item.percentage.toFixed(1)}%</div>
            </div>
        `;
    }).join('');

    // Store items for selection
    window.breakdownLegendItems = items;
}

// Handle segment selection for breakdown chart
function selectBreakdownSegment(index) {
    const items = window.breakdownLegendItems;
    if (!items || !items[index]) return;

    // Highlight selected legend item
    document.querySelectorAll('.breakdown-legend-item-compact').forEach((el, i) => {
        if (i === index) {
            el.classList.add('selected');
        } else {
            el.classList.remove('selected');
        }
    });

    // Highlight chart segment
    if (assetBreakdownChart) {
        assetBreakdownChart.setActiveElements([{ datasetIndex: 0, index: index }]);
        assetBreakdownChart.update();
    }
}

function getBlockchainColor(blockchain) {
    const colors = {
        'cardano': '#0033AD', 'bitcoin': '#F7931A', 'ethereum': '#627EEA',
        'solana': '#14F195', 'polygon': '#8247E5', 'base': '#0052FF'
    };
    return colors[blockchain] || '#888888';
}

function generateColorForToken(index) {
    const palette = [
        '#3498DB', '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C',
        '#E67E22', '#95A5A6', '#34495E', '#16A085', '#27AE60', '#2980B9',
        '#8E44AD', '#F1C40F', '#E84393', '#00B894'
    ];
    return palette[index % palette.length];
}

function closeAssetBreakdownModal() {
    document.getElementById('assetBreakdownModal').classList.add('hidden');

    // Clear selected legend items
    document.querySelectorAll('.breakdown-legend-item-compact').forEach(el => {
        el.classList.remove('selected');
    });

    // Destroy doughnut chart
    if (assetBreakdownChart) {
        assetBreakdownChart.destroy();
        assetBreakdownChart = null;
    }

    // Destroy modal price chart
    destroyModalPriceChart();
}

// ============================================================================
// Modal Price Chart (TradingView Lightweight Charts inside Asset Breakdown Modal)
// ============================================================================

let modalPriceChart = null;
let modalPriceChartSeries = null;
let modalPriceChartBlockchain = null;
let modalPriceChartTimeframe = '1D';
let modalPriceChartResizeObserver = null;

function initModalPriceChart(blockchain) {
    const container = document.getElementById('modalPriceChart');
    if (!container || !window.LightweightCharts) {
        console.warn('Modal price chart container or LightweightCharts not available');
        return;
    }

    // Destroy any existing instance
    destroyModalPriceChart();

    modalPriceChartBlockchain = blockchain;
    modalPriceChartTimeframe = '1D';

    // Reset timeframe button states
    document.querySelectorAll('.modal-tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tf === '1D');
    });

    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
    const colors = getModalPriceChartColors(theme);

    const crosshairOpts3 = { mode: colors.crosshairMode != null ? colors.crosshairMode : LightweightCharts.CrosshairMode.Normal };
    if (colors.crosshairColor) { crosshairOpts3.vertLine = { color: colors.crosshairColor }; crosshairOpts3.horzLine = { color: colors.crosshairColor }; }

    modalPriceChart = LightweightCharts.createChart(container, {
        layout: {
            background: { color: colors.background },
            textColor: colors.text
        },
        grid: {
            vertLines: { color: colors.gridLines },
            horzLines: { color: colors.gridLines }
        },
        crosshair: crosshairOpts3,
        rightPriceScale: {
            borderColor: colors.border
        },
        timeScale: {
            borderColor: colors.border,
            timeVisible: true,
            secondsVisible: false
        },
        width: container.clientWidth,
        height: container.clientHeight
    });

    const seriesOpts3 = { lineColor: colors.lineColor, lineWidth: colors.lineWidth || 2 };
    if (colors.lineStyle != null) seriesOpts3.lineStyle = colors.lineStyle;
    if (colors.lineType != null) seriesOpts3.lineType = colors.lineType;

    if (colors.seriesType === 'line') {
        seriesOpts3.color = colors.lineColor;
        modalPriceChartSeries = modalPriceChart.addLineSeries(seriesOpts3);
    } else {
        seriesOpts3.topColor = colors.areaTop;
        seriesOpts3.bottomColor = colors.areaBottom;
        modalPriceChartSeries = modalPriceChart.addAreaSeries(seriesOpts3);
    }

    // Handle resize
    modalPriceChartResizeObserver = new ResizeObserver(() => {
        if (modalPriceChart && container) {
            modalPriceChart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight
            });
        }
    });
    modalPriceChartResizeObserver.observe(container);

    // Load initial data
    loadModalPriceChartData(blockchain, '1D');
}

function getModalPriceChartColors(theme) {
    // Reuse getPriceChartColors if available, otherwise define inline
    if (typeof getPriceChartColors === 'function') {
        return getPriceChartColors(theme);
    }
    const themeColors = {
        'dark-mode': {
            background: '#1a1a2e',
            text: '#eaeaea',
            gridLines: '#2a2a4a',
            border: '#3a3a5a',
            areaTop: 'rgba(0, 210, 106, 0.56)',
            areaBottom: 'rgba(0, 210, 106, 0.04)',
            lineColor: 'rgba(0, 210, 106, 1)'
        },
        'light': {
            background: '#ffffff',
            text: '#1a1a2e',
            gridLines: '#e5e7eb',
            border: '#d1d5db',
            areaTop: 'rgba(0, 184, 148, 0.4)',
            areaBottom: 'rgba(0, 184, 148, 0.05)',
            lineColor: 'rgba(0, 184, 148, 1)'
        },
        'ocean-depths': {
            background: '#0a1929',
            text: '#b8e7fb',
            gridLines: '#1e3a52',
            border: '#2d5a7b',
            areaTop: 'rgba(56, 189, 248, 0.56)',
            areaBottom: 'rgba(56, 189, 248, 0.04)',
            lineColor: 'rgba(56, 189, 248, 1)'
        },
        'sunset-horizon': {
            background: '#1a0f0a',
            text: '#ffd8b8',
            gridLines: '#3d2415',
            border: '#5d3a25',
            areaTop: 'rgba(251, 146, 60, 0.56)',
            areaBottom: 'rgba(251, 146, 60, 0.04)',
            lineColor: 'rgba(251, 146, 60, 1)'
        },
        'cypherpunk': {
            background: '#000000',
            text: '#00ff41',
            gridLines: '#003311',
            border: '#005522',
            areaTop: 'rgba(0, 255, 65, 0.56)',
            areaBottom: 'rgba(0, 255, 65, 0.04)',
            lineColor: 'rgba(0, 255, 65, 1)'
        },
        'cypherpunk1': {
            background: '#030308',
            text: '#8ec8ff',
            gridLines: '#1a0a3a',
            border: '#7c3aed',
            areaTop: 'rgba(0, 212, 255, 0.5)',
            areaBottom: 'rgba(0, 212, 255, 0.04)',
            lineColor: 'rgba(0, 212, 255, 1)'
        }
    };
    return themeColors[theme] || themeColors['dark-mode'];
}

async function loadModalPriceChartData(blockchain, timeframe) {
    // Use the shared priceChartCache if available
    const cacheKey = `${blockchain}_${timeframe}`;
    if (typeof priceChartCache !== 'undefined' && priceChartCache[cacheKey]) {
        updateModalChartDisplay(priceChartCache[cacheKey]);
        return;
    }

    try {
        const response = await authFetch(`${API_BASE}/portfolio/charts/blockchain/${blockchain}?timeframe=${timeframe}`);
        if (!response.ok) {
            console.warn(`Modal price chart: HTTP ${response.status} for ${blockchain} ${timeframe}`);
            return;
        }

        const data = await response.json();
        if (!data.data || data.data.length === 0) {
            console.warn('Modal price chart: No data available');
            return;
        }

        // Store in shared cache
        if (typeof priceChartCache !== 'undefined') {
            priceChartCache[cacheKey] = data;
        }

        updateModalChartDisplay(data);
    } catch (error) {
        console.error('Error loading modal price chart:', error);
    }
}

function updateModalChartDisplay(data) {
    // Update chart series
    if (modalPriceChartSeries && data.data && data.data.length > 0) {
        modalPriceChartSeries.setData(data.data);
    }

    // Update price and change display
    const priceEl = document.getElementById('modalChartPrice');
    if (priceEl) {
        priceEl.textContent = formatUSD(data.current_price);
    }

    const changeEl = document.getElementById('modalChartChange');
    if (changeEl) {
        const change = data.change_24h || 0;
        changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.className = `modal-chart-change ${change >= 0 ? 'positive' : 'negative'}`;
    }

    // Fit chart to data
    if (modalPriceChart) {
        modalPriceChart.timeScale().fitContent();
    }
}

function selectModalTimeframe(timeframe) {
    modalPriceChartTimeframe = timeframe;

    // Update button states
    document.querySelectorAll('.modal-tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tf === timeframe);
    });

    if (modalPriceChartBlockchain) {
        loadModalPriceChartData(modalPriceChartBlockchain, timeframe);
    }
}

function destroyModalPriceChart() {
    if (modalPriceChartResizeObserver) {
        modalPriceChartResizeObserver.disconnect();
        modalPriceChartResizeObserver = null;
    }
    if (modalPriceChart) {
        modalPriceChart.remove();
        modalPriceChart = null;
        modalPriceChartSeries = null;
    }
    modalPriceChartBlockchain = null;
    modalPriceChartTimeframe = '1D';
}

// ============================================================================
// Analytics Slider
// ============================================================================

let currentAnalyticsSlide = 0;
let coinAllocationChart = null;
let categoryAllocationChart = null;
let portfolioAnalyticsData = null;  // portfolio coin/category data (separate from transaction-analytics.js analyticsData)
let analyticsLoading = false;
let selectedCoinIndex = null;
let selectedCategoryIndex = null;

const ANALYTICS_CACHE_KEY = 'abct_analytics_cache';
const ANALYTICS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function getCachedAnalytics() {
    try {
        const raw = sessionStorage.getItem(ANALYTICS_CACHE_KEY);
        if (!raw) return null;
        const cached = JSON.parse(raw);
        if (Date.now() - cached.timestamp > ANALYTICS_CACHE_TTL) {
            sessionStorage.removeItem(ANALYTICS_CACHE_KEY);
            return null;
        }
        return cached.data;
    } catch { return null; }
}

function setCachedAnalytics(data) {
    try {
        sessionStorage.setItem(ANALYTICS_CACHE_KEY, JSON.stringify({ data, timestamp: Date.now() }));
    } catch { /* sessionStorage full or unavailable */ }
}

// DeFi cache — persistent across tabs/sessions via localStorage
const DEFI_CACHE_KEY = 'abct_defi_cache';

function getCachedDefi() {
    try {
        const raw = localStorage.getItem(DEFI_CACHE_KEY);
        if (!raw) return null;
        const cached = JSON.parse(raw);
        return cached.data;
    } catch { return null; }
}

function getCachedDefiAge() {
    try {
        const raw = localStorage.getItem(DEFI_CACHE_KEY);
        if (!raw) return Infinity;
        const cached = JSON.parse(raw);
        return Date.now() - cached.timestamp;
    } catch { return Infinity; }
}

function setCachedDefi(data) {
    try {
        localStorage.setItem(DEFI_CACHE_KEY, JSON.stringify({ data, timestamp: Date.now() }));
    } catch { /* localStorage full or unavailable */ }
}

function updateDefiTimestamp() {
    const el = document.getElementById('defiLastUpdated');
    if (!el) return;
    const age = getCachedDefiAge();
    if (age === Infinity) { el.textContent = ''; return; }
    const mins = Math.floor(age / 60000);
    const hours = Math.floor(age / 3600000);
    const days = Math.floor(age / 86400000);
    if (mins < 1) el.textContent = 'Updated just now';
    else if (mins < 60) el.textContent = `Updated ${mins} min ago`;
    else if (hours < 24) el.textContent = `Updated ${hours}h ago`;
    else if (days === 1) el.textContent = 'Updated yesterday';
    else el.textContent = `Updated ${days} days ago`;
}

function setRefreshIndicators(state) {
    const coin = document.getElementById('coinRefreshIndicator');
    const cat = document.getElementById('categoryRefreshIndicator');
    if (state === 'loading') {
        if (coin) { coin.classList.add('active'); coin.classList.remove('done'); }
        if (cat) { cat.classList.add('active'); cat.classList.remove('done'); }
    } else if (state === 'done') {
        if (coin) { coin.classList.remove('active'); coin.classList.add('done'); }
        if (cat) { cat.classList.remove('active'); cat.classList.add('done'); }
        setTimeout(() => {
            if (coin) { coin.classList.remove('done'); }
            if (cat) { cat.classList.remove('done'); }
        }, 2000);
    } else {
        if (coin) { coin.classList.remove('active', 'done'); }
        if (cat) { cat.classList.remove('active', 'done'); }
    }
}

async function loadPortfolioAnalytics(background = false) {
    if (analyticsLoading) {
        console.log('[Analytics] Skipped - already loading');
        return;
    }
    analyticsLoading = true;
    console.log('[Analytics] Loading analytics data...');

    // Show cached data instantly if available
    const cached = getCachedAnalytics();
    if (cached && !portfolioAnalyticsData) {
        portfolioAnalyticsData = cached;
        console.log('[Analytics] Rendering from session cache');
        setAllocationLoadingOverlays(false);
        renderCoinAllocationChart();
        renderCategoryAllocationChart();
        renderPortfolioHeatmap();
    }

    // Show loading overlays if no cached data yet, or refresh indicator if we have data
    if (portfolioAnalyticsData) {
        setRefreshIndicators('loading');
    } else {
        setAllocationLoadingOverlays(true);
    }

    try {
        const response = await authFetch(`${API_BASE}/portfolio/analytics`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const freshData = await response.json();

        console.log('[Analytics] Fetched:', {
            coins: freshData.coin_allocation?.length || 0,
            categories: freshData.category_allocation?.length || 0,
            total: freshData.total_value_usd
        });

        setCachedAnalytics(freshData);
        portfolioAnalyticsData = freshData;
        renderCoinAllocationChart();
        renderCategoryAllocationChart();
        renderPortfolioHeatmap();
        setRefreshIndicators('done');
        setAllocationLoadingOverlays(false);
    } catch (error) {
        console.error('Error loading analytics data:', error);
        setRefreshIndicators('hide');
        setAllocationLoadingOverlays(false);
    } finally {
        analyticsLoading = false;
    }
}

function setAllocationLoadingOverlays(show) {
    const coinOverlay = document.getElementById('coinAllocationLoading');
    const catOverlay = document.getElementById('categoryAllocationLoading');
    if (coinOverlay) coinOverlay.style.display = show ? 'flex' : 'none';
    if (catOverlay) catOverlay.style.display = show ? 'flex' : 'none';
}

// ===========================
// Portfolio Heatmap (Treemap)
// ===========================

function getHeatmapColor(change) {
    // Theme-aware gradient using --accent-success and --accent-error
    const style = getComputedStyle(document.documentElement);
    const successHex = style.getPropertyValue('--accent-success').trim() || '#00d26a';
    const errorHex = style.getPropertyValue('--accent-error').trim() || '#ff6b6b';
    const bgHex = style.getPropertyValue('--bg-secondary').trim() || '#16213e';

    function hexToRgb(hex) {
        hex = hex.replace('#', '');
        return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)];
    }
    function lerp(a, b, t) { return Math.round(a + (b - a) * t); }

    const [sr, sg, sb] = hexToRgb(successHex);
    const [er, eg, eb] = hexToRgb(errorHex);
    const [nr, ng, nb] = hexToRgb(bgHex); // neutral base

    const clamped = Math.max(-15, Math.min(15, change));
    const intensity = Math.abs(clamped) / 15;

    if (clamped >= 0) {
        // Neutral -> accent-success
        return `rgb(${lerp(nr, sr, intensity)}, ${lerp(ng, sg, intensity)}, ${lerp(nb, sb, intensity)})`;
    } else {
        // Neutral -> accent-error
        return `rgb(${lerp(nr, er, intensity)}, ${lerp(ng, eg, intensity)}, ${lerp(nb, eb, intensity)})`;
    }
}

function renderPortfolioHeatmap() {
    const container = document.getElementById('heatmapContainer');
    if (!container || !portfolioAnalyticsData) return;

    const coins = portfolioAnalyticsData.coin_allocation || [];
    // Only tokens with >$10 value
    const filtered = coins.filter(c => c.value_usd >= 10);

    if (filtered.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">No token data available</div>';
        return;
    }

    // Flatten all tokens into a single list (no chain grouping)
    const allTokens = [];
    for (const coin of filtered) {
        let change24h = coin.price_change_24h || 0;
        if (!change24h && priceData[coin.symbol]) {
            change24h = priceData[coin.symbol].usd_24h_change || 0;
        }
        allTokens.push({ ...coin, change24h });
    }
    allTokens.sort((a, b) => b.value_usd - a.value_usd);

    const containerWidth = container.clientWidth || 800;
    const totalHeight = 480;

    // Layout all tokens as one flat treemap
    const tiles = layoutTreemapTiles(allTokens, containerWidth, totalHeight);

    let tilesHtml = '';
    for (const tile of tiles) {
        const bgColor = getHeatmapColor(tile.token.change24h);
        const changeStr = (tile.token.change24h >= 0 ? '+' : '') + tile.token.change24h.toFixed(2) + '%';
        const valueStr = formatUSD(tile.token.value_usd);

        // Size text based on tile area
        const area = tile.w * tile.h;
        let symbolSize, changeSize, valueSize;
        if (area > 40000) {
            symbolSize = '1.8rem'; changeSize = '1.2rem'; valueSize = '1rem';
        } else if (area > 20000) {
            symbolSize = '1.4rem'; changeSize = '1rem'; valueSize = '0.85rem';
        } else if (area > 8000) {
            symbolSize = '1.1rem'; changeSize = '0.85rem'; valueSize = '0.75rem';
        } else if (area > 3000) {
            symbolSize = '0.9rem'; changeSize = '0.75rem'; valueSize = '0.65rem';
        } else if (area > 1000) {
            symbolSize = '0.75rem'; changeSize = '0.6rem'; valueSize = '0';
        } else {
            symbolSize = '0.65rem'; changeSize = '0'; valueSize = '0';
        }

        tilesHtml += `<div class="heatmap-tile" style="` +
            `position:absolute;left:${tile.x}px;top:${tile.y}px;` +
            `width:${tile.w}px;height:${tile.h}px;` +
            `background:${bgColor};" ` +
            `title="${tile.token.symbol}: ${valueStr} (${changeStr})">` +
            `<span class="tile-symbol" style="font-size:${symbolSize}">${tile.token.symbol}</span>` +
            (changeSize !== '0' ? `<span class="tile-change" style="font-size:${changeSize}">${changeStr}</span>` : '') +
            (valueSize !== '0' ? `<span class="tile-value" style="font-size:${valueSize}">${valueStr}</span>` : '') +
            `</div>`;
    }

    container.innerHTML = `<div style="position:relative;width:${containerWidth}px;height:${totalHeight}px;">${tilesHtml}</div>`;
}

// Squarified treemap layout algorithm
function layoutTreemapTiles(tokens, width, height) {
    if (tokens.length === 0) return [];

    const totalValue = tokens.reduce((s, t) => s + t.value_usd, 0);
    if (totalValue === 0) return [];

    const results = [];
    const remaining = tokens.map(t => ({
        token: t,
        area: (t.value_usd / totalValue) * width * height
    }));

    squarify(remaining, [], { x: 0, y: 0, w: width, h: height }, results);
    return results;
}

function squarify(items, row, rect, results) {
    if (items.length === 0) {
        layoutRow(row, rect, results);
        return;
    }

    if (row.length === 0) {
        row.push(items[0]);
        squarify(items.slice(1), row, rect, results);
        return;
    }

    const rowWithNext = [...row, items[0]];
    if (worstRatio(row, rect) >= worstRatio(rowWithNext, rect)) {
        squarify(items.slice(1), rowWithNext, rect, results);
    } else {
        const newRect = layoutRow(row, rect, results);
        squarify(items, [], newRect, results);
    }
}

function worstRatio(row, rect) {
    const totalArea = row.reduce((s, r) => s + r.area, 0);
    const shortSide = Math.min(rect.w, rect.h);
    if (shortSide === 0 || totalArea === 0) return Infinity;

    let worst = 0;
    for (const item of row) {
        const ratio = Math.max(
            (shortSide * shortSide * item.area) / (totalArea * totalArea),
            (totalArea * totalArea) / (shortSide * shortSide * item.area)
        );
        worst = Math.max(worst, ratio);
    }
    return worst;
}

function layoutRow(row, rect, results) {
    if (row.length === 0) return rect;

    const totalArea = row.reduce((s, r) => s + r.area, 0);
    const horizontal = rect.w >= rect.h;

    if (horizontal) {
        const rowWidth = totalArea / rect.h;
        let y = rect.y;
        for (const item of row) {
            const h = item.area / rowWidth;
            results.push({
                token: item.token,
                x: Math.round(rect.x),
                y: Math.round(y),
                w: Math.max(1, Math.round(rowWidth) - 1),
                h: Math.max(1, Math.round(h) - 1)
            });
            y += h;
        }
        return { x: rect.x + rowWidth, y: rect.y, w: rect.w - rowWidth, h: rect.h };
    } else {
        const rowHeight = totalArea / rect.w;
        let x = rect.x;
        for (const item of row) {
            const w = item.area / rowHeight;
            results.push({
                token: item.token,
                x: Math.round(x),
                y: Math.round(rect.y),
                w: Math.max(1, Math.round(w) - 1),
                h: Math.max(1, Math.round(rowHeight) - 1)
            });
            x += w;
        }
        return { x: rect.x, y: rect.y + rowHeight, w: rect.w, h: rect.h - rowHeight };
    }
}

// Slider functions kept as no-ops for backward compatibility
// (analytics charts have moved to the Blockchains tab on data.html)
function nextAnalyticsSlide() {}
function previousAnalyticsSlide() {}
function goToAnalyticsSlide(index) {}
function updateAnalyticsSlide() {}

// Initialize Blockchains tab on data.html
let _blockchainsInitialized = false;
async function initBlockchainsTab() {
    if (_blockchainsInitialized) return;
    _blockchainsInitialized = true;
    console.log('[Blockchains] Initializing tab...');

    // Ensure prices and portfolio data are loaded (needed for all charts)
    // On data.html these globals may not be populated yet
    const needsPrices = !prices || !prices.ADA || prices.ADA === 0;
    const needsPortfolio = !lastPortfolioData;
    console.log('[Blockchains] needsPrices:', needsPrices, 'needsPortfolio:', needsPortfolio);

    if (needsPrices || needsPortfolio) {
        try {
            // Load prices and portfolio summary in parallel
            const [, summaryResp] = await Promise.all([
                needsPrices ? loadPrices() : Promise.resolve(),
                needsPortfolio ? authFetch(`${API_BASE}/portfolio/summary`) : Promise.resolve(null)
            ]);
            if (summaryResp && summaryResp.ok) {
                const data = await summaryResp.json();
                // Populate globals that getChainAllocations() depends on
                lastPortfolioData = data;
                walletTotals.ADA = data.cardano?.total_ada || 0;
                walletTotals.BTC = data.bitcoin?.total_btc || 0;
                walletTotals.ETH = data.ethereum?.total_eth || 0;
                walletTotals.SOL = data.solana?.total_sol || 0;
                walletTotals.MATIC = data.polygon?.total_matic || 0;
                walletTotals.ETH_BASE = data.base?.total_eth || 0;
                walletTotals.ALGO = data.algorand?.total_algo || 0;
                walletTotals.BNB = data.bsc?.total_bnb || 0;
                walletTotals.ETH_ARB = data.arbitrum?.total_eth || 0;
                walletTotals.AVAX = data.avalanche?.total_avax || 0;
                walletTotals.TRX = data.tron?.total_trx || 0;
                walletTotals.XRP = data.xrp?.total_xrp || 0;
                walletTotals.HBAR = data.hedera?.total_hbar || 0;
                walletTotals.EGLD = data.multiversx?.total_egld || 0;
                walletTotals.SUI = data.sui?.total_sui || 0;
                walletTotals.APT = data.aptos?.total_apt || 0;
                walletTotals.FIL = data.filecoin?.total_fil || 0;
                walletTotals.LTC = data.litecoin?.total_ltc || 0;
                walletTotals.DOGE = data.dogecoin?.total_doge || 0;
                walletTotals.ZEC = data.zcash?.total_zec || 0;
                walletTotals.XTZ = data.tezos?.total_xtz || 0;
                walletTotals.STX = data.stacks?.total_stx || 0;
                walletTotals.VET = data.vechain?.total_vet || 0;
                walletTotals.ATOM = data.cosmos?.total_atom || 0;
                walletTotals.NEAR = data.near?.total_near || 0;
                walletTotals.ICP = data.icp?.total_icp || 0;
                walletTotals.OSMO = data.osmosis?.total_osmo || 0;
                walletTotals.TIA = data.celestia?.total_tia || 0;
                walletTotals.INJ = data.injective?.total_inj || 0;
                walletTotals.DYDX = data.dydx?.total_dydx || 0;
                walletTotals.SEI = data.sei?.total_sei || 0;
                walletTotals.AKT = data.akash?.total_akt || 0;
                walletTotals.TON = data.ton?.total_ton || 0;
                walletTotals.DOT = data.polkadot?.total_dot || 0;
                walletTotals.KSM = data.kusama?.total_ksm || 0;
                walletTotals.XLM = data.stellar?.total_xlm || 0;
                walletTotals.KAS = data.kaspa?.total_kas || 0;
                walletTotals.KLAY = data.kaia?.total_klay || 0;
                walletTotals.ERG = data.ergo?.total_erg || 0;
                walletTotals.IOTA = data.iota?.total_iota || 0;
                walletTotals.WAVES = data.waves?.total_waves || 0;
                walletTotals.MINA = data.mina?.total_mina || 0;
                walletTotals.ZIL = data.zilliqa?.total_zil || 0;
                renderBlockchainCards(data);
            }
        } catch (e) {
            console.warn('[Blockchains] Failed to load prices/portfolio:', e);
        }
    } else {
        // Data already loaded (e.g. on index.html), just render cards
        try {
            const resp = await authFetch(`${API_BASE}/portfolio/summary`);
            if (resp.ok) {
                const data = await resp.json();
                renderBlockchainCards(data);
            }
        } catch (e) {
            console.warn('[Blockchains] Failed to load portfolio data:', e);
        }
    }

    // Initialize Sankey flow diagram (3-column: Total → Chains → Wallets)
    if (typeof PortfolioSankey !== 'undefined' && document.getElementById('portfolioSankeyContainer')) {
        try {
            window.portfolioSankey = new PortfolioSankey('portfolioSankeyContainer');
            const allocs = getChainAllocations();
            const total = allocs.reduce((sum, a) => sum + a.usd, 0);
            window.portfolioSankey.setData(total, allocs, lastPortfolioData, prices);
            window.portfolioSankey.render();
        } catch (e) {
            console.warn('[Sankey] Failed to initialize:', e);
        }
    }

    // Initialize Streamgraph (chain history over time)
    if (typeof PortfolioStreamgraph !== 'undefined' && document.getElementById('portfolioStreamContainer')) {
        try {
            window.portfolioStream = new PortfolioStreamgraph('portfolioStreamContainer');
            window.portfolioStream.loadData('1y');
        } catch (e) {
            console.warn('[Streamgraph] Failed to initialize:', e);
        }
    }

    // Load analytics data (coin allocation, category allocation, heatmap)
    console.log('[Blockchains] About to call loadPortfolioAnalytics...');
    try {
        await loadPortfolioAnalytics();
        console.log('[Blockchains] loadPortfolioAnalytics completed. portfolioAnalyticsData:', portfolioAnalyticsData ? 'loaded' : 'null');
    } catch (e) {
        console.error('[Blockchains] loadPortfolioAnalytics threw:', e);
    }

    // Initialize price chart
    if (typeof initializePriceChart === 'function') {
        setTimeout(() => initializePriceChart(), 200);
    }
}

function renderCoinAllocationChart() {
    if (!portfolioAnalyticsData || !portfolioAnalyticsData.coin_allocation) return;

    const canvasEl = document.getElementById('coinAllocationChart');
    if (!canvasEl) return;
    const ctx = canvasEl.getContext('2d');
    if (coinAllocationChart) coinAllocationChart.destroy();

    // Top 6 coins, rest go into "Other"
    const topCoins = portfolioAnalyticsData.coin_allocation.slice(0, 6);
    const remainingCoins = portfolioAnalyticsData.coin_allocation.slice(6);

    let coins, labels, values, colors;

    if (remainingCoins.length > 0) {
        const otherValue = remainingCoins.reduce((sum, c) => sum + c.value_usd, 0);
        const otherPercentage = remainingCoins.reduce((sum, c) => sum + c.percentage, 0);

        coins = [...topCoins, {
            symbol: 'Other',
            name: `${remainingCoins.length} other assets`,
            value_usd: otherValue,
            percentage: otherPercentage
        }];
    } else {
        coins = topCoins;
    }

    labels = coins.map(c => c.symbol);
    values = coins.map(c => c.value_usd);
    colors = generateChartColors(coins.length);

    // Store coins on window for center text plugin access
    window._coinChartData = coins;

    // Plugin to draw detailed info in center of doughnut
    const coinCenterTextPlugin = {
        id: 'coinCenterText',
        afterDraw: (chart) => {
            const coinData = window._coinChartData;
            if (selectedCoinIndex === null || selectedCoinIndex === undefined || !coinData) return;

            const coin = coinData[selectedCoinIndex];
            const ctx = chart.ctx;
            const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
            const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;

            ctx.save();
            ctx.textAlign = 'center';

            // Line 1: Symbol (bold, large)
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 18px sans-serif';
            ctx.fillText(coin.symbol, centerX, centerY - 22);

            // Line 2: USD value (bold, larger)
            ctx.font = 'bold 24px sans-serif';
            ctx.fillText(formatUSD(coin.value_usd), centerX, centerY + 8);

            // Line 3: Percentage (muted)
            ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
            ctx.font = '14px sans-serif';
            ctx.fillText(coin.percentage.toFixed(2) + '%', centerX, centerY + 32);

            ctx.restore();
        }
    };

    // Build per-segment borders: thin dark line between segments
    const bgColor = getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim() || '#1a1a2e';

    coinAllocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: bgColor,
                hoverBorderWidth: 2,
                hoverBorderColor: bgColor,
                offset: new Array(coins.length).fill(0),
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '62%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    selectCoinSegment(elements[0].index);
                }
            }
        },
        plugins: [coinCenterTextPlugin]
    });

    renderCoinLegend(coins, colors);
}

function selectCoinSegment(index) {
    selectedCoinIndex = index;

    // Get the coin data - handle "Other" aggregation
    const topCoins = portfolioAnalyticsData.coin_allocation.slice(0, 6);
    const remainingCoins = portfolioAnalyticsData.coin_allocation.slice(6);
    let coins;
    if (remainingCoins.length > 0) {
        const otherValue = remainingCoins.reduce((sum, c) => sum + c.value_usd, 0);
        const otherPercentage = remainingCoins.reduce((sum, c) => sum + c.percentage, 0);
        coins = [...topCoins, {
            symbol: 'Other',
            name: `${remainingCoins.length} other assets`,
            value_usd: otherValue,
            percentage: otherPercentage
        }];
    } else {
        coins = topCoins;
    }

    // Pop-out effect: offset selected segment
    const offsets = new Array(coins.length).fill(0);
    offsets[index] = 14;

    // Brighten selected, keep others at base
    const colors = generateChartColors(coins.length);
    colors[index] = brightenColor(colors[index], 30);

    coinAllocationChart.data.datasets[0].backgroundColor = colors;
    coinAllocationChart.data.datasets[0].offset = offsets;
    coinAllocationChart.update();

    // Update legend selection (visual highlight)
    document.querySelectorAll('#coinAllocationLegend .analytics-legend-item-compact').forEach((item, i) => {
        if (i === index) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
}

function renderCoinLegend(coins, colors) {
    const legendDiv = document.getElementById('coinAllocationLegend');
    legendDiv.innerHTML = coins.map((coin, index) => {
        // Use logo_url from backend data, or fallback to LogoKit for "Other" case
        const tokenLogoUrl = coin.logo_url || (
            coin.symbol !== 'Other'
                ? getLogoKitUrl(coin.symbol, 32)
                : ''
        );

        return `
            <div class="analytics-legend-item-compact" onclick="selectCoinSegment(${index})">
                ${tokenLogoUrl ? `<img src="${tokenLogoUrl}" alt="${coin.symbol}" class="coin-legend-logo" onerror="this.style.display='none'">` : ''}
                <div class="legend-compact-label">
                    <div class="legend-top-row">
                        <span class="legend-symbol">${coin.symbol}</span>
                        <span class="legend-value-inline">${formatUSD(coin.value_usd)}</span>
                    </div>
                    <span class="legend-percentage-compact">${coin.percentage.toFixed(1)}%</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderCategoryAllocationChart() {
    if (!portfolioAnalyticsData || !portfolioAnalyticsData.category_allocation) return;

    const canvasEl = document.getElementById('categoryAllocationChart');
    if (!canvasEl) return;
    const ctx = canvasEl.getContext('2d');
    if (categoryAllocationChart) categoryAllocationChart.destroy();

    const categories = portfolioAnalyticsData.category_allocation;
    const labels = categories.map(c => c.category);
    const values = categories.map(c => c.value_usd);
    const colors = generateCategoryColors(categories.length);

    // Store categories on window for center text plugin access
    window._categoryChartData = categories;

    // Plugin to draw detailed info in center of doughnut
    const centerTextPlugin = {
        id: 'centerText',
        afterDraw: (chart) => {
            const catData = window._categoryChartData;
            if (selectedCategoryIndex === null || selectedCategoryIndex === undefined || !catData) return;

            const cat = catData[selectedCategoryIndex];
            const ctx = chart.ctx;
            const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
            const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;

            let categoryName = cat.category;
            if (categoryName === 'Decentralized Finance') categoryName = 'DeFi';

            ctx.save();
            ctx.textAlign = 'center';

            // Line 1: Category name (bold)
            ctx.fillStyle = '#ffffff';
            const nameSize = categoryName.length > 14 ? 15 : 18;
            ctx.font = `bold ${nameSize}px sans-serif`;
            ctx.fillText(categoryName, centerX, centerY - 22);

            // Line 2: USD value (bold, larger)
            ctx.font = 'bold 24px sans-serif';
            ctx.fillText(formatUSD(cat.value_usd), centerX, centerY + 8);

            // Line 3: Percentage (muted)
            ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
            ctx.font = '14px sans-serif';
            ctx.fillText(cat.percentage.toFixed(2) + '%', centerX, centerY + 32);

            ctx.restore();
        }
    };

    // Build per-segment borders: thin dark line between segments
    const bgColor = getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim() || '#1a1a2e';

    categoryAllocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: bgColor,
                hoverBorderWidth: 2,
                hoverBorderColor: bgColor,
                offset: new Array(categories.length).fill(0),
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '62%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    selectCategorySegment(elements[0].index);
                }
            }
        },
        plugins: [centerTextPlugin]
    });

    renderCategoryLegend(categories, colors);
}

function selectCategorySegment(index) {
    selectedCategoryIndex = index;

    const count = portfolioAnalyticsData.category_allocation.length;

    // Pop-out effect: offset selected segment
    const offsets = new Array(count).fill(0);
    offsets[index] = 14;

    // Brighten selected, keep others at base
    const colors = generateCategoryColors(count);
    colors[index] = brightenColor(colors[index], 30);

    categoryAllocationChart.data.datasets[0].backgroundColor = colors;
    categoryAllocationChart.data.datasets[0].offset = offsets;
    categoryAllocationChart.update();

    // Update legend selection (visual highlight)
    document.querySelectorAll('#categoryAllocationLegend .analytics-legend-item-compact').forEach((item, i) => {
        if (i === index) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
}

function renderCategoryLegend(categories, colors) {
    const legendDiv = document.getElementById('categoryAllocationLegend');
    legendDiv.innerHTML = categories.map((category, index) => `
        <div class="analytics-legend-item-compact"
             onclick="selectCategorySegment(${index})"
             onmouseenter="showCategoryTooltip(event, ${index})"
             onmouseleave="hideCategoryTooltip()">
            <div class="legend-compact-label">
                <div class="legend-top-row">
                    <span class="legend-symbol">${category.category}</span>
                    <span class="legend-value-inline">${formatUSD(category.value_usd)}</span>
                </div>
                <span class="legend-percentage-compact">${category.percentage.toFixed(1)}%</span>
            </div>
        </div>
    `).join('');
}

function showCategoryTooltip(event, categoryIndex) {
    const category = portfolioAnalyticsData.category_allocation[categoryIndex];

    // Remove existing tooltip if any
    hideCategoryTooltip();

    // Get top 5 assets sorted by value
    if (!category.tokens || category.tokens.length === 0) return;

    const topTokens = [...category.tokens]
        .sort((a, b) => b.value_usd - a.value_usd)
        .slice(0, 5);

    // Create tooltip element
    const tooltip = document.createElement('div');
    tooltip.id = 'categoryTooltip';
    tooltip.className = 'category-tooltip';

    let html = `
        <div class="category-tooltip-header">Top Assets in ${category.category}</div>
        <div class="category-tooltip-body">
    `;

    topTokens.forEach((token, idx) => {
        html += `
            <div class="category-tooltip-item">
                <span class="tooltip-rank">${idx + 1}.</span>
                <span class="tooltip-symbol">${token.symbol}</span>
                <span class="tooltip-value">${formatUSD(token.value_usd)}</span>
            </div>
        `;
    });

    if (category.token_count > 5) {
        html += `
            <div class="category-tooltip-more">
                ... and ${category.token_count - 5} more token${category.token_count - 5 !== 1 ? 's' : ''}
            </div>
        `;
    }

    html += `</div>`;
    tooltip.innerHTML = html;

    // Position tooltip
    document.body.appendChild(tooltip);

    const rect = event.currentTarget.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();

    // Position to the right of the legend item
    let left = rect.right + 10;
    let top = rect.top + (rect.height / 2) - (tooltipRect.height / 2);

    // Adjust if tooltip goes off screen
    if (left + tooltipRect.width > window.innerWidth) {
        left = rect.left - tooltipRect.width - 10; // Show on left instead
    }
    if (top < 10) top = 10;
    if (top + tooltipRect.height > window.innerHeight - 10) {
        top = window.innerHeight - tooltipRect.height - 10;
    }

    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
}

function hideCategoryTooltip() {
    const tooltip = document.getElementById('categoryTooltip');
    if (tooltip) {
        tooltip.remove();
    }
}

function generateChartColors(count) {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';

    let baseColors;

    if (theme === 'ocean-depths') {
        // Ocean Depths - Aquatic blues with coral accents
        // Matches --accent-cardano (#00b4d8), --accent-success (#06d6a0), --accent-bitcoin (#ffd166)
        baseColors = [
            '#00b4d8', // Bright cyan (matches theme accent)
            '#06d6a0', // Teal green (success accent)
            '#48cae4', // Light cyan
            '#0096c7', // Deep ocean blue
            '#90e0ef', // Sky blue
            '#ffd166', // Coral yellow (bitcoin accent)
            '#ef476f', // Coral pink (error accent)
            '#118ab2', // Navy blue
            '#00f5d4', // Aqua
            '#073b4c'  // Deep teal
        ];
    } else if (theme === 'sunset-horizon') {
        // Sunset Horizon - Warm oranges, reds, purples
        // Matches --accent-cardano (#ff6b35), --accent-bitcoin (#ffc145)
        baseColors = [
            '#ff6b35', // Vivid orange (cardano accent)
            '#ffc145', // Golden (bitcoin accent)
            '#ff8c42', // Warm orange (ethereum accent)
            '#f72585', // Hot pink
            '#b5179e', // Magenta
            '#d62828', // Deep red
            '#7209b7', // Purple
            '#fcbf49', // Amber yellow
            '#ff3366', // Red (error accent)
            '#560bad'  // Deep purple
        ];
    } else if (theme === 'cypherpunk1') {
        // Cypherpunk - Neon cyan/magenta/violet palette
        baseColors = [
            '#00d4ff', // Electric cyan (primary)
            '#d946ef', // Neon magenta
            '#7c3aed', // Vibrant violet
            '#06b6d4', // Deep cyan
            '#a855f7', // Purple
            '#ec4899', // Pink
            '#0ea5e9', // Sky blue
            '#8b5cf6', // Indigo
            '#f472b6', // Light pink
            '#22d3ee', // Bright teal
            '#c084fc', // Lavender
            '#818cf8', // Periwinkle
        ];
    } else {
        // Default - Balanced professional palette
        // Greens, blues, purples with warm accents
        baseColors = [
            '#00d26a', // Emerald green (primary)
            '#3498db', // Bright blue
            '#1abc9c', // Turquoise
            '#9b59b6', // Amethyst purple
            '#f39c12', // Orange
            '#e74c3c', // Coral red
            '#2ecc71', // Green
            '#e91e63', // Pink
            '#3b82f6', // Blue
            '#8b5cf6'  // Purple
        ];
    }

    return baseColors.slice(0, count);
}

function generateCategoryColors(count) {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';

    let categoryColors;

    if (theme === 'ocean-depths') {
        // Ocean Depths - Aquatic blues with coral accents
        categoryColors = {
            'Layer 1 (L1)': '#00b4d8',        // Bright cyan (matches accent-cardano)
            'Decentralized Finance (DeFi)': '#06d6a0', // Teal green (success)
            'Cardano Ecosystem': '#48cae4',   // Light cyan
            'Infrastructure': '#ffd166',       // Coral yellow (bitcoin accent)
            'Stablecoins': '#0096c7',         // Deep ocean blue
            'Meme': '#ef476f',                // Coral pink (error)
            'Gaming': '#90e0ef',              // Sky blue
            'Other': '#6c757d'                // Gray
        };
    } else if (theme === 'sunset-horizon') {
        // Sunset Horizon - Warm oranges, reds, purples
        categoryColors = {
            'Layer 1 (L1)': '#ff6b35',        // Vivid orange (cardano accent)
            'Decentralized Finance (DeFi)': '#ffc145', // Golden (bitcoin accent)
            'Cardano Ecosystem': '#ff8c42',   // Warm orange (ethereum accent)
            'Infrastructure': '#f72585',       // Hot pink
            'Stablecoins': '#b5179e',         // Magenta
            'Meme': '#ff3366',                // Red (error)
            'Gaming': '#7209b7',              // Purple
            'Other': '#6c757d'                // Gray
        };
    } else if (theme === 'cypherpunk1') {
        // Cypherpunk - Neon cyan/magenta/violet category palette
        categoryColors = {
            'Layer 1 (L1)': '#00d4ff',        // Electric cyan
            'Decentralized Finance (DeFi)': '#d946ef', // Neon magenta
            'Cardano Ecosystem': '#7c3aed',   // Vibrant violet
            'Infrastructure': '#06b6d4',       // Deep cyan
            'Stablecoins': '#a855f7',         // Purple
            'Meme': '#ec4899',                // Pink
            'Gaming': '#0ea5e9',              // Sky blue
            'Other': '#64748b'                // Slate gray
        };
    } else {
        // Default - Balanced professional palette
        categoryColors = {
            'Layer 1 (L1)': '#3498db',        // Bright blue
            'Decentralized Finance (DeFi)': '#00d26a', // Emerald green (primary)
            'Cardano Ecosystem': '#1abc9c',   // Turquoise
            'Infrastructure': '#f39c12',       // Orange
            'Stablecoins': '#9b59b6',         // Amethyst purple
            'Meme': '#e91e63',                // Pink
            'Gaming': '#8b5cf6',              // Purple
            'Other': '#6b7280'                // Gray
        };
    }

    return portfolioAnalyticsData.category_allocation.map(cat =>
        categoryColors[cat.category] || categoryColors['Other']
    );
}

function brightenColor(hex, percent) {
    // Convert hex to RGB
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.min(255, ((num >> 16) & 255) + percent);
    const g = Math.min(255, ((num >> 8) & 255) + percent);
    const b = Math.min(255, (num & 255) + percent);

    // Convert back to hex
    return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
}

// ============================================================================
// TradingView Lightweight Charts Integration (4th Analytics Slide)
// ============================================================================

let priceChart = null;
let priceChartSeries = null;
let currentBlockchain = 'cardano';
let currentTimeframe = '1D';
let priceChartInitialized = false;
let priceChartLoadingSet = new Set(); // Track which blockchain+timeframe combos are currently loading
let priceChartLoadTimeout = null;
// Cache for storing fetched timeframe data: { 'cardano_1M': {...}, 'bitcoin_7D': {...} }
let priceChartCache = {};

async function initializePriceChart() {
    if (priceChartInitialized) return;

    const container = document.getElementById('priceChart');
    if (!container || !window.LightweightCharts) {
        console.warn('Price chart container or LightweightCharts library not available');
        return;
    }

    // Get theme colors
    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
    const chartColors = getPriceChartColors(theme);

    // Create chart
    const crosshairOpts = { mode: chartColors.crosshairMode != null ? chartColors.crosshairMode : LightweightCharts.CrosshairMode.Normal };
    if (chartColors.crosshairColor) { crosshairOpts.vertLine = { color: chartColors.crosshairColor }; crosshairOpts.horzLine = { color: chartColors.crosshairColor }; }

    priceChart = LightweightCharts.createChart(container, {
        layout: {
            background: { color: chartColors.background },
            textColor: chartColors.text
        },
        grid: {
            vertLines: { color: chartColors.gridLines },
            horzLines: { color: chartColors.gridLines }
        },
        crosshair: crosshairOpts,
        rightPriceScale: {
            borderColor: chartColors.border
        },
        timeScale: {
            borderColor: chartColors.border,
            timeVisible: true,
            secondsVisible: false
        },
        width: container.clientWidth,
        height: container.clientHeight
    });

    // Create series based on Chart Designer settings
    const seriesOpts = {
        lineColor: chartColors.lineColor,
        lineWidth: chartColors.lineWidth || 2
    };
    if (chartColors.lineStyle != null) seriesOpts.lineStyle = chartColors.lineStyle;
    if (chartColors.lineType != null) seriesOpts.lineType = chartColors.lineType;

    if (chartColors.seriesType === 'line') {
        seriesOpts.color = chartColors.lineColor;
        priceChartSeries = priceChart.addLineSeries(seriesOpts);
    } else {
        seriesOpts.topColor = chartColors.areaTop;
        seriesOpts.bottomColor = chartColors.areaBottom;
        priceChartSeries = priceChart.addAreaSeries(seriesOpts);
    }

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
        if (priceChart && container) {
            priceChart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight
            });
        }
    });
    resizeObserver.observe(container);

    priceChartInitialized = true;

    // Load initial data (Cardano, 1D) - other timeframes load on-demand
    await loadPriceChartData('cardano', '1D');
}

function getChartDesignerSettings() {
    try {
        const raw = localStorage.getItem('abct_chart_designer');
        if (!raw) return null;
        const s = JSON.parse(raw);
        if (!s || !s.enabled) return null;
        return s;
    } catch (e) {
        return null;
    }
}

function getPriceChartColors(theme) {
    // Check for Chart Designer overrides
    const custom = getChartDesignerSettings();
    if (custom) {
        const hexToRgba = (hex, opacity) => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${opacity})`;
        };
        return {
            background: custom.background,
            text: custom.textColor,
            gridLines: custom.gridVisible ? custom.gridColor : 'transparent',
            border: custom.borderColor,
            areaTop: hexToRgba(custom.areaTopColor, custom.areaTopOpacity),
            areaBottom: hexToRgba(custom.areaBottomColor, custom.areaBottomOpacity),
            lineColor: custom.lineColor,
            crosshairMode: custom.crosshairMode,
            crosshairColor: custom.crosshairColor,
            seriesType: custom.seriesType,
            lineWidth: custom.lineWidth,
            lineStyle: custom.lineStyle,
            lineType: custom.lineType
        };
    }

    const themeColors = {
        'dark-mode': {
            background: '#1a1a2e',
            text: '#eaeaea',
            gridLines: '#2a2a4a',
            border: '#3a3a5a',
            areaTop: 'rgba(0, 210, 106, 0.56)',
            areaBottom: 'rgba(0, 210, 106, 0.04)',
            lineColor: 'rgba(0, 210, 106, 1)'
        },
        'light': {
            background: '#ffffff',
            text: '#1a1a2e',
            gridLines: '#e5e7eb',
            border: '#d1d5db',
            areaTop: 'rgba(0, 184, 148, 0.4)',
            areaBottom: 'rgba(0, 184, 148, 0.05)',
            lineColor: 'rgba(0, 184, 148, 1)'
        },
        'ocean-depths': {
            background: '#0a1929',
            text: '#b8e7fb',
            gridLines: '#1e3a52',
            border: '#2d5a7b',
            areaTop: 'rgba(56, 189, 248, 0.56)',
            areaBottom: 'rgba(56, 189, 248, 0.04)',
            lineColor: 'rgba(56, 189, 248, 1)'
        },
        'sunset-horizon': {
            background: '#1a0f0a',
            text: '#ffd8b8',
            gridLines: '#3d2415',
            border: '#5d3a25',
            areaTop: 'rgba(251, 146, 60, 0.56)',
            areaBottom: 'rgba(251, 146, 60, 0.04)',
            lineColor: 'rgba(251, 146, 60, 1)'
        },
        'cypherpunk': {
            background: '#000000',
            text: '#00ff41',
            gridLines: '#003311',
            border: '#005522',
            areaTop: 'rgba(0, 255, 65, 0.56)',
            areaBottom: 'rgba(0, 255, 65, 0.04)',
            lineColor: 'rgba(0, 255, 65, 1)'
        },
        'cypherpunk1': {
            background: '#030308',
            text: '#8ec8ff',
            gridLines: '#1a0a3a',
            border: '#7c3aed',
            areaTop: 'rgba(0, 212, 255, 0.5)',
            areaBottom: 'rgba(0, 212, 255, 0.04)',
            lineColor: 'rgba(0, 212, 255, 1)'
        }
    };

    return themeColors[theme] || themeColors['dark-mode'];
}

async function loadPriceChartData(blockchain, timeframe, silent = false) {
    // Check cache first
    const cacheKey = `${blockchain}_${timeframe}`;
    if (priceChartCache[cacheKey]) {
        const data = priceChartCache[cacheKey];

        // If not silent, update the UI
        if (!silent) {
            updateChartDisplay(blockchain, data);
        }
        return data;
    }

    // Prevent duplicate requests for the same blockchain+timeframe combo
    const requestKey = `${blockchain}_${timeframe}`;
    if (priceChartLoadingSet.has(requestKey)) {
        console.log(`Chart data for ${blockchain} ${timeframe} already loading, skipping duplicate request`);
        return;
    }

    // Mark this request as in progress
    priceChartLoadingSet.add(requestKey);

    try {
        const response = await authFetch(`${API_BASE}/portfolio/charts/blockchain/${blockchain}?timeframe=${timeframe}`);
        if (!response.ok) {
            if (response.status === 404 || response.status === 503) {
                const error = await response.json();
                console.warn('Price data unavailable:', error.error || error.detail);
                // Keep showing current chart, don't clear it
                return null;
            }
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();

        if (!data.data || data.data.length === 0) {
            console.warn('No chart data available');
            return null;
        }

        // Store in cache
        priceChartCache[cacheKey] = data;

        // Update UI if not silent
        if (!silent) {
            updateChartDisplay(blockchain, data);
        }

        return data;

    } catch (error) {
        if (!silent) {
            console.error('Error loading price chart data:', error);
        }
        return null;
    } finally {
        // Remove from loading set after a short delay to prevent rapid duplicate requests
        setTimeout(() => {
            priceChartLoadingSet.delete(requestKey);
        }, 500);
    }
}

function updateChartDisplay(blockchain, data) {
    console.log(`[Chart] Updating display for ${blockchain}`, {
        dataPoints: data.data ? data.data.length : 0,
        firstPoint: data.data && data.data[0],
        lastPoint: data.data && data.data[data.data.length - 1],
        currentPrice: data.current_price
    });

    // Update chart series
    if (priceChartSeries && data.data && data.data.length > 0) {
        priceChartSeries.setData(data.data);
        console.log(`[Chart] ✓ Set ${data.data.length} data points for ${blockchain}`);
    } else {
        console.warn(`[Chart] Cannot update chart:`, {
            hasSeries: !!priceChartSeries,
            hasData: !!(data.data && data.data.length > 0)
        });
    }

    // Update chart title and stats
    const titleEl = document.getElementById('chartTitle');
    if (titleEl) {
        titleEl.textContent = `${blockchain.charAt(0).toUpperCase() + blockchain.slice(1)} (${data.symbol})`;
    }

    const priceEl = document.getElementById('chartPrice');
    if (priceEl) {
        priceEl.textContent = formatUSD(data.current_price);
    }

    const changeEl = document.getElementById('chartChange');
    if (changeEl) {
        const change = data.change_24h || 0;
        changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
        changeEl.className = change >= 0 ? 'change positive' : 'change negative';
    }

    // Fit chart to data
    if (priceChart) {
        priceChart.timeScale().fitContent();
    }
}

// All chart data loads on-demand when user selects timeframe
// Backend caching (1hr TTL) + client cache makes subsequent loads instant

function selectBlockchain(blockchain) {
    currentBlockchain = blockchain;

    // Update button states
    document.querySelectorAll('.blockchain-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.blockchain === blockchain);
    });

    // Load data for current timeframe only (other timeframes load on-demand)
    loadPriceChartData(blockchain, currentTimeframe);
}

function selectTimeframe(timeframe) {
    currentTimeframe = timeframe;

    // Update button states
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.timeframe === timeframe);
    });

    // Load new data
    loadPriceChartData(currentBlockchain, timeframe);
}

// Initialize price chart when the blockchains tab is visible
function checkAndInitPriceChart() {
    const priceChartContainer = document.getElementById('priceChart');
    if (priceChartContainer && !priceChartInitialized) {
        setTimeout(() => initializePriceChart(), 100);
    }
}

// Update changeTheme to recreate price chart
const originalChangeTheme = window.changeTheme;
window.changeTheme = function(themeName) {
    if (originalChangeTheme) {
        originalChangeTheme(themeName);
    } else {
        document.documentElement.setAttribute('data-theme', themeName);
        localStorage.setItem('abct-theme', themeName);
    }

    // Recreate price chart with new theme colors
    if (priceChart && priceChartInitialized) {
        const container = document.getElementById('priceChart');
        if (container) {
            priceChart.remove();
            priceChart = null;
            priceChartSeries = null;
            priceChartInitialized = false;
            setTimeout(() => initializePriceChart(), 100);
        }
    }
};
