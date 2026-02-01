/**
 * DashV2 - Widget-Based Dashboard Controller
 * Manages Gridstack initialization, widget lifecycle, and layout persistence
 */

let grid = null;
let editMode = false;
let widgetInstances = new Map(); // Store widget instances for cleanup
let saveLayoutTimeout = null;

/**
 * Theme management
 */
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

    console.log(`[DashV2] Theme changed to: ${themeName}`);

    // Update all price charts with new theme
    refreshAllPriceCharts();
}

function loadSavedTheme() {
    // Load saved theme from localStorage
    const savedTheme = localStorage.getItem('abct-theme') || 'default';
    changeTheme(savedTheme);
}

/**
 * Refresh all price chart widgets with new theme colors
 */
function refreshAllPriceCharts() {
    widgetInstances.forEach((widgetData, widgetId) => {
        if (widgetData.type === 'price-chart' && widgetData.instance) {
            // Destroy and recreate the chart with new theme
            const element = document.querySelector(`[data-widget-id="${widgetId}"]`);
            if (element) {
                const bodyEl = document.getElementById(`widget-body-${widgetId}`);
                if (bodyEl) {
                    // Re-render the widget
                    const widgetDef = WIDGET_REGISTRY['price-chart'];
                    if (widgetDef) {
                        // Cleanup old chart
                        if (widgetDef.destroy) {
                            widgetDef.destroy(widgetData.instance);
                        }
                        // Render new chart with new theme
                        widgetDef.render(bodyEl).then(instance => {
                            widgetInstances.set(widgetId, { type: 'price-chart', instance });
                        });
                    }
                }
            }
        }
    });
}

// Export for global access
window.changeTheme = changeTheme;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Load theme first (before rendering anything)
        loadSavedTheme();

        // Check authentication first - this will redirect to login if not authenticated
        const isAuthenticated = await checkAuth('/dashv2.html');

        if (!isAuthenticated) {
            // Show login required message (checkAuth will redirect, but show message just in case)
            showLoginRequired();
            return;
        }

        // Verify we have a valid session token
        const token = localStorage.getItem('abct_token');
        if (!token) {
            showLoginRequired();
            return;
        }

        // Get current username for display
        const username = getCurrentUsername();
        console.log(`[DashV2] Authenticated as: ${username}`);

        // Initialize grid
        initGrid();

        // Load saved layout (user-specific)
        await loadLayout();

        // Setup event listeners
        setupEventListeners();

        // Set initial edit mode (View Mode by default)
        setEditMode(false);

        // Hide loading state
        document.getElementById('loadingState').classList.add('hidden');

    } catch (error) {
        console.error('Dashboard initialization error:', error);

        // Check if it's an authentication error
        if (error.message && error.message.includes('auth')) {
            showLoginRequired();
        } else {
            showError('Failed to initialize dashboard');
        }
    }
});

/**
 * Initialize Gridstack instance
 */
function initGrid() {
    grid = GridStack.init({
        column: 12,
        cellHeight: 80,
        minRow: 1,
        margin: 10,
        animate: true,
        float: true,
        disableOneColumnMode: true,
        removable: false,
        acceptWidgets: true
    });

    // Listen for layout changes
    grid.on('change', (event, items) => {
        if (editMode) {
            debounceSaveLayout();
        }
    });

    // Set initial mode to edit
    setEditMode(true);
}

/**
 * Load layout from backend
 */
async function loadLayout() {
    try {
        const response = await authFetch('/api/dashboard/layout');
        const layout = await response.json();

        if (layout && layout.widgets) {
            // Clear existing widgets
            grid.removeAll();
            widgetInstances.clear();

            // Load widgets from layout
            for (const widgetConfig of layout.widgets) {
                addWidgetToGrid(widgetConfig);
            }
        }
    } catch (error) {
        console.error('Error loading layout:', error);
        showNotification('Failed to load layout', 'error');
    }
}

/**
 * Save layout to backend (debounced)
 */
function debounceSaveLayout() {
    if (saveLayoutTimeout) {
        clearTimeout(saveLayoutTimeout);
    }

    saveLayoutTimeout = setTimeout(async () => {
        await saveLayout();
    }, 2000); // Debounce 2 seconds
}

/**
 * Save layout to backend
 */
async function saveLayout() {
    try {
        const widgets = [];
        const items = grid.getGridItems();

        items.forEach(item => {
            const node = item.gridstackNode;
            const widgetType = item.getAttribute('data-widget-type');
            const widgetId = item.getAttribute('data-widget-id');
            const widgetConfigStr = item.getAttribute('data-widget-config');

            const widgetData = {
                id: widgetId,
                type: widgetType,
                x: node.x,
                y: node.y,
                w: node.w,
                h: node.h
            };

            // Include config if present
            if (widgetConfigStr) {
                try {
                    widgetData.config = JSON.parse(widgetConfigStr);
                } catch (e) {
                    console.warn('Failed to parse widget config:', e);
                }
            }

            widgets.push(widgetData);
        });

        const layout = { widgets };

        const response = await authFetch('/api/dashboard/layout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(layout)
        });

        if (response.ok) {
            console.log('Layout saved successfully');
        }
    } catch (error) {
        console.error('Error saving layout:', error);
        showNotification('Failed to save layout', 'error');
    }
}

/**
 * Add widget to grid
 */
function addWidgetToGrid(config) {
    const widgetType = config.type;
    const widgetDef = WIDGET_REGISTRY[widgetType];

    if (!widgetDef) {
        console.error(`Widget type not found: ${widgetType}`);
        return;
    }

    // Create widget container
    const widgetEl = document.createElement('div');
    widgetEl.className = 'grid-stack-item';
    widgetEl.setAttribute('data-widget-type', widgetType);
    widgetEl.setAttribute('data-widget-id', config.id);

    // Store widget config if present
    if (config.config) {
        widgetEl.setAttribute('data-widget-config', JSON.stringify(config.config));
    }

    // Create widget content
    const contentEl = document.createElement('div');
    contentEl.className = 'grid-stack-item-content';

    // Widget header
    const headerEl = document.createElement('div');
    headerEl.className = 'widget-header';
    headerEl.innerHTML = `
        <div class="widget-title">
            <span class="widget-icon">${widgetDef.icon}</span>
            <span>${widgetDef.title}</span>
        </div>
        <button class="widget-remove" onclick="removeWidget('${config.id}')"></button>
    `;

    // Widget body
    const bodyEl = document.createElement('div');
    bodyEl.className = 'widget-body';
    bodyEl.id = `widget-body-${config.id}`;

    contentEl.appendChild(headerEl);
    contentEl.appendChild(bodyEl);
    widgetEl.appendChild(contentEl);

    // Add to grid
    const gridItem = grid.addWidget(widgetEl, {
        x: config.x,
        y: config.y,
        w: config.w,
        h: config.h,
        minW: widgetDef.minSize.w,
        minH: widgetDef.minSize.h,
        id: config.id
    });

    // Render widget content (pass widgetId and config for widgets that need it)
    try {
        const widgetConfig = config.config || {};
        let instance;

        // For widgets that accept widgetId and config (like custom-token)
        if (widgetDef.hasConfig) {
            instance = widgetDef.render(bodyEl, config.id, widgetConfig);
        } else {
            instance = widgetDef.render(bodyEl);
        }

        widgetInstances.set(config.id, { type: widgetType, instance });
    } catch (error) {
        console.error(`Error rendering widget ${widgetType}:`, error);
        bodyEl.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load widget</div>
                <button onclick="refreshWidget('${config.id}')">Retry</button>
            </div>
        `;
    }
}

/**
 * Remove widget from grid
 */
function removeWidget(widgetId) {
    if (!confirm('Remove this widget?')) {
        return;
    }

    // Cleanup widget instance
    const widgetData = widgetInstances.get(widgetId);
    if (widgetData && widgetData.instance) {
        const widgetDef = WIDGET_REGISTRY[widgetData.type];
        if (widgetDef.destroy) {
            widgetDef.destroy(widgetData.instance);
        }
    }
    widgetInstances.delete(widgetId);

    // Remove from grid
    const element = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (element) {
        grid.removeWidget(element);
        saveLayout();
    }
}

/**
 * Refresh widget content
 */
async function refreshWidget(widgetId) {
    const element = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (!element) return;

    const widgetType = element.getAttribute('data-widget-type');
    const widgetDef = WIDGET_REGISTRY[widgetType];
    const bodyEl = document.getElementById(`widget-body-${widgetId}`);

    if (!widgetDef || !bodyEl) return;

    // Show loading state
    bodyEl.innerHTML = '<div class="widget-loading"><div class="spinner"></div></div>';

    try {
        // Cleanup old instance
        const oldInstance = widgetInstances.get(widgetId);
        if (oldInstance && widgetDef.destroy) {
            widgetDef.destroy(oldInstance.instance);
        }

        // Re-render
        const instance = await widgetDef.render(bodyEl);
        widgetInstances.set(widgetId, { type: widgetType, instance });
    } catch (error) {
        console.error(`Error refreshing widget ${widgetType}:`, error);
        bodyEl.innerHTML = `
            <div class="widget-error">
                <div class="widget-error-icon">⚠️</div>
                <div>Failed to load widget</div>
                <button onclick="refreshWidget('${widgetId}')">Retry</button>
            </div>
        `;
    }
}

/**
 * Toggle edit/view mode
 */
function toggleEditMode() {
    const checkbox = document.getElementById('toggleEditMode');
    setEditMode(checkbox.checked);
    saveLayout();
}

/**
 * Set edit mode state
 */
function setEditMode(enabled) {
    editMode = enabled;

    // Update grid
    if (enabled) {
        grid.enable();
        document.body.classList.add('edit-mode');
        document.body.classList.remove('view-mode');
    } else {
        grid.disable();
        document.body.classList.add('view-mode');
        document.body.classList.remove('edit-mode');
    }

    // Update checkbox state
    const checkbox = document.getElementById('toggleEditMode');
    if (checkbox) {
        checkbox.checked = enabled;
    }

    // Show/hide add widget bar
    const addWidgetBar = document.getElementById('addWidgetBar');
    if (addWidgetBar) {
        if (enabled) {
            addWidgetBar.classList.add('visible');
        } else {
            addWidgetBar.classList.remove('visible');
        }
    }
}

/**
 * Open add widget modal
 */
function openAddWidgetModal() {
    const modal = document.getElementById('addWidgetModal');
    const widgetList = document.getElementById('widgetList');

    // Build widget list
    widgetList.innerHTML = '';

    for (const [type, widget] of Object.entries(WIDGET_REGISTRY)) {
        const card = document.createElement('div');
        card.className = 'widget-card';
        card.onclick = () => addWidget(type);
        card.innerHTML = `
            <div class="widget-card-icon">${widget.icon}</div>
            <div class="widget-card-title">${widget.title}</div>
            <div class="widget-card-description">${widget.description}</div>
        `;
        widgetList.appendChild(card);
    }

    modal.classList.remove('hidden');
}

/**
 * Close add widget modal
 */
function closeAddWidgetModal() {
    document.getElementById('addWidgetModal').classList.add('hidden');
}

/**
 * Add new widget
 */
function addWidget(type) {
    const widgetDef = WIDGET_REGISTRY[type];
    if (!widgetDef) return;

    // Generate unique ID
    const widgetId = `widget-${Date.now()}`;

    // Create widget config with default position
    const config = {
        id: widgetId,
        type: type,
        x: 0,
        y: 0,
        w: widgetDef.defaultSize.w,
        h: widgetDef.defaultSize.h
    };

    // Add to grid
    addWidgetToGrid(config);

    // Close modal
    closeAddWidgetModal();

    // Save layout
    saveLayout();
}

/**
 * Reset layout to default
 */
async function resetLayout() {
    if (!confirm('Reset layout to default? This will remove all customizations.')) {
        return;
    }

    try {
        // Clear all widgets
        grid.removeAll();
        widgetInstances.forEach((data, id) => {
            const widgetDef = WIDGET_REGISTRY[data.type];
            if (widgetDef.destroy && data.instance) {
                widgetDef.destroy(data.instance);
            }
        });
        widgetInstances.clear();

        // Load default layout by fetching it fresh
        // The backend will return default if no saved layout exists
        // So we just need to delete the saved layout
        const response = await authFetch('/api/dashboard/layout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ widgets: [] })
        });

        if (response.ok) {
            // Reload page to get default layout
            location.reload();
        }
    } catch (error) {
        console.error('Error resetting layout:', error);
        showNotification('Failed to reset layout', 'error');
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    document.getElementById('toggleEditMode').addEventListener('change', toggleEditMode);
    document.getElementById('addWidgetBtn').addEventListener('click', openAddWidgetModal);
    document.getElementById('resetLayoutBtn').addEventListener('click', resetLayout);
}

/**
 * Show notification (simple toast)
 */
function showNotification(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: ${type === 'error' ? 'var(--danger-color)' : 'var(--accent-color)'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Show login required message
 */
function showLoginRequired() {
    const loadingState = document.getElementById('loadingState');
    loadingState.innerHTML = `
        <div class="widget-error">
            <div class="widget-error-icon">🔒</div>
            <h3 style="margin: 1rem 0 0.5rem 0;">Authentication Required</h3>
            <div style="margin-bottom: 1rem; color: var(--text-secondary);">
                You must be logged in to access the dashboard.
            </div>
            <button onclick="window.location.href='/login.html?redirect=/dashv2.html'" style="
                background: var(--accent-color);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 6px;
                font-size: 1rem;
                cursor: pointer;
                font-weight: 600;
            ">
                Go to Login
            </button>
        </div>
    `;
    loadingState.classList.remove('hidden');

    // Hide the dashboard header and grid
    document.querySelector('.dashv2-header').style.display = 'none';
    document.querySelector('.grid-stack').style.display = 'none';
}

/**
 * Show error message
 */
function showError(message) {
    const loadingState = document.getElementById('loadingState');
    loadingState.innerHTML = `
        <div class="widget-error">
            <div class="widget-error-icon">⚠️</div>
            <div>${message}</div>
            <button onclick="location.reload()">Retry</button>
        </div>
    `;
    loadingState.classList.remove('hidden');
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
