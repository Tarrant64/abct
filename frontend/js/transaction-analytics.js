/**
 * Transaction Analytics - Chart visualization of transaction activity by chain
 */

let analyticsChart = null;
let analyticsData = null;
let selectedChains = new Set();

// Chain colors matching the theme colors from styles.css
const CHAIN_COLORS = {
    'cardano': {
        normal: '#5c9eff',
        faded: 'rgba(92, 158, 255, 0.6)',
        fill: 'rgba(92, 158, 255, 0.3)'
    },
    'ethereum': {
        normal: '#8ba4f5',
        faded: 'rgba(139, 164, 245, 0.6)',
        fill: 'rgba(139, 164, 245, 0.3)'
    },
    'bitcoin': {
        normal: '#ffb74d',
        faded: 'rgba(255, 183, 77, 0.6)',
        fill: 'rgba(255, 183, 77, 0.3)'
    },
    'solana': {
        normal: '#3dffb3',
        faded: 'rgba(61, 255, 179, 0.6)',
        fill: 'rgba(61, 255, 179, 0.3)'
    },
    'polygon': {
        normal: '#a673f0',
        faded: 'rgba(166, 115, 240, 0.6)',
        fill: 'rgba(166, 115, 240, 0.3)'
    },
    'base': {
        normal: '#5c9eff',
        faded: 'rgba(92, 158, 255, 0.6)',
        fill: 'rgba(92, 158, 255, 0.3)'
    }
};

/**
 * Initialize analytics chart
 */
function initAnalyticsChart() {
    const canvas = document.getElementById('analyticsChart');
    if (!canvas) {
        console.error('Analytics chart canvas not found');
        return;
    }

    const ctx = canvas.getContext('2d');

    // Get theme for styling (use getChartColors if available, otherwise fallback)
    const theme = document.documentElement.getAttribute('data-theme') || 'dark-mode';
    const isDarkTheme = theme !== 'light';

    const gridColor = isDarkTheme ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
    const tickColor = isDarkTheme ? '#94a3b8' : '#6b7280';
    const tooltipBg = isDarkTheme ? '#1e293b' : '#ffffff';
    const tooltipBorder = isDarkTheme ? '#334155' : '#e5e7eb';
    const crosshairColor = isDarkTheme ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.15)';

    // Crosshair plugin for hover
    const crosshairPlugin = {
        id: 'analyticsCrosshair',
        afterDraw: (chart) => {
            const activeElements = chart.tooltip?.getActiveElements();
            if (activeElements && activeElements.length > 0) {
                const x = activeElements[0].element.x;
                const yAxis = chart.scales.y;
                const drawCtx = chart.ctx;
                drawCtx.save();
                drawCtx.beginPath();
                drawCtx.setLineDash([4, 4]);
                drawCtx.strokeStyle = crosshairColor;
                drawCtx.lineWidth = 1;
                drawCtx.moveTo(x, yAxis.top);
                drawCtx.lineTo(x, yAxis.bottom);
                drawCtx.stroke();
                drawCtx.restore();
            }
        }
    };

    analyticsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        plugins: [crosshairPlugin],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: false  // We'll use custom chain indicators
                },
                tooltip: {
                    backgroundColor: tooltipBg,
                    titleColor: tickColor,
                    bodyColor: tickColor,
                    borderColor: tooltipBorder,
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y;
                            return `${label}: ${value} transaction${value !== 1 ? 's' : ''}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: tickColor,
                        maxRotation: 45,
                        minRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: tickColor,
                        precision: 0
                    }
                }
            }
        }
    });

    // Load initial data
    loadAnalyticsData();
}

/**
 * Load analytics data from API
 */
async function loadAnalyticsData(days = 30) {
    const loadingEl = document.getElementById('analyticsLoading');
    const emptyEl = document.getElementById('analyticsEmpty');
    const chartContainer = document.getElementById('analyticsChartContainer');

    if (loadingEl) loadingEl.style.display = 'flex';
    if (emptyEl) emptyEl.style.display = 'none';
    if (chartContainer) chartContainer.style.display = 'none';

    try {
        const response = await authFetch(`/transactions/analytics/by-chain?days=${days}`);
        const data = await response.json();

        if (data.success) {
            analyticsData = data;

            if (!data.buckets || data.buckets.length === 0) {
                if (loadingEl) loadingEl.style.display = 'none';
                if (emptyEl) emptyEl.style.display = 'block';
                return;
            }

            renderAnalyticsChart(data);
            renderChainIndicators(data.chains);

            if (loadingEl) loadingEl.style.display = 'none';
            if (chartContainer) chartContainer.style.display = 'block';
        } else {
            throw new Error(data.message || 'Failed to load analytics');
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
        if (loadingEl) loadingEl.style.display = 'none';
        if (emptyEl) {
            emptyEl.style.display = 'block';
            emptyEl.querySelector('p').textContent = 'Error loading analytics data';
        }
    }
}

/**
 * Render chart with analytics data
 */
function renderAnalyticsChart(data) {
    if (!analyticsChart) return;

    const datasets = [];

    // Create dataset for each chain
    const noneSelected = selectedChains.size === 0;

    for (const [chain, counts] of Object.entries(data.chains)) {
        const isSelected = selectedChains.has(chain);
        const colors = CHAIN_COLORS[chain] || {
            normal: '#888',
            faded: 'rgba(136, 136, 136, 0.6)',
            fill: 'rgba(136, 136, 136, 0.3)'
        };

        // When none selected: show all at moderate level
        // When some selected: selected = bold, unselected = very faded
        let borderColor, fillColor, borderWidth, pointRadius, pointHoverRadius;

        if (noneSelected) {
            borderColor = colors.faded;
            fillColor = colors.fill;
            borderWidth = 2;
            pointRadius = 0;
            pointHoverRadius = 0;
        } else if (isSelected) {
            borderColor = colors.normal;
            fillColor = colors.fill;
            borderWidth = 3;
            pointRadius = 0;
            pointHoverRadius = 0;
        } else {
            borderColor = 'rgba(136, 136, 136, 0.15)';
            fillColor = 'rgba(136, 136, 136, 0.03)';
            borderWidth = 1;
            pointRadius = 0;
            pointHoverRadius = 0;
        }

        datasets.push({
            label: formatChainName(chain),
            data: counts,
            borderColor: borderColor,
            backgroundColor: fillColor,
            borderWidth: borderWidth,
            pointRadius: pointRadius,
            pointHoverRadius: pointHoverRadius,
            tension: 0.4,
            fill: true,
            hidden: false
        });
    }

    analyticsChart.data.labels = data.buckets;
    analyticsChart.data.datasets = datasets;
    analyticsChart.update();
}

/**
 * Render chain filter indicators
 */
function renderChainIndicators(chains) {
    const container = document.getElementById('chainIndicators');
    if (!container) return;

    container.innerHTML = '';

    // Always show all supported chains in a specific order
    const allChains = ['cardano', 'ethereum', 'bitcoin', 'solana', 'polygon', 'base'];

    allChains.forEach(chain => {
        const isSelected = selectedChains.has(chain);
        const colors = CHAIN_COLORS[chain] || { normal: '#888' };

        const indicator = document.createElement('button');
        indicator.className = `chain-indicator ${isSelected ? 'active' : ''}`;
        indicator.onclick = () => toggleChain(chain);

        // Create color dot
        const dot = document.createElement('span');
        dot.className = 'chain-indicator-dot';
        dot.style.backgroundColor = colors.normal;

        // Create label
        const label = document.createElement('span');
        label.className = 'chain-indicator-label';
        label.textContent = formatChainName(chain);

        // Create count badge (0 if chain has no data)
        const totalCount = chains[chain]
            ? chains[chain].reduce((sum, count) => sum + count, 0)
            : 0;
        const badge = document.createElement('span');
        badge.className = 'chain-indicator-count';
        badge.textContent = totalCount;

        indicator.appendChild(dot);
        indicator.appendChild(label);
        indicator.appendChild(badge);

        container.appendChild(indicator);
    });
}

/**
 * Toggle chain visibility/highlight
 */
function toggleChain(chain) {
    if (selectedChains.has(chain)) {
        selectedChains.delete(chain);
    } else {
        selectedChains.add(chain);
    }

    // Update chart
    if (analyticsData) {
        renderAnalyticsChart(analyticsData);
    }

    // Update indicators
    const indicators = document.querySelectorAll('.chain-indicator');
    indicators.forEach(indicator => {
        const label = indicator.querySelector('.chain-indicator-label').textContent.toLowerCase();
        const chain = Object.keys(CHAIN_COLORS).find(c => formatChainName(c).toLowerCase() === label);

        if (chain) {
            if (selectedChains.has(chain)) {
                indicator.classList.add('active');
            } else {
                indicator.classList.remove('active');
            }
        }
    });
}

/**
 * Change analytics time period
 */
function changeAnalyticsPeriod(days) {
    // Update active button
    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Reload data
    loadAnalyticsData(days);
}

/**
 * Format chain name for display
 */
function formatChainName(chain) {
    const names = {
        'cardano': 'Cardano',
        'ethereum': 'Ethereum',
        'bitcoin': 'Bitcoin',
        'solana': 'Solana',
        'polygon': 'Polygon',
        'base': 'Base'
    };
    return names[chain] || chain;
}
