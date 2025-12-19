/**
 * Charts Page - TradingView Widget Integration
 * Displays charts with position levels
 */

let tvWidget = null;
let currentPositions = [];
let currentSymbol = 'BTCUSDT';

document.addEventListener('DOMContentLoaded', () => {
    initializeChart();
    loadOpenPositions();
    setupEventListeners();
});

function initializeChart() {
    const symbol = document.getElementById('chartSymbol').value || 'BTCUSDT';
    currentSymbol = symbol;
    loadTradingViewChart(symbol);
}

function loadTradingViewChart(symbol) {
    const container = document.getElementById('tradingview_chart');
    if (!container) return;

    // Clear existing widget
    container.innerHTML = '';

    // Create new TradingView widget
    tvWidget = new TradingView.widget({
        autosize: true,
        symbol: `BINANCE:${symbol}.P`,
        interval: '15',
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#12121a',
        enable_publishing: false,
        allow_symbol_change: false,
        container_id: 'tradingview_chart',
        hide_side_toolbar: false,
        withdateranges: true,
        save_image: false,
        studies: [],
        overrides: {
            "paneProperties.background": "#0a0a0f",
            "paneProperties.backgroundType": "solid",
            "paneProperties.vertGridProperties.color": "#1e1e24",
            "paneProperties.horzGridProperties.color": "#1e1e24",
            "scalesProperties.textColor": "#a1a1aa",
            "scalesProperties.lineColor": "#27272a",
            "mainSeriesProperties.candleStyle.upColor": "#4ade80",
            "mainSeriesProperties.candleStyle.downColor": "#ef4444",
            "mainSeriesProperties.candleStyle.borderUpColor": "#4ade80",
            "mainSeriesProperties.candleStyle.borderDownColor": "#ef4444",
            "mainSeriesProperties.candleStyle.wickUpColor": "#4ade80",
            "mainSeriesProperties.candleStyle.wickDownColor": "#ef4444"
        }
    });

    // Draw position levels when chart is ready
    if (tvWidget.onChartReady) {
        tvWidget.onChartReady(() => {
            const position = currentPositions.find(p => p.symbol === symbol);
            if (position) {
                drawPositionLevels(position);
            }
        });
    }
}

function drawPositionLevels(position) {
    if (!tvWidget || !position) return;

    try {
        const chart = tvWidget.chart();

        // Clear existing shapes
        chart.removeAllShapes();

        // Entry line (gold)
        if (position.entry_price) {
            chart.createShape(
                { time: Math.floor(Date.now() / 1000), price: position.entry_price },
                {
                    shape: 'horizontal_line',
                    lock: true,
                    disableSelection: true,
                    disableSave: true,
                    disableUndo: true,
                    overrides: {
                        linecolor: '#fbbf24',
                        linewidth: 2,
                        linestyle: 0,
                        showLabel: true,
                        text: `Entry: $${position.entry_price.toFixed(4)}`
                    }
                }
            );
        }

        // Stop loss line (red)
        if (position.stop_price) {
            chart.createShape(
                { time: Math.floor(Date.now() / 1000), price: position.stop_price },
                {
                    shape: 'horizontal_line',
                    lock: true,
                    disableSelection: true,
                    overrides: {
                        linecolor: '#ef4444',
                        linewidth: 2,
                        linestyle: 2,
                        showLabel: true,
                        text: `SL: $${position.stop_price.toFixed(4)}`
                    }
                }
            );
        }

        // Take profit line (green)
        if (position.tp_price) {
            chart.createShape(
                { time: Math.floor(Date.now() / 1000), price: position.tp_price },
                {
                    shape: 'horizontal_line',
                    lock: true,
                    disableSelection: true,
                    overrides: {
                        linecolor: '#22c55e',
                        linewidth: 2,
                        linestyle: 2,
                        showLabel: true,
                        text: `TP: $${position.tp_price.toFixed(4)}`
                    }
                }
            );
        }

    } catch (error) {
        console.error('Error drawing position levels:', error);
    }

    // Update overlay
    updatePositionOverlay(position);
}

function updatePositionOverlay(position) {
    const overlay = document.getElementById('positionOverlay');
    if (!overlay) return;

    if (!position) {
        overlay.style.display = 'none';
        return;
    }

    document.getElementById('overlayEntry').textContent = `$${position.entry_price?.toFixed(4) || '-'}`;
    document.getElementById('overlayStop').textContent = position.stop_price ? `$${position.stop_price.toFixed(4)}` : '-';
    document.getElementById('overlayTP').textContent = position.tp_price ? `$${position.tp_price.toFixed(4)}` : '-';

    const pnl = position.unrealized_pnl || 0;
    const pnlEl = document.getElementById('overlayPnl');
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    pnlEl.className = `level-value ${pnl >= 0 ? 'positive' : 'negative'}`;

    overlay.style.display = 'block';
}

async function loadOpenPositions() {
    try {
        const response = await fetch('/api/positions/all?force=false');
        const data = await response.json();

        if (response.ok) {
            currentPositions = data;
            updatePositionSelector();
        }
    } catch (error) {
        console.error('Error loading positions:', error);
    }
}

function updatePositionSelector() {
    const select = document.getElementById('positionSelect');
    if (!select) return;

    select.innerHTML = '<option value="">Select position...</option>';

    if (currentPositions.length === 0) {
        return;
    }

    currentPositions.forEach(pos => {
        const pnl = pos.unrealized_pnl || 0;
        const pnlStr = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
        select.innerHTML += `
            <option value="${pos.symbol}" data-position='${JSON.stringify(pos)}'>
                ${pos.symbol} ${pos.side} (${pnlStr})
            </option>
        `;
    });
}

function setupEventListeners() {
    // Symbol selector change
    const symbolSelect = document.getElementById('chartSymbol');
    if (symbolSelect) {
        symbolSelect.addEventListener('change', (e) => {
            const symbol = e.target.value;
            currentSymbol = symbol;
            loadTradingViewChart(symbol);

            // Check if there's a position for this symbol
            const position = currentPositions.find(p => p.symbol === symbol);
            if (position) {
                updatePositionOverlay(position);
            } else {
                document.getElementById('positionOverlay').style.display = 'none';
            }
        });
    }

    // Symbol search
    const symbolSearch = document.getElementById('chartSymbolSearch');
    if (symbolSearch) {
        symbolSearch.addEventListener('input', (e) => {
            const search = e.target.value.toUpperCase();
            const options = symbolSelect.options;

            for (let i = 0; i < options.length; i++) {
                const optionValue = options[i].value.toUpperCase();
                if (optionValue.includes(search)) {
                    options[i].style.display = '';
                } else {
                    options[i].style.display = 'none';
                }
            }
        });
    }

    // Position selector change
    const positionSelect = document.getElementById('positionSelect');
    if (positionSelect) {
        positionSelect.addEventListener('change', (e) => {
            const symbol = e.target.value;
            if (!symbol) {
                document.getElementById('positionOverlay').style.display = 'none';
                return;
            }

            // Update symbol selector
            const symbolSelect = document.getElementById('chartSymbol');
            if (symbolSelect) {
                // Check if symbol exists in options
                let found = false;
                for (let option of symbolSelect.options) {
                    if (option.value === symbol) {
                        symbolSelect.value = symbol;
                        found = true;
                        break;
                    }
                }

                // Add if not found
                if (!found) {
                    const option = document.createElement('option');
                    option.value = symbol;
                    option.textContent = symbol;
                    symbolSelect.appendChild(option);
                    symbolSelect.value = symbol;
                }
            }

            currentSymbol = symbol;
            loadTradingViewChart(symbol);

            // Find and show position
            const position = currentPositions.find(p => p.symbol === symbol);
            if (position) {
                // Delay to wait for chart to load
                setTimeout(() => {
                    drawPositionLevels(position);
                }, 1000);
            }
        });
    }
}

// Toast notification (reuse from script.js if available)
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
