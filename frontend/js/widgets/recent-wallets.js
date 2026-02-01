/**
 * Recent Wallets Widget
 * Displays top wallets by value from portfolio summary
 */

let recentWalletsCache = null;
let recentWalletsInterval = null;

/**
 * Render recent wallets widget
 */
async function renderRecentWallets(container) {
    container.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        const data = await fetchRecentWallets();
        updateRecentWalletsUI(container, data);

        // Auto-refresh every 5 minutes
        recentWalletsInterval = setInterval(async () => {
            try {
                const refreshedData = await fetchRecentWallets();
                updateRecentWalletsUI(container, refreshedData);
            } catch (error) {
                console.error('Recent wallets refresh error:', error);
            }
        }, 5 * 60 * 1000);

        return { container, interval: recentWalletsInterval };
    } catch (error) {
        console.error('Recent wallets error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load wallet data</div>
            </div>
        `;
        throw error;
    }
}

/**
 * Fetch recent wallets data
 */
async function fetchRecentWallets() {
    console.log('[Recent Wallets Widget] Fetching wallet data and prices...');

    // Fetch both portfolio and prices in parallel
    const [portfolioResponse, pricesResponse] = await Promise.all([
        authFetch('/portfolio/summary'),
        authFetch('/prices/all')
    ]);

    if (!portfolioResponse.ok) {
        console.error('[Recent Wallets Widget] Portfolio fetch failed:', portfolioResponse.status, portfolioResponse.statusText);
        if (portfolioResponse.status === 401 || portfolioResponse.status === 403) {
            throw new Error('Authentication required - please login');
        }
        throw new Error('Failed to fetch wallet data');
    }

    if (!pricesResponse.ok) {
        console.error('[Recent Wallets Widget] Prices fetch failed:', pricesResponse.status, pricesResponse.statusText);
        throw new Error('Failed to fetch prices');
    }

    const portfolioData = await portfolioResponse.json();
    const pricesData = await pricesResponse.json();

    // Extract prices
    const prices = {};
    const rawPrices = pricesData.prices || pricesData;
    for (const [symbol, priceData] of Object.entries(rawPrices)) {
        prices[symbol] = priceData.usd || 0;
    }

    // Store prices globally for other widgets to use
    window.pricesCache = prices;

    console.log('[Recent Wallets Widget] Data received:', portfolioData);
    console.log('[Recent Wallets Widget] Prices received:', prices);

    recentWalletsCache = portfolioData;
    return portfolioData;
}

/**
 * Update recent wallets UI
 */
function updateRecentWalletsUI(container, data) {
    console.log('[Recent Wallets Widget] Updating UI with data:', data);

    // Extract wallets from blockchain-grouped data
    const wallets = [];

    // Fetch prices to calculate USD values
    const prices = window.pricesCache || {};

    // Process each blockchain
    const blockchains = ['cardano', 'bitcoin', 'ethereum', 'solana', 'polygon', 'base'];
    for (const blockchain of blockchains) {
        const blockchainData = data[blockchain];
        if (!blockchainData || !blockchainData.wallets) continue;

        // Get price for this blockchain
        let price = 0;
        switch (blockchain) {
            case 'cardano': price = prices.ADA || 0; break;
            case 'bitcoin': price = prices.BTC || 0; break;
            case 'ethereum': price = prices.ETH || 0; break;
            case 'solana': price = prices.SOL || 0; break;
            case 'polygon': price = prices.MATIC || 0; break;
            case 'base': price = prices.ETH || 0; break;
        }

        // Add each wallet
        for (const wallet of blockchainData.wallets) {
            const value = wallet.balance * price;
            if (value > 0) {
                wallets.push({
                    name: wallet.label || wallet.address_short,
                    balance: `${formatBalance(wallet.balance)} ${getBlockchainSymbol(blockchain)}`,
                    value: value,
                    blockchain: blockchain
                });
            }
        }
    }

    // Sort by value descending
    wallets.sort((a, b) => b.value - a.value);

    // Take top 10
    const topWallets = wallets.slice(0, 10);
    console.log('[Recent Wallets Widget] Top wallets:', topWallets);

    let html = '<div class="wallets-list">';

    if (topWallets.length === 0) {
        html += `
            <div style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                No wallet data available
            </div>
        `;
    } else {
        for (const wallet of topWallets) {
            html += `
                <div class="wallet-item">
                    <div class="wallet-info">
                        <div class="wallet-name">${wallet.name}</div>
                        <div class="wallet-balance" data-privacy>${wallet.balance}</div>
                    </div>
                    <div class="wallet-value" data-privacy>$${formatWalletValue(wallet.value)}</div>
                </div>
            `;
        }
    }

    html += '</div>';
    container.innerHTML = html;

    // Apply privacy mode if enabled
    if (typeof applyPrivacyMode === 'function') {
        applyPrivacyMode();
    }
}

/**
 * Refresh recent wallets
 */
async function refreshRecentWallets(instance) {
    if (instance && instance.container) {
        const data = await fetchRecentWallets();
        updateRecentWalletsUI(instance.container, data);
    }
}

/**
 * Destroy recent wallets widget
 */
function destroyRecentWallets(instance) {
    if (recentWalletsInterval) {
        clearInterval(recentWalletsInterval);
        recentWalletsInterval = null;
    }
    if (instance && instance.interval) {
        clearInterval(instance.interval);
    }
}

/**
 * Get blockchain display name
 */
function getBlockchainDisplayName(blockchain) {
    const names = {
        'cardano': 'Cardano',
        'bitcoin': 'Bitcoin',
        'ethereum': 'Ethereum',
        'solana': 'Solana',
        'polygon': 'Polygon',
        'base': 'Base'
    };
    return names[blockchain] || blockchain.charAt(0).toUpperCase() + blockchain.slice(1);
}

/**
 * Get blockchain symbol
 */
function getBlockchainSymbol(blockchain) {
    const symbols = {
        'cardano': 'ADA',
        'bitcoin': 'BTC',
        'ethereum': 'ETH',
        'solana': 'SOL',
        'polygon': 'MATIC',
        'base': 'ETH'
    };
    return symbols[blockchain] || blockchain.toUpperCase();
}

/**
 * Format balance with appropriate decimals
 */
function formatBalance(amount) {
    if (amount === null || amount === undefined) return '0';
    const num = parseFloat(amount);
    if (num >= 1000) {
        return num.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    } else if (num >= 1) {
        return num.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 4
        });
    } else {
        return num.toLocaleString('en-US', {
            minimumFractionDigits: 4,
            maximumFractionDigits: 8
        });
    }
}

/**
 * Format wallet value
 */
function formatWalletValue(value) {
    if (value === null || value === undefined) return '0.00';
    return parseFloat(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
