/**
 * NFT Gallery Widget
 * Displays random NFTs from the user's collection, rotating every 10 seconds
 */

let nftGalleryCache = null;
let nftGalleryInterval = null;
let nftRotationInterval = null;
let currentNFTs = [];
let allNFTs = [];

/**
 * Render NFT gallery widget
 */
async function renderNFTGallery(container) {
    container.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        const data = await fetchNFTGallery();

        // Store all NFTs
        allNFTs = data.nfts || [];

        if (allNFTs.length === 0) {
            container.innerHTML = `
                <div class="nft-gallery-empty">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">🖼️</div>
                    <div style="color: var(--text-secondary);">No NFTs found</div>
                </div>
            `;
            return { container };
        }

        // Initial render
        rotateNFTs(container);

        // Auto-rotate every 10 seconds
        nftRotationInterval = setInterval(() => {
            rotateNFTs(container);
        }, 10 * 1000);

        // Refresh data every 5 minutes
        nftGalleryInterval = setInterval(async () => {
            try {
                const refreshedData = await fetchNFTGallery();
                allNFTs = refreshedData.nfts || [];
                if (allNFTs.length > 0) {
                    rotateNFTs(container);
                }
            } catch (error) {
                console.error('NFT gallery refresh error:', error);
            }
        }, 5 * 60 * 1000);

        return { container, rotationInterval: nftRotationInterval, dataInterval: nftGalleryInterval };
    } catch (error) {
        console.error('NFT gallery error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load NFTs</div>
            </div>
        `;
        throw error;
    }
}

/**
 * Fetch NFT gallery data
 */
async function fetchNFTGallery() {
    console.log('[NFT Gallery Widget] Fetching NFTs...');
    const response = await authFetch('/nfts/wall/nfts');
    if (!response.ok) {
        console.error('[NFT Gallery Widget] Fetch failed:', response.status, response.statusText);
        if (response.status === 401 || response.status === 403) {
            throw new Error('Authentication required - please login');
        }
        throw new Error('Failed to fetch NFT data');
    }
    const data = await response.json();
    console.log('[NFT Gallery Widget] Data received:', data);
    nftGalleryCache = data;
    return data;
}

/**
 * Rotate to new random NFTs
 */
function rotateNFTs(container) {
    if (!allNFTs || allNFTs.length === 0) return;

    // Determine grid size based on widget height
    const widgetHeight = container.closest('.grid-stack-item')?.gridstackNode?.h || 3;
    let nftCount = 4; // Default for small widget

    if (widgetHeight >= 6) {
        nftCount = 12; // Large widget: 3x4 grid
    } else if (widgetHeight >= 4) {
        nftCount = 6;  // Medium widget: 2x3 grid
    } else if (widgetHeight >= 3) {
        nftCount = 4;  // Small widget: 2x2 grid
    } else {
        nftCount = 2;  // Tiny widget: 1x2 grid
    }

    // Randomly select NFTs
    const shuffled = [...allNFTs].sort(() => 0.5 - Math.random());
    currentNFTs = shuffled.slice(0, Math.min(nftCount, allNFTs.length));

    console.log(`[NFT Gallery Widget] Rotating to ${currentNFTs.length} random NFTs`);

    updateNFTGalleryUI(container, currentNFTs);
}

/**
 * Update NFT gallery UI
 */
function updateNFTGalleryUI(container, nfts) {
    // Determine grid columns based on number of NFTs
    let gridCols = 2;
    if (nfts.length >= 12) {
        gridCols = 4;
    } else if (nfts.length >= 6) {
        gridCols = 3;
    }

    let html = `<div class="nft-gallery" style="grid-template-columns: repeat(${gridCols}, 1fr);">`;

    for (const nft of nfts) {
        const imageUrl = nft.thumbnail_url || nft.image_url || '';
        const name = nft.name || 'Unnamed NFT';
        const collection = nft.collection || '';
        const floorPrice = nft.floor_price || 0;
        const symbol = nft.native_symbol || '';

        html += `
            <div class="nft-card" title="${name} - ${collection}">
                <div class="nft-image-wrapper">
                    ${imageUrl ? `
                        <img src="${imageUrl}"
                             alt="${name}"
                             class="nft-image"
                             loading="lazy"
                             onerror="this.parentElement.innerHTML='<div class=nft-placeholder>🖼️</div>'">
                    ` : `
                        <div class="nft-placeholder">🖼️</div>
                    `}
                </div>
                <div class="nft-info">
                    <div class="nft-name" title="${name}">${truncateText(name, 15)}</div>
                    ${floorPrice > 0 ? `
                        <div class="nft-price" data-privacy>
                            ${formatNFTPrice(floorPrice)} ${symbol}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;

    // Apply privacy mode if enabled
    if (typeof applyPrivacyMode === 'function') {
        applyPrivacyMode();
    }
}

/**
 * Refresh NFT gallery
 */
async function refreshNFTGallery(instance) {
    if (instance && instance.container) {
        const data = await fetchNFTGallery();
        allNFTs = data.nfts || [];
        if (allNFTs.length > 0) {
            rotateNFTs(instance.container);
        }
    }
}

/**
 * Destroy NFT gallery widget
 */
function destroyNFTGallery(instance) {
    if (nftGalleryInterval) {
        clearInterval(nftGalleryInterval);
        nftGalleryInterval = null;
    }
    if (nftRotationInterval) {
        clearInterval(nftRotationInterval);
        nftRotationInterval = null;
    }
    if (instance) {
        if (instance.rotationInterval) {
            clearInterval(instance.rotationInterval);
        }
        if (instance.dataInterval) {
            clearInterval(instance.dataInterval);
        }
    }
    currentNFTs = [];
    allNFTs = [];
}

/**
 * Format NFT price
 */
function formatNFTPrice(price) {
    if (price === null || price === undefined) return '0';
    if (price >= 1000) {
        return price.toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
    } else if (price >= 1) {
        return price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    } else {
        return price.toLocaleString('en-US', {
            minimumFractionDigits: 4,
            maximumFractionDigits: 6
        });
    }
}

/**
 * Truncate text to max length
 */
function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}
