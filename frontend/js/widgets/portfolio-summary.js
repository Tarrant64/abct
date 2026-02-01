/**
 * Portfolio Summary Widget
 * Displays total portfolio value with breakdown by category
 */

let portfolioSummaryCache = null;
let portfolioSummaryInterval = null;
let pricesCache = null;

/**
 * Render portfolio summary widget
 */
async function renderPortfolioSummary(container) {
    container.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        const data = await fetchPortfolioSummary();
        updatePortfolioSummaryUI(container, data);

        // Auto-refresh every 5 minutes
        portfolioSummaryInterval = setInterval(async () => {
            try {
                const refreshedData = await fetchPortfolioSummary();
                updatePortfolioSummaryUI(container, refreshedData);
            } catch (error) {
                console.error('Portfolio summary refresh error:', error);
            }
        }, 5 * 60 * 1000);

        return { container, interval: portfolioSummaryInterval, data };
    } catch (error) {
        console.error('Portfolio summary error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load portfolio data</div>
                <button onclick="refreshWidget('${container.closest('.grid-stack-item')?.getAttribute('data-widget-id')}')">Retry</button>
            </div>
        `;
        throw error;
    }
}

/**
 * Fetch portfolio summary data
 */
async function fetchPortfolioSummary() {
    console.log('[Portfolio Widget] Fetching summary and prices...');

    // Fetch both portfolio and prices in parallel
    const [portfolioResponse, pricesResponse] = await Promise.all([
        authFetch('/portfolio/summary'),
        authFetch('/prices/all')
    ]);

    if (!portfolioResponse.ok) {
        console.error('[Portfolio Widget] Portfolio fetch failed:', portfolioResponse.status, portfolioResponse.statusText);
        if (portfolioResponse.status === 401 || portfolioResponse.status === 403) {
            throw new Error('Authentication required - please login');
        }
        throw new Error('Failed to fetch portfolio summary');
    }

    if (!pricesResponse.ok) {
        console.error('[Portfolio Widget] Prices fetch failed:', pricesResponse.status, pricesResponse.statusText);
        throw new Error('Failed to fetch prices');
    }

    const portfolioData = await portfolioResponse.json();
    const pricesData = await pricesResponse.json();

    console.log('[Portfolio Widget] Portfolio data received:', portfolioData);
    console.log('[Portfolio Widget] Prices data received:', pricesData);

    // Extract prices from response
    const prices = {};
    const rawPrices = pricesData.prices || pricesData;
    for (const [symbol, priceData] of Object.entries(rawPrices)) {
        prices[symbol] = priceData.usd || 0;
    }

    portfolioSummaryCache = portfolioData;
    pricesCache = prices;

    return { portfolio: portfolioData, prices };
}

/**
 * Update portfolio summary UI
 */
function updatePortfolioSummaryUI(container, data) {
    console.log('[Portfolio Widget] Updating UI with data:', data);

    const portfolio = data.portfolio || data;
    const prices = data.prices || pricesCache || {};

    // Calculate wallet values by blockchain
    const adaValue = (portfolio.cardano?.total_ada || 0) * (prices.ADA || 0);
    const btcValue = (portfolio.bitcoin?.total_btc || 0) * (prices.BTC || 0);
    const ethValue = (portfolio.ethereum?.total_eth || 0) * (prices.ETH || 0);
    const solValue = (portfolio.solana?.total_sol || 0) * (prices.SOL || 0);
    const maticValue = (portfolio.polygon?.total_matic || 0) * (prices.MATIC || 0);
    const baseValue = (portfolio.base?.total_eth || 0) * (prices.ETH || 0);

    // Calculate native assets values (tokens in wallets)
    const tokensValue =
        (portfolio.cardano?.native_assets_value_usd || 0) +
        (portfolio.ethereum?.native_assets_value_usd || 0) +
        (portfolio.solana?.native_assets_value_usd || 0) +
        (portfolio.polygon?.native_assets_value_usd || 0) +
        (portfolio.base?.native_assets_value_usd || 0);

    // Total wallet value (native coins + tokens)
    const walletsValue = adaValue + btcValue + ethValue + solValue + maticValue + baseValue + tokensValue;

    // Total portfolio value (for now just wallets, could expand to include staking/exchanges/NFTs)
    const totalValue = walletsValue;

    console.log('[Portfolio Widget] Calculated total:', totalValue, 'Breakdown:', {
        wallets: walletsValue,
        tokens: tokensValue
    });

    const html = `
        <div class="portfolio-summary">
            <div class="portfolio-total" data-privacy>
                $${formatNumber(totalValue)}
            </div>
            <div class="portfolio-breakdown">
                ${walletsValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Self-Custody</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(walletsValue)}</div>
                    </div>
                ` : ''}
                ${adaValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Cardano (ADA)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(adaValue)}</div>
                    </div>
                ` : ''}
                ${btcValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Bitcoin (BTC)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(btcValue)}</div>
                    </div>
                ` : ''}
                ${ethValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Ethereum (ETH)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(ethValue)}</div>
                    </div>
                ` : ''}
                ${solValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Solana (SOL)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(solValue)}</div>
                    </div>
                ` : ''}
                ${maticValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Polygon (MATIC)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(maticValue)}</div>
                    </div>
                ` : ''}
                ${baseValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Base (ETH)</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(baseValue)}</div>
                    </div>
                ` : ''}
                ${tokensValue > 0 ? `
                    <div class="breakdown-item">
                        <div class="breakdown-label">Tokens</div>
                        <div class="breakdown-value" data-privacy>$${formatNumber(tokensValue)}</div>
                    </div>
                ` : ''}
            </div>
        </div>
    `;

    container.innerHTML = html;

    // Apply privacy mode if enabled
    if (typeof applyPrivacyMode === 'function') {
        applyPrivacyMode();
    }
}

/**
 * Refresh portfolio summary
 */
async function refreshPortfolioSummary(instance) {
    if (instance && instance.container) {
        const data = await fetchPortfolioSummary();
        updatePortfolioSummaryUI(instance.container, data);
    }
}

/**
 * Destroy portfolio summary widget
 */
function destroyPortfolioSummary(instance) {
    if (portfolioSummaryInterval) {
        clearInterval(portfolioSummaryInterval);
        portfolioSummaryInterval = null;
    }
    if (instance && instance.interval) {
        clearInterval(instance.interval);
    }
}

/**
 * Format number with commas
 */
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return parseFloat(num).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
