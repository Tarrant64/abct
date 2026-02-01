/**
 * Widget Registry
 * Defines all available widgets with their metadata and lifecycle methods
 */

const WIDGET_REGISTRY = {
    'portfolio-summary': {
        title: 'Portfolio Summary',
        defaultSize: { w: 4, h: 3 },
        minSize: { w: 3, h: 2 },
        icon: '💼',
        description: 'Total portfolio value with breakdown',
        render: renderPortfolioSummary,
        refresh: refreshPortfolioSummary,
        destroy: destroyPortfolioSummary
    },
    'blockchain-prices': {
        title: 'Blockchain Prices',
        defaultSize: { w: 4, h: 3 },
        minSize: { w: 3, h: 2 },
        icon: '📊',
        description: 'Live prices for major blockchains',
        render: renderBlockchainPrices,
        refresh: refreshBlockchainPrices,
        destroy: destroyBlockchainPrices
    },
    'price-chart': {
        title: 'Price Chart',
        defaultSize: { w: 6, h: 4 },
        minSize: { w: 4, h: 3 },
        icon: '📈',
        description: 'TradingView price charts',
        render: renderPriceChart,
        refresh: refreshPriceChart,
        destroy: destroyPriceChart
    },
    'recent-wallets': {
        title: 'Recent Wallets',
        defaultSize: { w: 3, h: 4 },
        minSize: { w: 2, h: 3 },
        icon: '👛',
        description: 'Top wallets by value',
        render: renderRecentWallets,
        refresh: refreshRecentWallets,
        destroy: destroyRecentWallets
    },
    'nft-gallery': {
        title: 'NFT Gallery',
        defaultSize: { w: 4, h: 4 },
        minSize: { w: 2, h: 2 },
        icon: '🖼️',
        description: 'Random NFTs from your collection (rotates every 10s)',
        render: renderNFTGallery,
        refresh: refreshNFTGallery,
        destroy: destroyNFTGallery
    },
    'custom-token': {
        title: 'Custom Token Tracker',
        defaultSize: { w: 3, h: 3 },
        minSize: { w: 2, h: 2 },
        icon: '🪙',
        description: 'Track any token by ticker (ADA, SNEK, INDY, etc.)',
        render: renderCustomToken,
        refresh: refreshCustomToken,
        destroy: destroyCustomToken,
        hasConfig: true
    }
};

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WIDGET_REGISTRY };
}
