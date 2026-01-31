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
let prices = { ADA: 0, BTC: 0, ETH: 0, SOL: 0, MATIC: 0 };
let displayMode = 'crypto'; // 'crypto' or 'usd'

// Portfolio totals for calculating total value
let walletTotals = { ADA: 0, BTC: 0, ETH: 0, SOL: 0, MATIC: 0, ETH_BASE: 0 };
let stakingTotals = {}; // { 'INDY': 1234.56, 'STRIKE': 789.01, etc. }
let defiTotals = {}; // DeFi tokens held in wallets (governance tokens, stablecoins, etc.)
let exchangeTotals = { usd: 0 }; // Total USD value from exchanges
let nftTotals = { cardano: 0, ethereum: 0, solana: 0, polygon: 0, base: 0 }; // NFT values by chain
let nftCounts = { cardano: 0, ethereum: 0, solana: 0, polygon: 0, base: 0 }; // NFT counts by chain

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

// Helper to get total NFT value across all chains
function getNftTotalUsd() {
    return (nftTotals.cardano || 0) + (nftTotals.ethereum || 0) + (nftTotals.solana || 0) + (nftTotals.polygon || 0) + (nftTotals.base || 0);
}

// Update NFT counts in summary cards
function updateSummaryCardNftCounts() {
    const cardanoNftsEl = document.getElementById('cardanoNfts');
    const ethereumNftsEl = document.getElementById('ethereumNfts');
    const solanaNftsEl = document.getElementById('solanaNfts');
    const polygonNftsEl = document.getElementById('polygonNfts');
    const baseNftsEl = document.getElementById('baseNfts');

    if (cardanoNftsEl) {
        const count = nftCounts.cardano || 0;
        cardanoNftsEl.textContent = `${count} NFT${count !== 1 ? 's' : ''}`;
    }
    if (ethereumNftsEl) {
        const count = nftCounts.ethereum || 0;
        ethereumNftsEl.textContent = `${count} NFT${count !== 1 ? 's' : ''}`;
    }
    if (solanaNftsEl) {
        const count = nftCounts.solana || 0;
        solanaNftsEl.textContent = `${count} NFT${count !== 1 ? 's' : ''}`;
    }
    if (polygonNftsEl) {
        const count = nftCounts.polygon || 0;
        polygonNftsEl.textContent = `${count} NFT${count !== 1 ? 's' : ''}`;
    }
    if (baseNftsEl) {
        const count = nftCounts.base || 0;
        baseNftsEl.textContent = `${count} NFT${count !== 1 ? 's' : ''}`;
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

// Toggle display mode (crypto vs USD primary)
function toggleDisplayMode() {
    const toggleBtn = document.getElementById('displayToggle');
    const options = toggleBtn.querySelectorAll('.toggle-option');

    if (displayMode === 'crypto') {
        displayMode = 'usd';
        document.body.classList.add('usd-primary');
    } else {
        displayMode = 'crypto';
        document.body.classList.remove('usd-primary');
    }

    // Update toggle button appearance
    options.forEach(opt => {
        opt.classList.toggle('active', opt.dataset.mode === displayMode);
    });
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
    if (portfolioChart) {
        const activeRangeBtn = document.querySelector('.range-btn.active');
        const currentRange = activeRangeBtn ? activeRangeBtn.dataset.range : '7d';
        loadPortfolioHistory(currentRange);
    }

    // Re-render analytics charts with new theme colors
    if (analyticsData) {
        if (coinAllocationChart) {
            renderCoinAllocationChart();
        }
        if (categoryAllocationChart) {
            renderCategoryAllocationChart();
        }
    }
}

function loadSavedTheme() {
    // Load saved theme from localStorage
    const savedTheme = localStorage.getItem('abct-theme') || 'default';
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

// Update price and 1hr change display in summary cards
function updatePriceDisplay() {
    const tokens = [
        { symbol: 'ADA', priceEl: 'adaPrice', changeEl: 'adaChange', mcapEl: 'adaMcap' },
        { symbol: 'BTC', priceEl: 'btcPrice', changeEl: 'btcChange', mcapEl: 'btcMcap' },
        { symbol: 'ETH', priceEl: 'ethPrice', changeEl: 'ethChange', mcapEl: 'ethMcap' },
        { symbol: 'SOL', priceEl: 'solPrice', changeEl: 'solChange', mcapEl: 'solMcap' },
        { symbol: 'MATIC', priceEl: 'maticPrice', changeEl: 'maticChange', mcapEl: 'maticMcap' }
    ];

    for (const { symbol, priceEl, changeEl, mcapEl } of tokens) {
        const priceElement = document.getElementById(priceEl);
        const changeElement = document.getElementById(changeEl);
        const mcapElement = document.getElementById(mcapEl);
        const pd = priceData[symbol];

        if (priceElement && pd) {
            // Format price based on magnitude
            const price = pd.usd || 0;
            if (price >= 1000) {
                priceElement.textContent = `$${price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
            } else if (price >= 1) {
                priceElement.textContent = `$${price.toFixed(2)}`;
            } else {
                priceElement.textContent = `$${price.toFixed(4)}`;
            }
        }

        if (changeElement && pd) {
            const change1h = pd.usd_1h_change || 0;
            const changeText = `${change1h >= 0 ? '+' : ''}${change1h.toFixed(2)}%`;
            changeElement.textContent = changeText;
            // Static colors regardless of theme: green for positive, red for negative
            changeElement.classList.remove('positive', 'negative');
            changeElement.classList.add(change1h >= 0 ? 'positive' : 'negative');
        }

        if (mcapElement && pd) {
            const mcap = pd.market_cap || 0;
            setSafeHTML(mcapElement, mcap > 0 ? `MCap: ${formatMarketCap(mcap)}` : '');
        }
    }
}

// Update total portfolio value display
function updateTotalPortfolioValue() {
    const totalValueEl = document.getElementById('totalPortfolioValue');
    const totalBreakdownEl = document.getElementById('totalBreakdown');

    if (!totalValueEl) return;

    // Calculate wallet value
    const adaWalletValue = walletTotals.ADA * (prices.ADA || 0);
    const btcWalletValue = walletTotals.BTC * (prices.BTC || 0);
    const ethWalletValue = walletTotals.ETH * (prices.ETH || 0);
    const solWalletValue = walletTotals.SOL * (prices.SOL || 0);
    const maticWalletValue = walletTotals.MATIC * (prices.MATIC || 0);
    const baseEthWalletValue = walletTotals.ETH_BASE * (prices.ETH || 0);  // Base uses ETH
    const walletsTotal = adaWalletValue + btcWalletValue + ethWalletValue + solWalletValue + maticWalletValue + baseEthWalletValue;

    // Calculate staking value
    let stakingTotal = 0;
    for (const [token, amount] of Object.entries(stakingTotals)) {
        const price = prices[token] || 0;
        stakingTotal += amount * price;
    }

    // Calculate DeFi tokens value (governance tokens, stablecoins, LP tokens in wallet)
    let defiTotal = 0;
    for (const [token, amount] of Object.entries(defiTotals)) {
        const price = prices[token] || 0;
        defiTotal += amount * price;
    }

    // Exchange value (already in USD)
    const exchangesTotal = exchangeTotals.usd || 0;

    // NFT value (already in USD) - sum of all chains
    const nftsTotal = getNftTotalUsd();

    // Tracked native tokens value (from toggle selections)
    const trackedTokensTotal = trackedTokensValue || 0;

    // Custom tokens value (from toggle selections)
    const customTokensTotal = customTokensValue || 0;

    // Total portfolio value (include tracked native tokens and custom tokens)
    const totalValue = walletsTotal + exchangesTotal + stakingTotal + defiTotal + nftsTotal + trackedTokensTotal + customTokensTotal;

    // Update display
    setSafeHTML(totalValueEl, formatUSDBlur(totalValue));

    if (totalBreakdownEl) {
        const stakingLoading = document.body.classList.contains('staking-loading');
        const defiLoading = document.body.classList.contains('defi-loading');
        const nftLoading = document.body.classList.contains('nft-loading');
        setSafeHTML(totalBreakdownEl, `
            <span class="breakdown-item">Self-Custody: ${formatUSDBlur(walletsTotal)}</span>
            <span class="breakdown-item">Exchanges: ${formatUSDBlur(exchangesTotal)}</span>
            <span class="breakdown-item">Staking: ${formatUSDBlur(stakingTotal)}${stakingLoading ? ' <span class="staking-spinner"></span>' : ''}</span>
            <span class="breakdown-item">DeFi Tokens: ${formatUSDBlur(defiTotal)}${defiLoading ? ' <span class="staking-spinner"></span>' : ''}</span>
            <span class="breakdown-item">NFTs: ${formatUSDBlur(nftsTotal)}${nftLoading ? ' <span class="staking-spinner"></span>' : ''}</span>
            ${trackedTokensTotal > 0 ? `<span class="breakdown-item">Native Tokens: ${formatUSDBlur(trackedTokensTotal)}</span>` : ''}
            ${customTokensTotal > 0 ? `<span class="breakdown-item">Custom Tokens: ${formatUSDBlur(customTokensTotal)}</span>` : ''}
        `);
    }

    // Update loading indicator on total value
    const isLoading = document.body.classList.contains('staking-loading') || document.body.classList.contains('nft-loading') || document.body.classList.contains('defi-loading');
    const spinner = totalValueEl.parentElement.querySelector('.total-loading-spinner');
    if (isLoading && !spinner) {
        const spinnerEl = document.createElement('div');
        spinnerEl.className = 'total-loading-spinner';
        spinnerEl.title = 'Loading...';
        totalValueEl.parentElement.appendChild(spinnerEl);
    } else if (!isLoading && spinner) {
        spinner.remove();
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

// Initialize privacy mode from localStorage
function initializePrivacyMode() {
    const privacyEnabled = localStorage.getItem('privacyMode') === 'true';
    if (privacyEnabled) {
        document.body.classList.add('privacy-mode');
        const btn = document.getElementById('privacyBtn');
        if (btn) btn.classList.add('active');
    }
}

// Toggle privacy mode
function togglePrivacyMode() {
    const body = document.body;
    const btn = document.getElementById('privacyBtn');
    const isEnabled = body.classList.toggle('privacy-mode');
    btn.classList.toggle('active');

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
    }
});

// Toggle waffle menu
function toggleWaffleMenu() {
    const menu = document.getElementById('waffleMenu');
    menu.classList.toggle('active');
}

// Close waffle menu when clicking outside
document.addEventListener('click', function(event) {
    const menu = document.getElementById('waffleMenu');
    const btn = document.querySelector('.waffle-menu-btn');
    if (menu && btn && !menu.contains(event.target) && !btn.contains(event.target)) {
        menu.classList.remove('active');
    }
});

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
    if (address.length > 20) {
        return `${address.slice(0, 12)}...${address.slice(-8)}`;
    }
    return address;
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

        // Store wallet totals for portfolio calculation
        walletTotals.ADA = data.cardano.total_ada;
        walletTotals.BTC = data.bitcoin.total_btc;
        walletTotals.ETH = data.ethereum?.total_eth || 0;
        walletTotals.SOL = data.solana?.total_sol || 0;
        walletTotals.MATIC = data.polygon?.total_matic || 0;
        walletTotals.ETH_BASE = data.base?.total_eth || 0;

        // Calculate USD values
        const adaUsd = data.cardano.total_ada * (prices.ADA || 0);
        const btcUsd = data.bitcoin.total_btc * (prices.BTC || 0);
        const ethUsd = (data.ethereum?.total_eth || 0) * (prices.ETH || 0);
        const solUsd = (data.solana?.total_sol || 0) * (prices.SOL || 0);
        const maticUsd = (data.polygon?.total_matic || 0) * (prices.MATIC || 0);
        const baseEthUsd = (data.base?.total_eth || 0) * (prices.ETH || 0);

        // Update Cardano summary
        if (adaBalance) {
            setSafeHTML(adaBalance, formatCryptoBlur(data.cardano.total_ada, 'ADA', 6));
        }
        const adaBalanceUsd = document.getElementById('adaBalanceUsd');
        if (adaBalanceUsd) {
            setSafeHTML(adaBalanceUsd, formatUSDBlur(adaUsd));
        }
        if (cardanoWallets) {
            cardanoWallets.textContent = `${data.cardano.wallet_count} wallet${data.cardano.wallet_count !== 1 ? 's' : ''}`;
        }
        if (cardanoAssets) {
            cardanoAssets.textContent = `${data.cardano.native_assets_count} native asset${data.cardano.native_assets_count !== 1 ? 's' : ''}`;
        }

        // Update Bitcoin summary
        if (btcBalance) {
            setSafeHTML(btcBalance, formatCryptoBlur(data.bitcoin.total_btc.toFixed(8), 'BTC', 8));
        }
        const btcBalanceUsd = document.getElementById('btcBalanceUsd');
        if (btcBalanceUsd) {
            setSafeHTML(btcBalanceUsd, formatUSDBlur(btcUsd));
        }
        if (bitcoinWallets) {
            bitcoinWallets.textContent = `${data.bitcoin.wallet_count} wallet${data.bitcoin.wallet_count !== 1 ? 's' : ''}`;
        }
        // Update Ethereum summary
        if (ethBalance) {
            setSafeHTML(ethBalance, formatCryptoBlur((data.ethereum?.total_eth || 0).toFixed(8), 'ETH', 8));
        }
        const ethBalanceUsd = document.getElementById('ethBalanceUsd');
        if (ethBalanceUsd) {
            setSafeHTML(ethBalanceUsd, formatUSDBlur(ethUsd));
        }
        if (ethereumWallets) {
            ethereumWallets.textContent = `${data.ethereum?.wallet_count || 0} wallet${(data.ethereum?.wallet_count || 0) !== 1 ? 's' : ''}`;
        }
        if (ethereumTokens) {
            ethereumTokens.textContent = `${data.ethereum?.token_count || 0} token${(data.ethereum?.token_count || 0) !== 1 ? 's' : ''}`;
        }

        // Update Solana summary
        const solBalance = document.getElementById('solBalance');
        if (solBalance) {
            setSafeHTML(solBalance, formatCryptoBlur((data.solana?.total_sol || 0).toFixed(9), 'SOL', 9));
        }
        const solBalanceUsd = document.getElementById('solBalanceUsd');
        if (solBalanceUsd) {
            setSafeHTML(solBalanceUsd, formatUSDBlur(solUsd));
        }
        const solanaWallets = document.getElementById('solanaWallets');
        if (solanaWallets) {
            solanaWallets.textContent = `${data.solana?.wallet_count || 0} wallet${(data.solana?.wallet_count || 0) !== 1 ? 's' : ''}`;
        }
        const solanaTokens = document.getElementById('solanaTokens');
        if (solanaTokens) {
            solanaTokens.textContent = `${data.solana?.token_count || 0} token${(data.solana?.token_count || 0) !== 1 ? 's' : ''}`;
        }

        // Update Polygon summary
        const maticBalance = document.getElementById('maticBalance');
        if (maticBalance) {
            setSafeHTML(maticBalance, formatCryptoBlur((data.polygon?.total_matic || 0).toFixed(6), 'POL', 6));
        }
        const maticBalanceUsd = document.getElementById('maticBalanceUsd');
        if (maticBalanceUsd) {
            setSafeHTML(maticBalanceUsd, formatUSDBlur(maticUsd));
        }
        const polygonWallets = document.getElementById('polygonWallets');
        if (polygonWallets) {
            polygonWallets.textContent = `${data.polygon?.wallet_count || 0} wallet${(data.polygon?.wallet_count || 0) !== 1 ? 's' : ''}`;
        }
        const polygonTokens = document.getElementById('polygonTokens');
        if (polygonTokens) {
            polygonTokens.textContent = `${data.polygon?.token_count || 0} token${(data.polygon?.token_count || 0) !== 1 ? 's' : ''}`;
        }

        // Update Base summary (Base uses ETH as native token)
        const baseEthBalance = document.getElementById('baseEthBalance');
        if (baseEthBalance) {
            setSafeHTML(baseEthBalance, formatCryptoBlur((data.base?.total_eth || 0).toFixed(8), 'ETH', 8));
        }
        const baseEthBalanceUsd = document.getElementById('baseEthBalanceUsd');
        if (baseEthBalanceUsd) {
            setSafeHTML(baseEthBalanceUsd, formatUSDBlur(baseEthUsd));
        }
        // Base uses ETH price - copy from Ethereum card
        const baseEthPrice = document.getElementById('baseEthPrice');
        const baseEthChange = document.getElementById('baseEthChange');
        if (baseEthPrice) {
            const ethPriceEl = document.getElementById('ethPrice');
            const ethChangeEl = document.getElementById('ethChange');
            if (ethPriceEl) baseEthPrice.textContent = ethPriceEl.textContent;
            if (ethChangeEl) {
                baseEthChange.textContent = ethChangeEl.textContent;
                baseEthChange.className = ethChangeEl.className;
            }
        }
        const baseWallets = document.getElementById('baseWallets');
        if (baseWallets) {
            baseWallets.textContent = `${data.base?.wallet_count || 0} wallet${(data.base?.wallet_count || 0) !== 1 ? 's' : ''}`;
        }
        const baseTokens = document.getElementById('baseTokens');
        if (baseTokens) {
            baseTokens.textContent = `${data.base?.token_count || 0} token${(data.base?.token_count || 0) !== 1 ? 's' : ''}`;
        }

        // Update wallets section summary - show stake groups count for Cardano
        const stakeGroupCount = data.cardano.stake_groups?.length || 0;
        const ethWalletCount = data.ethereum?.wallet_count || 0;
        const solWalletCount = data.solana?.wallet_count || 0;
        const polygonWalletCount = data.polygon?.wallet_count || 0;
        const baseWalletCount = data.base?.wallet_count || 0;
        const walletsSummary = document.getElementById('walletsSummary');
        if (walletsSummary) {
            let summaryHtml = `
                <span class="chain-count cardano">${stakeGroupCount} Cardano stake key${stakeGroupCount !== 1 ? 's' : ''}</span>
                <span class="chain-count bitcoin">${data.bitcoin.wallet_count} Bitcoin</span>
            `;
            if (ethWalletCount > 0) {
                summaryHtml += `<span class="chain-count ethereum">${ethWalletCount} Ethereum</span>`;
            }
            if (solWalletCount > 0) {
                summaryHtml += `<span class="chain-count solana">${solWalletCount} Solana</span>`;
            }
            if (polygonWalletCount > 0) {
                summaryHtml += `<span class="chain-count polygon">${polygonWalletCount} Polygon</span>`;
            }
            if (baseWalletCount > 0) {
                summaryHtml += `<span class="chain-count base">${baseWalletCount} Base</span>`;
            }
            setSafeHTML(walletsSummary, summaryHtml);
        }

        // Render wallets list with stake groups for Cardano
        renderWalletsGrouped(data.cardano.stake_groups || [], data.bitcoin.wallets || [], data.ethereum?.wallets || [], data.solana?.wallets || [], data.polygon?.wallets || [], data.base?.wallets || []);

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
function renderWalletsGrouped(cardanoStakeGroups, bitcoinWallets, ethereumWallets = [], solanaWallets = [], polygonWallets = [], baseWallets = []) {
    const allEmpty = cardanoStakeGroups.length === 0 && bitcoinWallets.length === 0 && ethereumWallets.length === 0 && solanaWallets.length === 0 && polygonWallets.length === 0 && baseWallets.length === 0;

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
            <div class="blockchain-section cardano collapsed">
                <div class="blockchain-section-header">
                    <div class="blockchain-info">
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
                            <span class="group-label">Stake Key: ${group.stake_address_short || 'No Stake Key'}</span>
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
        const totalAssets = wallets.reduce((sum, w) => sum + (w.native_assets_count || w.token_count || 0), 0);
        const totalNativeAssetsValue = wallets.reduce((sum, w) => sum + (w.native_assets_value_usd || 0), 0);
        const totalUsd = totalBalance * (prices[unit] || 0) + totalNativeAssetsValue;

        const blockchainName = blockchain.charAt(0).toUpperCase() + blockchain.slice(1);

        return `
            <div class="blockchain-section ${blockchain} collapsed">
                <div class="blockchain-section-header">
                    <div class="blockchain-info">
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

    // Use innerHTML directly for internally generated HTML (not user input)
    walletsList.innerHTML = html;

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

    // Edit label button listeners
    document.querySelectorAll('.edit-label-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const address = this.closest('[data-address]').dataset.address;
            editWalletLabel(address, this);
        });
    });

    // Delete wallet button listeners
    document.querySelectorAll('.delete-wallet-btn').forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.stopPropagation();
            const address = this.closest('[data-address]').dataset.address;
            deleteWallet(address);
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
                                <div class="asset-ticker">${ticker}</div>
                                <div class="asset-name-small">${displayName}</div>
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
                <div class="wallet-label-container">
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
                </div>
                <span class="wallet-address">${formatAddress(wallet.address)}</span>
                ${explorerLinks}
            </div>
            <div class="wallet-balance">
                <div class="amount">${formatCryptoBlur(balance, unit)}</div>
                <div class="amount-usd">${formatUSDBlur(usdValue)}</div>
                ${assetsInfo && hasAssets ? `<div class="assets assets-toggle" data-wallet-id="${walletId}">${assetsInfo} ▼</div>` : (assetsInfo ? `<div class="assets">${assetsInfo}</div>` : '')}
            </div>
            ${hasAssets ? `<div class="wallet-assets-list" id="assets-${walletId}" style="display: none;"><div class="loading">Loading assets...</div></div>` : ''}
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
                            ? `<a href="${poolLink}" target="_blank" rel="noopener" class="gov-link">${poolDisplay}</a>`
                            : `<span class="gov-value">${poolDisplay}</span>`
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
                const truncatedId = drepId ? `${drepId.slice(0, 12)}...${drepId.slice(-6)}` : 'Unknown';
                const drepDisplay = gov.drep.drep_name || truncatedId;
                const drepLink = drepId && !isSpecialDrep ? `https://cexplorer.io/drep/${drepId}` : null;
                html += `
                    <div class="gov-item drep">
                        <span class="gov-icon">&#128499;</span>
                        <span class="gov-label">DRep:</span>
                        ${drepLink
                            ? `<a href="${drepLink}" target="_blank" rel="noopener" class="gov-link">${drepDisplay}</a>`
                            : `<span class="gov-value">${drepDisplay}</span>`
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

            return `
                <div class="native-token-item other ${blockchain}">
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

    if (protocols.length === 0) {
        setSafeHTML(stakingPositions, '<p class="empty-state">No staked positions found in DeFi protocols.</p>');
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

    // Update section summary
    if (stakingSummary) {
        let summaryHtml = `
            <span class="staking-status">${protocols.length} protocol${protocols.length !== 1 ? 's' : ''}</span>
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
                    // Use the token symbol as the key
                    const token = pos.asset_name || pos.symbol;
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
        'INDY': 'https://app.indigoprotocol.io/governance',
        'LQ': 'https://app.liqwid.finance/agora',
        'MIN': 'https://app.minswap.org/governance',
        'SUNDAE': 'https://vote.sundaeswap.finance/',
        'STRIKE': 'https://app.strike.finance/governance',
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
    'INDY': { url: 'https://app.indigoprotocol.io/governance', name: 'Indigo' },
    'LQ': { url: 'https://app.liqwid.finance/agora', name: 'Liqwid' },
    'MIN': { url: 'https://app.minswap.org/governance', name: 'Minswap' },
    'SUNDAE': { url: 'https://vote.sundaeswap.finance/', name: 'SundaeSwap' },
    'STRIKE': { url: 'https://app.strike.finance/governance', name: 'Strike' },
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

// Load consolidated DeFi & Governance data
async function loadDefiGovernance() {
    const content = document.getElementById('defiGovernanceContent');
    const summary = document.getElementById('defiGovernanceSummary');

    if (!content) return;

    // Mark as loading
    document.body.classList.add('staking-loading');
    document.body.classList.add('defi-loading');
    updateTotalPortfolioValue();

    setSafeHTML(content, `
        <div class="loading-state">
            <div class="progress-container">
                <div class="progress-bar" id="defiGovProgressBar"></div>
            </div>
            <p class="progress-text" id="defiGovProgressText">Loading DeFi & Governance data...</p>
        </div>
    `);

    const progressBar = document.getElementById('defiGovProgressBar');
    const progressText = document.getElementById('defiGovProgressText');

    try {
        // Get all data in parallel where possible
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

        // Load staking data for each wallet
        if (progressText) progressText.textContent = 'Loading staking positions...';
        if (progressBar) progressBar.style.width = '20%';

        const allStaking = {};
        const totalWallets = cardanoWallets.length;
        let processedWallets = 0;

        for (const wallet of cardanoWallets) {
            const percent = 20 + Math.round((processedWallets / Math.max(totalWallets, 1)) * 60);
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

                    for (const stake of data.staked || []) {
                        if (!allStaking[protocol].staked[stake.token]) {
                            allStaking[protocol].staked[stake.token] = { amount: 0, positions: 0 };
                        }
                        allStaking[protocol].staked[stake.token].amount += stake.amount;
                        allStaking[protocol].staked[stake.token].positions += stake.positions;
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
            processedWallets++;
        }

        if (progressBar) progressBar.style.width = '90%';
        if (progressText) progressText.textContent = 'Rendering...';

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

        // Store DeFi totals for portfolio calculation
        defiTotals = {};
        if (defiData.positions_by_category) {
            for (const [category, positions] of Object.entries(defiData.positions_by_category)) {
                for (const pos of positions) {
                    const token = pos.asset_name || pos.symbol;
                    if (token && pos.quantity) {
                        if (!defiTotals[token]) defiTotals[token] = 0;
                        defiTotals[token] += pos.quantity;
                    }
                }
            }
        }

        // Extract exchange stablecoins (use currency field, not symbol)
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

        // Extract stablecoins from native assets (ETH/SOL chains)
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

        if (progressBar) progressBar.style.width = '100%';

        await new Promise(resolve => setTimeout(resolve, 200));

        // Render the consolidated view
        renderDefiGovernance(allStaking, defiData, exchangeStablecoins, nativeStablecoins);

        document.body.classList.remove('staking-loading');
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading DeFi & Governance:', error);
        setSafeHTML(content, '<p class="empty-state">Error loading DeFi & Governance data.</p>');
        document.body.classList.remove('staking-loading');
        document.body.classList.remove('defi-loading');
        updateTotalPortfolioValue();
    }
}

// Render consolidated DeFi & Governance section
function renderDefiGovernance(allStaking, defiData, exchangeStablecoins, nativeStablecoins = []) {
    const content = document.getElementById('defiGovernanceContent');
    const summary = document.getElementById('defiGovernanceSummary');

    if (!content) return;

    let html = '';
    let totalStakedValue = 0;
    let totalUnstakedValue = 0;
    let totalStableValue = 0;
    let stakedCount = 0;
    let governanceTokenCount = 0;

    // ========================================
    // SECTION 1: STAKED POSITIONS
    // ========================================
    const protocols = Object.keys(allStaking);

    if (protocols.length > 0) {
        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">🔒</span>
                <span class="subsection-title">Staked Positions</span>
            </div>
            <div class="defi-gov-cards">`;

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

                // Chain badge for staked position (default to cardano for now)
                const chainBadge = '<span class="chain-badge cardano" title="Cardano">ADA</span>';

                html += `
                    <div class="defi-gov-card staked">
                        <div class="card-header">
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

        html += `</div></div>`;
    }

    // ========================================
    // SECTION 2: GOVERNANCE TOKENS (Unstaked)
    // ========================================
    const governancePositions = defiData.positions_by_category?.['Governance Tokens'] || [];

    // Chain badge helper for governance tokens
    const getGovChainBadge = (chain) => {
        const badges = {
            'cardano': '<span class="chain-badge cardano" title="Cardano">ADA</span>',
            'ethereum': '<span class="chain-badge ethereum" title="Ethereum">ETH</span>',
            'solana': '<span class="chain-badge solana" title="Solana">SOL</span>'
        };
        return badges[chain] || badges['cardano'];
    };

    if (governancePositions.length > 0) {
        html += `<div class="defi-gov-subsection">
            <div class="defi-gov-subsection-header">
                <span class="subsection-icon">🏛️</span>
                <span class="subsection-title">Governance Tokens (Unstaked)</span>
            </div>
            <div class="defi-gov-list">`;

        // Sort by value descending
        governancePositions.sort((a, b) => {
            const valueA = a.quantity * (prices[a.asset_name] || 0);
            const valueB = b.quantity * (prices[b.asset_name] || 0);
            return valueB - valueA;
        });

        for (const pos of governancePositions) {
            const tokenPrice = prices[pos.asset_name] || 0;
            const usdValue = pos.quantity * tokenPrice;
            totalUnstakedValue += usdValue;
            governanceTokenCount++;

            const govInfo = GOVERNANCE_LINKS[pos.asset_name];
            // Default to cardano for now; can be extended when we support other chains
            const chain = pos.blockchain || 'cardano';

            html += `
                <div class="defi-gov-line">
                    <span class="line-token">${getGovChainBadge(chain)} ${pos.asset_name}</span>
                    <span class="line-amount">${blurValue(pos.quantity_formatted)}</span>
                    <span class="line-value">${usdValue > 0 ? formatUSDBlur(usdValue) : '--'}</span>
                    ${govInfo ? `<a href="${govInfo.url}" target="_blank" rel="noopener" class="gov-vote-link" title="Vote with ${pos.asset_name}">Vote</a>` : '<span class="gov-vote-placeholder"></span>'}
                </div>
            `;
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

            html += `
                <div class="defi-gov-line stable-line">
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
                    <button class="hidden-stables-toggle" onclick="toggleHiddenStables(this)">
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

                html += `
                    <div class="defi-gov-line stable-line hidden-stable">
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
    const otherCategories = ['Liquidity Pool Tokens', 'Staking Receipts', 'Protocol Receipts', 'Synthetic Assets', 'Reserve Tokens', 'Liquid Staking'];

    for (const category of otherCategories) {
        const positions = defiData.positions_by_category?.[category] || [];
        if (positions.length === 0) continue;

        const categoryIcons = {
            'Liquidity Pool Tokens': '💱',
            'Staking Receipts': '📄',
            'Protocol Receipts': '📃',
            'Synthetic Assets': '💵',
            'Reserve Tokens': '🏦',
            'Liquid Staking': '💧'
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
        html = '<p class="empty-state">No DeFi positions or governance tokens found.</p>';
    }

    setSafeHTML(content, html);

    // Update summary
    if (summary) {
        const totalValue = totalStakedValue + totalUnstakedValue + totalStableValue;
        let summaryParts = [];

        if (stakedCount > 0) {
            summaryParts.push(`${stakedCount} staked`);
        }
        if (governanceTokenCount > 0) {
            summaryParts.push(`${governanceTokenCount} gov tokens`);
        }

        setSafeHTML(summary, `
            <span class="defi-gov-count">${summaryParts.join(' · ') || 'No positions'}</span>
            <span class="defi-gov-total">${formatUSDBlur(totalValue)}</span>
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
        await loadDefiGovernance();

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

// Load exchange portfolio data
async function loadExchangeData() {
    const exchangesList = document.getElementById('exchangesList');
    const exchangesSummary = document.getElementById('exchangesSummary');

    if (!exchangesList) return;

    setSafeHTML(exchangesList, '<p class="loading-state">Loading exchange data...</p>');

    try {
        // Check exchange status first
        const statusResponse = await authFetch(`${API_BASE}/exchanges/status`);
        const statusData = await statusResponse.json();

        const coinbaseConfigured = statusData.exchanges?.coinbase?.configured;

        if (!coinbaseConfigured) {
            setSafeHTML(exchangesList, '<p class="empty-state">No exchanges configured. Add cdp_api_key.json for Coinbase.</p>');
            if (exchangesSummary) {
                setSafeHTML(exchangesSummary, '<span class="exchange-status not-configured">Not configured</span>');
            }
            return;
        }

        // Fetch Coinbase portfolio
        const response = await authFetch(`${API_BASE}/exchanges/coinbase`);

        if (!response.ok) {
            const error = await response.json();
            setSafeHTML(exchangesList, `<p class="empty-state error">Error: ${error.detail || 'Failed to load Coinbase data'}</p>`);
            return;
        }

        const data = await response.json();

        // Store exchange total for portfolio calculation
        exchangeTotals.usd = data.total_usd || 0;

        // Update summary
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, `
                <span class="exchange-count">${data.asset_count || 0} assets</span>
                <span class="exchange-total">${formatUSD(data.total_usd || 0)}</span>
            `);
        }

        // Render exchange assets
        renderExchangeAssets(data);

        // Update total portfolio value
        updateTotalPortfolioValue();

    } catch (error) {
        console.error('Error loading exchange data:', error);
        setSafeHTML(exchangesList, '<p class="empty-state error">Failed to load exchange data.</p>');
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, '<span class="exchange-status error">Error</span>');
        }
    }
}

// Render exchange assets
function renderExchangeAssets(data) {
    const exchangesList = document.getElementById('exchangesList');

    if (!data.assets || data.assets.length === 0) {
        setSafeHTML(exchangesList, '<p class="empty-state">No assets with value >= $1.00 found.</p>');
        return;
    }

    // Group by exchange (for future multi-exchange support)
    let html = `
        <div class="exchange-section" data-exchange="coinbase">
            <div class="exchange-header">
                <span class="exchange-icon coinbase">CB</span>
                <span class="exchange-name">Coinbase</span>
                <span class="exchange-value">${formatUSDBlur(data.total_usd)}</span>
            </div>
            <div class="exchange-assets">
    `;

    for (const asset of data.assets) {
        const balance = asset.balance;
        const available = asset.available_balance || balance;
        const held = asset.hold_balance || 0;
        const usdValue = asset.usd_value || 0;
        const price = asset.price || 0;

        // Format balance based on size
        const formatBalance = (val) => {
            if (val >= 1000) {
                return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            } else if (val >= 1) {
                return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
            } else {
                return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 });
            }
        };

        const balanceFormatted = formatBalance(balance);
        const holdInfo = held > 0 ? `<span class="hold-indicator" title="In open orders">(${formatBalance(held)} in orders)</span>` : '';

        html += `
            <div class="exchange-asset-item">
                <div class="asset-info">
                    <span class="asset-currency">${asset.currency}</span>
                    <span class="asset-name-small">${asset.name !== asset.currency ? asset.name : ''}</span>
                </div>
                <div class="asset-balance">
                    <div class="balance-amount">${formatCryptoBlur(balanceFormatted, asset.currency)} ${holdInfo}</div>
                    <div class="balance-usd">${formatUSDBlur(usdValue)}</div>
                </div>
            </div>
        `;
    }

    html += `
            </div>
        </div>
    `;

    setSafeHTML(exchangesList, html);
}

// Load NFTs
async function loadNFTs() {
    const nftsList = document.getElementById('nftsList');
    const nftsSummary = document.getElementById('nftsSummary');

    if (!nftsList) return;

    // Mark NFTs as loading
    document.body.classList.add('nft-loading');
    updateTotalPortfolioValue();

    setSafeHTML(nftsList, '<p class="loading-state">Loading NFTs... (this may take a moment)</p>');

    try {
        const response = await authFetch(`${API_BASE}/nfts`);

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

    try {
        const response = await authFetch(`${API_BASE}/wallets/refresh`, {
            method: 'POST'
        });
        const data = await response.json();

        showStatus(data.message);
        await loadPrices();
        await loadPortfolioSummary();
        // await loadNativeAssets(); // Now in Self-Custody Wallets
        await loadExchangeData();
        await loadDefiGovernance();
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
    const shortAddress = address.length > 20 ? address.slice(0, 10) + '...' + address.slice(-10) : address;
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

    try {
        // Force refresh the portfolio summary
        const response = await authFetch(`${API_BASE}/portfolio/summary?refresh=true`);
        const data = await response.json();

        walletTotals.ADA = data.cardano.total_ada;
        walletTotals.BTC = data.bitcoin.total_btc;
        walletTotals.ETH = data.ethereum?.total_eth || 0;

        // Update summary cards
        const adaUsd = data.cardano.total_ada * (prices.ADA || 0);
        const btcUsd = data.bitcoin.total_btc * (prices.BTC || 0);
        const ethUsd = (data.ethereum?.total_eth || 0) * (prices.ETH || 0);

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

        renderWalletsGrouped(data.cardano.stake_groups || [], data.bitcoin.wallets || [], data.ethereum?.wallets || [], data.solana?.wallets || [], data.polygon?.wallets || []);
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
        // Force refresh by adding refresh=true parameter
        const response = await authFetch(`${API_BASE}/exchanges/coinbase?refresh=true`);

        if (!response.ok) {
            throw new Error('Failed to fetch exchange data');
        }

        const data = await response.json();
        exchangeTotals.usd = data.total_usd || 0;

        const exchangesSummary = document.getElementById('exchangesSummary');
        if (exchangesSummary) {
            setSafeHTML(exchangesSummary, `
                <span class="exchange-count">${data.asset_count || 0} assets</span>
                <span class="exchange-total">${formatUSD(data.total_usd || 0)}</span>
            `);
        }

        renderExchangeAssets(data);
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
                    const token = pos.asset_name || pos.symbol;
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
function switchNFTChain(chain) {
    currentNFTChain = chain;

    // Update tab appearance
    document.querySelectorAll('.nft-chain-tabs .chain-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.chain === chain);
    });

    // Load NFTs for the selected chain
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
    const totalCount = (nftCounts.cardano || 0) + (nftCounts.ethereum || 0) + (nftCounts.solana || 0) + (nftCounts.polygon || 0) + (nftCounts.base || 0);

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
    try {
        const response = await authFetch(`${API_BASE}/nfts/images/config`);
        const config = await response.json();

        imageCacheEnabled = config.enabled || false;

        // Update the toggle checkbox
        const toggle = document.getElementById('imageCacheToggle');
        if (toggle) {
            toggle.checked = imageCacheEnabled;
        }

        console.log('Image cache initialized:', imageCacheEnabled ? 'enabled' : 'disabled');
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

// Sync Cardano NFT floor prices from the external Cardano NFT Price Service
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
        // First check if the service is available
        const statusResponse = await authFetch(`${API_BASE}/nfts/prices/service-status`);
        const statusData = await statusResponse.json();

        if (!statusData.configured) {
            showStatus('Cardano NFT Price Service not configured', true);
            return;
        }

        if (!statusData.available) {
            showStatus('Cardano NFT Price Service is not available', true);
            return;
        }

        // Sync prices
        const response = await authFetch(`${API_BASE}/nfts/prices/sync`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showStatus(`Synced ${data.synced} Cardano floor prices`);
            // Reload NFTs to show updated prices
            if (currentNFTChain === 'cardano') {
                loadNFTs();
            }
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
                const baseStats = document.getElementById('baseNftStats');
                if (baseStats) {
                    baseStats.textContent = 'Not configured';
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

        // Also refresh Ethereum, Solana, Polygon, and Base NFTs
        authFetch(`${API_BASE}/nfts/ethereum?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/solana?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/polygon?force_refresh=true`).catch(() => null);
        authFetch(`${API_BASE}/nfts/base?force_refresh=true`).catch(() => null);

        // Reload all UI components (force refresh for global refresh)
        await loadPortfolioSummary();
        // await loadNativeAssets(true); // Now in Self-Custody Wallets
        await loadExchangeData();
        await loadDefiGovernance();

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
        }

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
// Portfolio History Chart
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
    const adaWalletValue = walletTotals.ADA * (prices.ADA || 0);
    const btcWalletValue = walletTotals.BTC * (prices.BTC || 0);
    const ethWalletValue = walletTotals.ETH * (prices.ETH || 0);
    const solWalletValue = walletTotals.SOL * (prices.SOL || 0);
    const maticWalletValue = walletTotals.MATIC * (prices.MATIC || 0);
    const baseEthWalletValue = walletTotals.ETH_BASE * (prices.ETH || 0);
    const walletsTotal = adaWalletValue + btcWalletValue + ethWalletValue + solWalletValue + maticWalletValue + baseEthWalletValue;

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
    const adaWalletValue = walletTotals.ADA * (prices.ADA || 0);
    const btcWalletValue = walletTotals.BTC * (prices.BTC || 0);
    const ethWalletValue = walletTotals.ETH * (prices.ETH || 0);
    const solWalletValue = walletTotals.SOL * (prices.SOL || 0);
    const maticWalletValue = walletTotals.MATIC * (prices.MATIC || 0);
    const baseEthWalletValue = walletTotals.ETH_BASE * (prices.ETH || 0);
    const walletsTotal = adaWalletValue + btcWalletValue + ethWalletValue + solWalletValue + maticWalletValue + baseEthWalletValue;

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
            // Replace today's value with current live total portfolio value
            const today = new Date().toISOString().split('T')[0];
            const historyData = data.data.map(entry => {
                if (entry.date === today) {
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

            // If today isn't in the data, add it
            const hasToday = historyData.some(entry => entry.date === today);
            if (!hasToday) {
                historyData.push({
                    date: today,
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
            if (emptyState) emptyState.style.display = 'flex';
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

// Get theme colors for chart
function getChartColors() {
    const style = getComputedStyle(document.documentElement);
    const theme = document.documentElement.getAttribute('data-theme') || 'default';

    if (theme === 'cypherpunk1') {
        return {
            lineColor: '#ea00d9',
            fillColor: 'rgba(234, 0, 217, 0.15)',
            pointColor: '#ea00d9',
            pointBorderColor: '#050510',
            gridColor: 'rgba(113, 28, 145, 0.3)',
            tickColor: '#80deea',
            tooltipBg: '#12122a',
            tooltipTitle: '#e0f7fa',
            tooltipBody: '#0abdc6',
            tooltipBorder: '#711c91'
        };
    }

    if (theme === 'ocean-depths') {
        return {
            lineColor: '#00b4d8',
            fillColor: 'rgba(0, 180, 216, 0.15)',
            pointColor: '#00b4d8',
            pointBorderColor: '#0a1628',
            gridColor: 'rgba(26, 74, 110, 0.3)',
            tickColor: '#7ec8e3',
            tooltipBg: '#0d2137',
            tooltipTitle: '#e0f4ff',
            tooltipBody: '#00b4d8',
            tooltipBorder: '#1a4a6e'
        };
    }

    if (theme === 'sunset-horizon') {
        return {
            lineColor: '#ff6b35',
            fillColor: 'rgba(255, 107, 53, 0.15)',
            pointColor: '#ff6b35',
            pointBorderColor: '#1a0a1a',
            gridColor: 'rgba(92, 42, 92, 0.3)',
            tickColor: '#ffb4a2',
            tooltipBg: '#2d1233',
            tooltipTitle: '#ffe4e1',
            tooltipBody: '#ff6b35',
            tooltipBorder: '#5c2a5c'
        };
    }

    // Default theme colors
    return {
        lineColor: '#00d26a',
        fillColor: 'rgba(0, 210, 106, 0.1)',
        pointColor: '#00d26a',
        pointBorderColor: '#1a1a2e',
        gridColor: 'rgba(42, 42, 74, 0.5)',
        tickColor: '#a0a0a0',
        tooltipBg: '#0f3460',
        tooltipTitle: '#eaeaea',
        tooltipBody: '#00d26a',
        tooltipBorder: '#2a2a4a'
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
                pointRadius: 5,
                pointHoverRadius: 10,
                pointBackgroundColor: colors.pointColor,
                pointBorderColor: colors.pointBorderColor,
                pointBorderWidth: 2,
                pointHoverBackgroundColor: colors.lineColor,
                pointHoverBorderColor: '#ffffff',
                pointHoverBorderWidth: 2
            }]
        },
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
                    bodyFont: {
                        size: 18,
                        weight: 'bold'
                    },
                    borderColor: colors.tooltipBorder,
                    borderWidth: 2,
                    padding: 14,
                    displayColors: false,
                    callbacks: {
                        title: function(context) {
                            // Show full date in tooltip
                            const dataIndex = context[0].dataIndex;
                            return historyData[dataIndex].date;
                        },
                        label: function(context) {
                            return formatUSD(context.parsed.y);
                        }
                    }
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
    const buttons = document.querySelectorAll('.range-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Load new range
            loadPortfolioHistory(btn.dataset.range);
        });
    });
}

// Format date for chart display based on range
function formatChartDate(dateStr, range) {
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
// INITIALIZATION
// ============================================================================

// Initial load
document.addEventListener('DOMContentLoaded', async () => {
    // Load saved theme preference
    loadSavedTheme();

    // Initialize privacy mode from localStorage
    initializePrivacyMode();

    // Start monitoring startup status (non-blocking)
    monitorStartupStatus();

    // Initialize NFT image cache toggle state
    await initImageCacheToggle();

    // Initialize portfolio history chart range buttons
    initHistoryRangeButtons();

    // Initialize token form handler
    const tokenForm = document.getElementById('addTokenForm');
    if (tokenForm) {
        tokenForm.addEventListener('submit', handleTokenFormSubmit);
    }

    // ========================================
    // INSTANT LOAD - Show cached data first
    // ========================================
    // Load prices first for USD calculations
    await loadPrices();

    // Load portfolio summary from cache (instant)
    await loadPortfolioSummary();

    // ========================================
    // BACKGROUND UPDATES - Fetch fresh data
    // ========================================
    // These run in background and update UI when complete
    // Use Promise.allSettled to prevent one failure from blocking others
    Promise.allSettled([
        loadExchangeData(),
        loadDefiGovernance(),  // Slow - runs in background now
        loadCustomTokens(),
        loadAllNftSummaries()
    ]).then(() => {
        console.log('[Dashboard] Background data loading complete');
        // Update portfolio total one final time with all fresh data
        updateTotalPortfolioValue();
        // Load portfolio history chart NOW that all data is ready (shows correct current value)
        loadPortfolioHistory('7d');
        // Pre-fetch asset breakdowns for instant modal opening
        prefetchAssetBreakdowns();
    });

    // Load NFTs for the default chain (non-blocking)
    loadNFTs();
});

// ===========================
// Asset Breakdown Modal
// ===========================
let assetBreakdownChart = null;

// Pre-fetch asset breakdown data for all blockchains (cache warming)
async function prefetchAssetBreakdowns() {
    const blockchains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base'];

    // Fire off all requests in parallel (don't wait for responses)
    // This warms the backend cache so modals open instantly
    blockchains.forEach(blockchain => {
        authFetch(`${API_BASE}/portfolio/assets/${blockchain}`)
            .then(r => r.json())
            .catch(e => console.debug(`Pre-fetch ${blockchain} breakdown:`, e));
    });
}

async function openAssetBreakdown(blockchain) {
    try {
        // Open modal immediately with loading state
        const modal = document.getElementById('assetBreakdownModal');
        const chainName = document.getElementById('breakdownChainName');
        const totalValue = document.getElementById('breakdownTotalValue');
        const assetCount = document.getElementById('breakdownAssetCount');
        const legendDiv = document.getElementById('breakdownLegend');

        modal.classList.remove('hidden');
        chainName.textContent = `${blockchain.charAt(0).toUpperCase() + blockchain.slice(1)} Asset Breakdown`;

        // Show loading state
        totalValue.textContent = 'Loading...';
        assetCount.textContent = '...';
        legendDiv.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-secondary);">Loading asset data...</div>';

        // Clear any existing chart
        if (assetBreakdownChart) {
            assetBreakdownChart.destroy();
            assetBreakdownChart = null;
        }

        // Fetch data
        const response = await authFetch(`${API_BASE}/portfolio/assets/${blockchain}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();

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
                    percentage: token.percentage
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
                borderWidth: 2,
                borderColor: getComputedStyle(document.body).getPropertyValue('--bg-primary')
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${context.label}: ${formatUSD(context.parsed)} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderBreakdownLegend(items) {
    const legendDiv = document.getElementById('breakdownLegend');
    legendDiv.innerHTML = items.map(item => `
        <div class="legend-item">
            <div class="legend-label">
                <div class="legend-color" style="background-color: ${item.color};"></div>
                <span class="legend-symbol">${item.symbol}</span>
                <span class="legend-name">${item.name}</span>
            </div>
            <div class="legend-value">
                <div>${formatUSD(item.value_usd)}</div>
                <div class="legend-percentage">${item.percentage.toFixed(1)}%</div>
            </div>
        </div>
    `).join('');
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
    if (assetBreakdownChart) {
        assetBreakdownChart.destroy();
        assetBreakdownChart = null;
    }
}

// ============================================================================
// Analytics Slider
// ============================================================================

let currentAnalyticsSlide = 0;
let coinAllocationChart = null;
let categoryAllocationChart = null;
let analyticsData = null;
let selectedCoinIndex = null;
let selectedCategoryIndex = null;

async function loadAnalyticsData() {
    try {
        const response = await authFetch(`${API_BASE}/portfolio/analytics`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        analyticsData = await response.json();
        renderCoinAllocationChart();
        renderCategoryAllocationChart();
    } catch (error) {
        console.error('Error loading analytics data:', error);
    }
}

function nextAnalyticsSlide() {
    currentAnalyticsSlide = (currentAnalyticsSlide + 1) % 3;
    updateAnalyticsSlide();
}

function previousAnalyticsSlide() {
    currentAnalyticsSlide = (currentAnalyticsSlide - 1 + 3) % 3;
    updateAnalyticsSlide();
}

function goToAnalyticsSlide(index) {
    currentAnalyticsSlide = index;
    updateAnalyticsSlide();
}

function updateAnalyticsSlide() {
    const slides = document.querySelectorAll('.analytics-slide');
    const indicators = document.querySelectorAll('.slider-indicator');
    const slider = document.querySelector('.analytics-slider');

    slides.forEach((slide, index) => {
        if (index === currentAnalyticsSlide) {
            slide.classList.add('active');
        } else {
            slide.classList.remove('active');
        }
    });

    indicators.forEach((indicator, index) => {
        if (index === currentAnalyticsSlide) {
            indicator.classList.add('active');
        } else {
            indicator.classList.remove('active');
        }
    });

    slider.style.transform = `translateX(-${currentAnalyticsSlide * 100}%)`;

    // Load analytics data when switching to chart slides
    if (currentAnalyticsSlide > 0 && !analyticsData) {
        loadAnalyticsData();
    }
}

function renderCoinAllocationChart() {
    if (!analyticsData || !analyticsData.coin_allocation) return;

    const ctx = document.getElementById('coinAllocationChart').getContext('2d');
    if (coinAllocationChart) coinAllocationChart.destroy();

    // Top 6 coins, rest go into "Other"
    const topCoins = analyticsData.coin_allocation.slice(0, 6);
    const remainingCoins = analyticsData.coin_allocation.slice(6);

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

    coinAllocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 3,
                borderColor: 'rgba(0, 0, 0, 0.3)',
                hoverBorderWidth: 4,
                hoverBorderColor: colors.map(c => c) // Same as background for glow effect
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '65%', // Thicker ring for modern look
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    cornerRadius: 8,
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.2)',
                    callbacks: {
                        label: function(context) {
                            const percentage = coins[context.dataIndex].percentage;
                            return `${context.label}: ${formatUSD(context.parsed)} (${percentage.toFixed(2)}%)`;
                        }
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    selectCoinSegment(elements[0].index);
                }
            }
        }
    });

    renderCoinLegend(coins, colors);
}

function selectCoinSegment(index) {
    selectedCoinIndex = index;

    // Get the coin data - handle "Other" aggregation
    const topCoins = analyticsData.coin_allocation.slice(0, 6);
    const remainingCoins = analyticsData.coin_allocation.slice(6);
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

    // Update chart colors for selection effect (brighten selected segment)
    const colors = generateChartColors(coins.length);
    colors[index] = brightenColor(colors[index], 40);

    coinAllocationChart.data.datasets[0].backgroundColor = colors;
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
    legendDiv.innerHTML = coins.map((coin, index) => `
        <div class="analytics-legend-item-compact" onclick="selectCoinSegment(${index})">
            <div class="legend-color-dot-glow" style="background-color: ${colors[index]}; box-shadow: 0 0 8px ${colors[index]};"></div>
            <div class="legend-compact-label">
                <div class="legend-top-row">
                    <span class="legend-symbol">${coin.symbol}</span>
                    <span class="legend-value-inline">${formatUSD(coin.value_usd)}</span>
                </div>
                <span class="legend-percentage-compact">${coin.percentage.toFixed(1)}%</span>
            </div>
        </div>
    `).join('');
}

function renderCategoryAllocationChart() {
    if (!analyticsData || !analyticsData.category_allocation) return;

    const ctx = document.getElementById('categoryAllocationChart').getContext('2d');
    if (categoryAllocationChart) categoryAllocationChart.destroy();

    const categories = analyticsData.category_allocation;
    const labels = categories.map(c => c.category);
    const values = categories.map(c => c.value_usd);
    const colors = generateCategoryColors(categories.length);

    categoryAllocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 3,
                borderColor: 'rgba(0, 0, 0, 0.3)',
                hoverBorderWidth: 4,
                hoverBorderColor: colors.map(c => c) // Same as background for glow effect
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '65%', // Thicker ring for modern look
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    cornerRadius: 8,
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.2)',
                    callbacks: {
                        label: function(context) {
                            const percentage = categories[context.dataIndex].percentage;
                            const tokenCount = categories[context.dataIndex].token_count;
                            return `${context.label}: ${formatUSD(context.parsed)} (${percentage.toFixed(2)}%) - ${tokenCount} tokens`;
                        }
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    selectCategorySegment(elements[0].index);
                }
            }
        }
    });

    renderCategoryLegend(categories, colors);
}

function selectCategorySegment(index) {
    selectedCategoryIndex = index;

    // Update chart colors for selection effect (brighten selected segment)
    const colors = generateCategoryColors(analyticsData.category_allocation.length);
    colors[index] = brightenColor(colors[index], 40);

    categoryAllocationChart.data.datasets[0].backgroundColor = colors;
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
        <div class="analytics-legend-item-compact" onclick="selectCategorySegment(${index})">
            <div class="legend-color-dot-glow" style="background-color: ${colors[index]}; box-shadow: 0 0 8px ${colors[index]};"></div>
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

function generateChartColors(count) {
    const theme = document.documentElement.getAttribute('data-theme') || 'default';

    let baseColors;

    if (theme === 'ocean-depths') {
        // Ocean Depths - Professional aquatic palette
        // Blues → Cyans → Teals → Coral accents (complementary warm)
        baseColors = [
            '#0096c7', // Deep ocean blue
            '#00b4d8', // Bright cyan
            '#48cae4', // Light cyan
            '#90e0ef', // Sky blue
            '#06d6a0', // Teal green
            '#00f5d4', // Aqua
            '#ffd166', // Coral accent
            '#ef476f', // Pink accent
            '#118ab2', // Navy
            '#073b4c'  // Deep teal
        ];
    } else if (theme === 'sunset-horizon') {
        // Sunset Horizon - Warm gradient palette
        // Oranges → Reds → Purples → Magentas (sunset progression)
        baseColors = [
            '#ff6b35', // Vivid orange
            '#f77f00', // Amber
            '#fcbf49', // Golden yellow
            '#d62828', // Deep red
            '#f72585', // Hot pink
            '#b5179e', // Magenta
            '#7209b7', // Purple
            '#560bad', // Deep purple
            '#ff9e00', // Bright orange
            '#e63946'  // Crimson
        ];
    } else if (theme === 'cypherpunk1') {
        // Cypherpunk - High-contrast neon palette
        // Electric greens → Cyans → Magentas (cyberpunk aesthetic)
        baseColors = [
            '#39ff14', // Neon green
            '#00ff41', // Matrix green
            '#adff2f', // Yellow-green
            '#00d9ff', // Electric cyan
            '#0ff0fc', // Bright cyan
            '#00ffff', // Aqua cyan
            '#ff00ff', // Magenta
            '#ff10f0', // Hot magenta
            '#ff1493', // Deep pink
            '#7fff00'  // Chartreuse
        ];
    } else {
        // Default - Balanced professional palette
        // Green → Blues → Reds → Purples → Oranges (diverse, accessible)
        baseColors = [
            '#00d26a', // Emerald green (primary)
            '#3498db', // Bright blue
            '#e74c3c', // Coral red
            '#9b59b6', // Amethyst purple
            '#1abc9c', // Turquoise
            '#f39c12', // Orange
            '#e91e63', // Pink
            '#2ecc71', // Green
            '#3b82f6', // Blue
            '#8b5cf6'  // Purple
        ];
    }

    return baseColors.slice(0, count);
}

function generateCategoryColors(count) {
    const theme = document.documentElement.getAttribute('data-theme') || 'default';

    let categoryColors;

    if (theme === 'ocean-depths') {
        categoryColors = {
            'Layer 1 (L1)': '#0096c7',        // Deep ocean blue
            'Decentralized Finance (DeFi)': '#06d6a0', // Teal green
            'Cardano Ecosystem': '#00b4d8',   // Bright cyan
            'Infrastructure': '#ffd166',       // Coral accent
            'Stablecoins': '#48cae4',         // Light cyan
            'Meme': '#ef476f',                // Pink accent
            'Gaming': '#90e0ef',              // Sky blue
            'Other': '#6c757d'                // Gray
        };
    } else if (theme === 'sunset-horizon') {
        categoryColors = {
            'Layer 1 (L1)': '#ff6b35',        // Vivid orange
            'Decentralized Finance (DeFi)': '#fcbf49', // Golden yellow
            'Cardano Ecosystem': '#f77f00',   // Amber
            'Infrastructure': '#f72585',       // Hot pink
            'Stablecoins': '#d62828',         // Deep red
            'Meme': '#b5179e',                // Magenta
            'Gaming': '#7209b7',              // Purple
            'Other': '#6c757d'                // Gray
        };
    } else if (theme === 'cypherpunk1') {
        categoryColors = {
            'Layer 1 (L1)': '#39ff14',        // Neon green
            'Decentralized Finance (DeFi)': '#00d9ff', // Electric cyan
            'Cardano Ecosystem': '#00ff41',   // Matrix green
            'Infrastructure': '#adff2f',       // Yellow-green
            'Stablecoins': '#0ff0fc',         // Bright cyan
            'Meme': '#ff00ff',                // Magenta
            'Gaming': '#ff10f0',              // Hot magenta
            'Other': '#808080'                // Gray
        };
    } else {
        categoryColors = {
            'Layer 1 (L1)': '#3498db',        // Bright blue
            'Decentralized Finance (DeFi)': '#00d26a', // Emerald green
            'Cardano Ecosystem': '#1abc9c',   // Turquoise
            'Infrastructure': '#f39c12',       // Orange
            'Stablecoins': '#9b59b6',         // Amethyst purple
            'Meme': '#e91e63',                // Pink
            'Gaming': '#8b5cf6',              // Purple
            'Other': '#6b7280'                // Gray
        };
    }

    return analyticsData.category_allocation.map(cat =>
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
