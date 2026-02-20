/**
 * Price Chart Widget
 * Displays TradingView Lightweight Charts with blockchain selector and timeframe buttons
 */

let priceChartInstance = null;
let priceChartSeries = null;
let currentBlockchain = 'cardano';
let currentTimeframe = '7D'; // Use uppercase format for API

/**
 * Get theme-specific colors for price chart
 */
function getPriceChartThemeColors(theme) {
    const themes = {
        'default': {
            background: '#1a1d2e',
            text: '#e0e0e0',
            gridLines: 'rgba(255, 255, 255, 0.1)',
            lineColor: '#4CAF50',
            areaTop: 'rgba(76, 175, 80, 0.4)',
            areaBottom: 'rgba(76, 175, 80, 0.0)',
        },
        'cypherpunk1': {
            background: '#030308',
            text: '#8ec8ff',
            gridLines: 'rgba(124, 58, 237, 0.2)',
            lineColor: '#00d4ff',
            areaTop: 'rgba(0, 212, 255, 0.4)',
            areaBottom: 'rgba(0, 212, 255, 0.0)',
        },
        'ocean-depths': {
            background: '#0a1929',
            text: '#b2ebf2',
            gridLines: 'rgba(0, 150, 199, 0.2)',
            lineColor: '#00b4d8',
            areaTop: 'rgba(0, 180, 216, 0.4)',
            areaBottom: 'rgba(0, 180, 216, 0.0)',
        },
        'sunset-horizon': {
            background: '#1a1423',
            text: '#ffd4a3',
            gridLines: 'rgba(255, 107, 107, 0.2)',
            lineColor: '#ff9a56',
            areaTop: 'rgba(255, 154, 86, 0.4)',
            areaBottom: 'rgba(255, 154, 86, 0.0)',
        }
    };

    return themes[theme] || themes['default'];
}

/**
 * Render price chart widget
 */
async function renderPriceChart(container) {
    // Create chart controls and canvas
    const html = `
        <div class="price-chart-container">
            <div class="chart-controls">
                <select id="blockchainSelector" onchange="changePriceChartBlockchain(this.value)">
                    <option value="cardano">Cardano (ADA)</option>
                    <option value="bitcoin">Bitcoin (BTC)</option>
                    <option value="ethereum">Ethereum (ETH)</option>
                    <option value="solana">Solana (SOL)</option>
                    <option value="polygon">Polygon (MATIC)</option>
                </select>
                <button class="timeframe-btn ${currentTimeframe === '1D' ? 'active' : ''}" onclick="changePriceChartTimeframe('1D')">1D</button>
                <button class="timeframe-btn ${currentTimeframe === '7D' ? 'active' : ''}" onclick="changePriceChartTimeframe('7D')">7D</button>
                <button class="timeframe-btn ${currentTimeframe === '3M' ? 'active' : ''}" onclick="changePriceChartTimeframe('3M')">3M</button>
                <button class="timeframe-btn ${currentTimeframe === '1Y' ? 'active' : ''}" onclick="changePriceChartTimeframe('1Y')">1Y</button>
            </div>
            <div id="priceChartCanvas" style="width: 100%; height: 100%;"></div>
        </div>
    `;

    container.innerHTML = html;

    try {
        // Get current theme and colors
        const theme = document.documentElement.getAttribute('data-theme') || 'default';
        const themeColors = getPriceChartThemeColors(theme);

        // Initialize chart
        const chartContainer = container.querySelector('#priceChartCanvas');
        priceChartInstance = LightweightCharts.createChart(chartContainer, {
            layout: {
                background: { color: themeColors.background },
                textColor: themeColors.text,
            },
            grid: {
                vertLines: { color: themeColors.gridLines },
                horzLines: { color: themeColors.gridLines },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: themeColors.gridLines,
            },
            timeScale: {
                borderColor: themeColors.gridLines,
                timeVisible: true,
                secondsVisible: false,
            },
        });

        priceChartSeries = priceChartInstance.addAreaSeries({
            topColor: themeColors.areaTop,
            bottomColor: themeColors.areaBottom,
            lineColor: themeColors.lineColor,
            lineWidth: 2,
        });

        // Load initial data
        await updatePriceChartData();

        // Handle resize
        const resizeObserver = new ResizeObserver(() => {
            if (priceChartInstance && chartContainer) {
                priceChartInstance.applyOptions({
                    width: chartContainer.clientWidth,
                    height: chartContainer.clientHeight
                });
            }
        });
        resizeObserver.observe(chartContainer);

        return {
            container,
            chart: priceChartInstance,
            series: priceChartSeries,
            resizeObserver
        };
    } catch (error) {
        console.error('Price chart error:', error);
        container.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load chart</div>
            </div>
        `;
        throw error;
    }
}

/**
 * Update price chart data
 */
async function updatePriceChartData() {
    try {
        console.log(`[Price Chart Widget] Fetching data for ${currentBlockchain} @ ${currentTimeframe}...`);
        const response = await authFetch(`/portfolio/charts/blockchain/${currentBlockchain}?timeframe=${currentTimeframe}`);
        if (!response.ok) {
            console.error('[Price Chart Widget] Fetch failed:', response.status, response.statusText);
            if (response.status === 401 || response.status === 403) {
                throw new Error('Authentication required - please login');
            }
            throw new Error('Failed to fetch chart data');
        }

        const data = await response.json();
        console.log('[Price Chart Widget] Data received:', data);

        if (data.data && data.data.length > 0) {
            console.log(`[Price Chart Widget] Processing ${data.data.length} data points`);
            // Convert data to TradingView format (data.time is already ISO string)
            const chartData = data.data.map(point => {
                // Convert ISO string to Unix timestamp in seconds
                const timestamp = new Date(point.time).getTime() / 1000;
                return {
                    time: timestamp,
                    value: point.value
                };
            });

            // Sort by time
            chartData.sort((a, b) => a.time - b.time);

            console.log('[Price Chart Widget] Chart data prepared:', chartData.slice(0, 3));

            // Update series
            if (priceChartSeries) {
                priceChartSeries.setData(chartData);
                priceChartInstance.timeScale().fitContent();
                console.log('[Price Chart Widget] Chart updated successfully');
            } else {
                console.error('[Price Chart Widget] Chart series not initialized');
            }
        } else {
            console.warn('[Price Chart Widget] No chart data available:', data);
        }
    } catch (error) {
        console.error('[Price Chart Widget] Error updating chart data:', error);
    }
}

/**
 * Change blockchain
 */
async function changePriceChartBlockchain(blockchain) {
    currentBlockchain = blockchain;
    await updatePriceChartData();
}

/**
 * Change timeframe
 */
async function changePriceChartTimeframe(timeframe) {
    currentTimeframe = timeframe;

    // Update button states
    const buttons = document.querySelectorAll('.timeframe-btn');
    buttons.forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    await updatePriceChartData();
}

/**
 * Refresh price chart
 */
async function refreshPriceChart(instance) {
    if (instance && instance.chart) {
        await updatePriceChartData();
    }
}

/**
 * Destroy price chart widget
 */
function destroyPriceChart(instance) {
    if (instance) {
        if (instance.resizeObserver) {
            instance.resizeObserver.disconnect();
        }
        if (instance.chart) {
            instance.chart.remove();
        }
    }
    priceChartInstance = null;
    priceChartSeries = null;
}
