/**
 * Strategies Page - Manual Trading Strategies
 */

let strategies = [];
let accounts = [];
let refreshIntervals = {};
let editingStrategyId = null;
let pendingTrade = null;
let orderTypes = {};  // Track order type per strategy (MARKET, LIMIT, or BBO)
let pendingLimitOrder = null;  // Store pending limit order data

// DOM Elements
const strategiesGrid = document.getElementById('strategiesGrid');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const strategyCount = document.getElementById('strategyCount');

// Modals
const strategyModal = document.getElementById('strategyModal');
const tradeConfirmModal = document.getElementById('tradeConfirmModal');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadAccounts();
    await loadStrategies();
    setupEventListeners();
});

// Load accounts for dropdown
async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        if (!response.ok) throw new Error('Failed to load accounts');
        accounts = await response.json();
        populateAccountDropdown();
    } catch (error) {
        console.error('Error loading accounts:', error);
        showToast('Failed to load accounts', 'error');
    }
}

// Populate account dropdown
function populateAccountDropdown() {
    const select = document.getElementById('strategyAccount');
    select.innerHTML = '<option value="">Select an account...</option>';

    accounts.forEach(account => {
        const option = document.createElement('option');
        option.value = account.id;
        option.textContent = `${account.name}${account.is_testnet ? ' (Testnet)' : ''}`;
        select.appendChild(option);
    });
}

// Load strategies
async function loadStrategies() {
    try {
        const response = await fetch('/api/strategies');
        if (!response.ok) throw new Error('Failed to load strategies');
        strategies = await response.json();
        renderStrategies();

        // Start refresh intervals for each strategy
        strategies.forEach(s => startStrategyRefresh(s.id));
    } catch (error) {
        console.error('Error loading strategies:', error);
        showToast('Failed to load strategies', 'error');
        loadingState.style.display = 'none';
    }
}

// Render strategies
function renderStrategies() {
    loadingState.style.display = 'none';

    if (strategies.length === 0) {
        strategiesGrid.innerHTML = '';
        emptyState.style.display = 'flex';
        strategyCount.textContent = '0 strategies';
        return;
    }

    emptyState.style.display = 'none';
    strategyCount.textContent = `${strategies.length} quick ${strategies.length === 1 ? 'trade' : 'trades'}`;

    strategiesGrid.innerHTML = strategies.map(createStrategyCard).join('');
}

// Create strategy card HTML
function createStrategyCard(strategy) {
    return `
        <div class="strategy-card" data-strategy-id="${strategy.id}">
            <div class="strategy-collapsed-header" onclick="toggleStrategyCollapse(${strategy.id})">
                <div class="strategy-name">${escapeHtml(strategy.name)}</div>
                <div class="strategy-collapsed-info">
                    <span class="strategy-trend-badge" id="strategyTrendBadge-${strategy.id}">--</span>
                    <span class="strategy-sl-preview" id="strategySlPreview-${strategy.id}">SL: --</span>
                </div>
                <div class="strategy-actions" onclick="event.stopPropagation()">
                    <button class="edit-btn" onclick="editStrategy(${strategy.id})">Edit</button>
                    <button class="delete-btn" onclick="deleteStrategy(${strategy.id})">Delete</button>
                </div>
                <button class="strategy-collapse-btn" onclick="event.stopPropagation(); toggleStrategyCollapse(${strategy.id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </button>
            </div>

            <div class="strategy-card-body" id="strategyCardBody-${strategy.id}">
                <div class="strategy-info">
                    <div class="info-row">
                        <span class="label">Account:</span>
                        <a href="/accounts/${strategy.account_id}" class="value account-link">${escapeHtml(strategy.account_name)}${strategy.is_testnet ? ' (T)' : ''}</a>
                    </div>
                    <div class="info-row">
                        <span class="label">Symbol:</span>
                        <span class="value">${strategy.symbol}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">EMA:</span>
                        <span class="value">${strategy.fast_ema}/${strategy.slow_ema}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Timeframe:</span>
                        <span class="value">${strategy.timeframe}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Risk:</span>
                        <span class="value">${strategy.risk_percent}%</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Leverage:</span>
                        <span class="value">${strategy.leverage}x</span>
                    </div>
                </div>

                <div class="strategy-data" id="strategyData-${strategy.id}">
                    <div class="data-loading">Loading market data...</div>
                </div>

                <div class="order-type-toggle" id="orderTypeToggle-${strategy.id}">
                    <button class="toggle-btn active" data-type="MARKET" onclick="setOrderType(${strategy.id}, 'MARKET')">Market</button>
                    <button class="toggle-btn" data-type="LIMIT" onclick="setOrderType(${strategy.id}, 'LIMIT')">Limit</button>
                    <button class="toggle-btn" data-type="BBO" onclick="setOrderType(${strategy.id}, 'BBO')">BBO</button>
                </div>

                <div class="strategy-buttons">
                    <button class="take-long-btn" id="longBtn-${strategy.id}"
                            onclick="handleTradeClick(${strategy.id}, 'LONG')" disabled>
                        Market Long
                    </button>
                    <button class="take-short-btn" id="shortBtn-${strategy.id}"
                            onclick="handleTradeClick(${strategy.id}, 'SHORT')" disabled>
                        Market Short
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Start auto-refresh for a strategy
function startStrategyRefresh(strategyId) {
    // Clear existing interval if any
    if (refreshIntervals[strategyId]) {
        clearInterval(refreshIntervals[strategyId]);
    }

    // Initial fetch
    fetchStrategyData(strategyId);

    // Set up 30-second interval
    refreshIntervals[strategyId] = setInterval(() => {
        fetchStrategyData(strategyId);
    }, 30000);
}

// Fetch real-time data for a strategy
async function fetchStrategyData(strategyId) {
    const dataContainer = document.getElementById(`strategyData-${strategyId}`);
    if (!dataContainer) return;

    try {
        const response = await fetch(`/api/strategies/${strategyId}/data`);
        const data = await response.json();

        if (!response.ok) {
            dataContainer.innerHTML = `<div class="data-error">${data.error || 'Failed to load data'}</div>`;
            disableTradeButtons(strategyId);
            return;
        }

        // Store data for trade confirmation
        dataContainer.dataset.strategyData = JSON.stringify(data);

        const strategy = strategies.find(s => s.id === strategyId);
        const trendClass = data.trend === 'BULLISH' ? 'trend-bullish' : 'trend-bearish';
        const crossoverIndicator = data.crossover_just_happened ? '<span class="crossover-new">NEW</span>' : '';
        const crossoverTimeDisplay = data.crossover_time ? formatCrossoverTime(data.crossover_time) : '';

        dataContainer.innerHTML = `
            <div class="data-row">
                <span class="label">Price:</span>
                <span class="value price">$${formatPrice(data.current_price)}</span>
            </div>
            <div class="data-row">
                <span class="label">Fast EMA (${strategy.fast_ema}):</span>
                <span class="value">${formatPrice(data.fast_ema)}</span>
            </div>
            <div class="data-row">
                <span class="label">Slow EMA (${strategy.slow_ema}):</span>
                <span class="value">${formatPrice(data.slow_ema)}</span>
            </div>
            <div class="data-row">
                <span class="label">Trend:</span>
                <span class="value ${trendClass}">${data.trend} ${crossoverIndicator}</span>
            </div>
            ${crossoverTimeDisplay ? `<div class="crossover-time">Crossover: ${crossoverTimeDisplay}</div>` : ''}
            <div class="data-row">
                <span class="label">Balance:</span>
                <span class="value">$${data.balance.toFixed(2)}</span>
            </div>
            <div class="data-row">
                <span class="label">Risk Amount:</span>
                <span class="value">$${data.risk_amount.toFixed(2)}</span>
            </div>

            <div class="direction-section">
                <div class="direction-header long">LONG (Crossover SL)</div>
                <div class="data-row">
                    <span class="label">SL:</span>
                    <span class="value">$${formatPrice(data.long.sl_price)} (${data.long.sl_percent.toFixed(2)}%)</span>
                </div>
                <div class="data-row">
                    <span class="label">Size:</span>
                    <span class="value ${data.long.is_valid ? 'valid' : 'invalid'}">$${data.long.position_size.toFixed(2)}</span>
                </div>
                ${!data.long.is_valid ? `<div class="invalid-warning">${data.long.invalid_reason}</div>` : ''}
            </div>

            <div class="direction-section">
                <div class="direction-header short">SHORT (Crossover SL)</div>
                <div class="data-row">
                    <span class="label">SL:</span>
                    <span class="value">$${formatPrice(data.short.sl_price)} (${data.short.sl_percent.toFixed(2)}%)</span>
                </div>
                <div class="data-row">
                    <span class="label">Size:</span>
                    <span class="value ${data.short.is_valid ? 'valid' : 'invalid'}">$${data.short.position_size.toFixed(2)}</span>
                </div>
                ${!data.short.is_valid ? `<div class="invalid-warning">${data.short.invalid_reason}</div>` : ''}
            </div>

            <div class="last-updated">Updated: ${new Date().toLocaleTimeString()}</div>
        `;

        // Enable/disable trade buttons based on validity
        const longBtn = document.getElementById(`longBtn-${strategyId}`);
        const shortBtn = document.getElementById(`shortBtn-${strategyId}`);

        if (longBtn) longBtn.disabled = !data.long.is_valid;
        if (shortBtn) shortBtn.disabled = !data.short.is_valid;

        // Update collapsed header with trend and SL
        const trendBadge = document.getElementById(`strategyTrendBadge-${strategyId}`);
        const slPreview = document.getElementById(`strategySlPreview-${strategyId}`);

        if (trendBadge) {
            trendBadge.textContent = data.trend;
            trendBadge.className = `strategy-trend-badge ${data.trend === 'BULLISH' ? 'trend-bullish' : 'trend-bearish'}`;
        }

        if (slPreview) {
            // Show SL based on trend: SHORT SL when BEARISH, LONG SL when BULLISH
            const slData = data.trend === 'BEARISH' ? data.short : data.long;
            slPreview.textContent = `SL: $${formatPrice(slData.sl_price)}`;
        }

    } catch (error) {
        console.error(`Error fetching data for strategy ${strategyId}:`, error);
        dataContainer.innerHTML = `<div class="data-error">Failed to load market data</div>`;
        disableTradeButtons(strategyId);
    }
}

// Disable trade buttons
function disableTradeButtons(strategyId) {
    const longBtn = document.getElementById(`longBtn-${strategyId}`);
    const shortBtn = document.getElementById(`shortBtn-${strategyId}`);
    if (longBtn) longBtn.disabled = true;
    if (shortBtn) shortBtn.disabled = true;
}

// Set order type for a strategy (Market/Limit toggle)
function setOrderType(strategyId, type) {
    orderTypes[strategyId] = type;

    const toggleContainer = document.getElementById(`orderTypeToggle-${strategyId}`);
    if (toggleContainer) {
        toggleContainer.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === type);
        });
    }

    // Update button text
    updateButtonText(strategyId);
}

// Get order type for a strategy
function getOrderType(strategyId) {
    return orderTypes[strategyId] || 'MARKET';
}

// Toggle collapse state for a strategy card
function toggleStrategyCollapse(strategyId) {
    const card = document.querySelector(`.strategy-card[data-strategy-id="${strategyId}"]`);
    if (card) {
        card.classList.toggle('expanded');
    }
}

// Update trade button text based on order type
function updateButtonText(strategyId) {
    const longBtn = document.getElementById(`longBtn-${strategyId}`);
    const shortBtn = document.getElementById(`shortBtn-${strategyId}`);
    const orderType = getOrderType(strategyId);

    let longText, shortText;

    if (orderType === 'BBO') {
        longText = 'BBO Long';
        shortText = 'BBO Short';
    } else if (orderType === 'LIMIT') {
        longText = 'Limit Long';
        shortText = 'Limit Short';
    } else {
        longText = 'Market Long';
        shortText = 'Market Short';
    }

    if (longBtn) longBtn.textContent = longText;
    if (shortBtn) shortBtn.textContent = shortText;
}

// Handle trade button click - check if Market, Limit, or BBO
function handleTradeClick(strategyId, direction) {
    const orderType = getOrderType(strategyId);

    if (orderType === 'BBO') {
        // BBO queue order - LIMIT order using best bid/ask price
        openTradeConfirm(strategyId, direction, 'LIMIT', null, true);  // true = use BBO
    } else if (orderType === 'LIMIT') {
        openLimitPriceModal(strategyId, direction);
    } else {
        openTradeConfirm(strategyId, direction, 'MARKET', null, false);
    }
}

// Open limit price modal
function openLimitPriceModal(strategyId, direction) {
    const dataContainer = document.getElementById(`strategyData-${strategyId}`);
    if (!dataContainer || !dataContainer.dataset.strategyData) {
        showToast('Market data not loaded', 'error');
        return;
    }

    const strategyData = JSON.parse(dataContainer.dataset.strategyData);
    const strategy = strategies.find(s => s.id === strategyId);

    pendingLimitOrder = { strategyId, direction, strategyData, strategy };

    // Update modal
    document.getElementById('limitPriceModalTitle').textContent = `Enter Limit Price for ${direction}`;
    document.getElementById('limitModalCurrentPrice').textContent = `$${formatPrice(strategyData.current_price)}`;
    document.getElementById('limitPriceInput').value = '';
    document.getElementById('limitCalcPreview').innerHTML = '';

    document.getElementById('limitPriceModal').classList.add('active');
    document.getElementById('limitPriceInput').focus();
}

// Calculate and preview limit order details
function updateLimitPreview() {
    if (!pendingLimitOrder) return;

    const limitPriceInput = document.getElementById('limitPriceInput');
    const limitPrice = parseFloat(limitPriceInput.value);
    const preview = document.getElementById('limitCalcPreview');

    if (!limitPrice || limitPrice <= 0) {
        preview.innerHTML = '';
        return;
    }

    const { direction, strategyData, strategy } = pendingLimitOrder;
    const directionData = direction === 'LONG' ? strategyData.long : strategyData.short;

    // Recalculate SL% based on limit price
    const slPrice = directionData.sl_price;
    const newSlPercent = Math.abs(limitPrice - slPrice) / limitPrice * 100;

    // Recalculate position size
    const riskAmount = strategyData.risk_amount;
    const newPositionSize = riskAmount / (newSlPercent / 100);

    // Check validity
    const isValid = newSlPercent >= strategy.sl_min_percent && newSlPercent <= strategy.sl_max_percent;
    const validClass = isValid ? 'valid' : 'invalid';

    // Calculate potential loss (risk amount is fixed based on account balance * risk%)
    const potentialLoss = riskAmount;

    preview.innerHTML = `
        <div class="preview-row">
            <span class="label">Entry Price:</span>
            <span class="value">$${formatPrice(limitPrice)}</span>
        </div>
        <div class="preview-row">
            <span class="label">Stop Loss:</span>
            <span class="value">$${formatPrice(slPrice)}</span>
        </div>
        <div class="preview-row">
            <span class="label">SL Distance:</span>
            <span class="value ${validClass}">${newSlPercent.toFixed(2)}%</span>
        </div>
        <div class="preview-row">
            <span class="label">Position Size:</span>
            <span class="value highlight">$${newPositionSize.toFixed(2)}</span>
        </div>
        <div class="preview-row">
            <span class="label">Risk Amount:</span>
            <span class="value risk">$${potentialLoss.toFixed(2)}</span>
        </div>
        ${!isValid ? `<div class="preview-warning">SL outside valid range (${strategy.sl_min_percent}% - ${strategy.sl_max_percent}%)</div>` : ''}
    `;

    // Enable/disable continue button
    document.getElementById('confirmLimitPriceBtn').disabled = !isValid;
}

// Confirm limit price and proceed to trade confirmation
function confirmLimitPrice() {
    if (!pendingLimitOrder) return;

    const limitPrice = parseFloat(document.getElementById('limitPriceInput').value);
    if (!limitPrice || limitPrice <= 0) {
        showToast('Please enter a valid limit price', 'error');
        return;
    }

    const { strategyId, direction, strategyData, strategy } = pendingLimitOrder;
    const directionData = direction === 'LONG' ? strategyData.long : strategyData.short;

    // Recalculate values
    const slPrice = directionData.sl_price;
    const newSlPercent = Math.abs(limitPrice - slPrice) / limitPrice * 100;

    // Validate
    if (newSlPercent < strategy.sl_min_percent || newSlPercent > strategy.sl_max_percent) {
        showToast('SL outside valid range', 'error');
        return;
    }

    // Close limit modal
    document.getElementById('limitPriceModal').classList.remove('active');

    // Open trade confirmation with limit order data
    openTradeConfirm(strategyId, direction, 'LIMIT', limitPrice);
}

// Close limit price modal
function closeLimitPriceModal() {
    document.getElementById('limitPriceModal').classList.remove('active');
    pendingLimitOrder = null;
}

// Open trade confirmation modal
function openTradeConfirm(strategyId, direction, orderType = 'MARKET', limitPrice = null, useBbo = false) {
    const dataContainer = document.getElementById(`strategyData-${strategyId}`);
    if (!dataContainer || !dataContainer.dataset.strategyData) {
        showToast('Market data not loaded', 'error');
        return;
    }

    const strategyData = JSON.parse(dataContainer.dataset.strategyData);
    const strategy = strategies.find(s => s.id === strategyId);
    const directionData = direction === 'LONG' ? strategyData.long : strategyData.short;

    // For MARKET orders, check original validity
    // For LIMIT orders, we already validated in confirmLimitPrice()
    if (orderType === 'MARKET' && !directionData.is_valid) {
        showToast('Trade conditions not met', 'error');
        return;
    }

    // Calculate values based on order type
    let entryPrice, slPercent, positionSize;

    if (orderType === 'LIMIT' && limitPrice) {
        entryPrice = limitPrice;
        slPercent = Math.abs(limitPrice - directionData.sl_price) / limitPrice * 100;
        positionSize = strategyData.risk_amount / (slPercent / 100);
    } else {
        entryPrice = strategyData.current_price;
        slPercent = directionData.sl_percent;
        positionSize = directionData.position_size;
    }

    pendingTrade = {
        strategyId,
        direction,
        data: strategyData,
        strategy,
        orderType,
        limitPrice,
        useBbo,
        entryPrice,
        slPercent,
        positionSize
    };

    // Update modal content
    document.getElementById('tradeConfirmTitle').textContent = `Confirm ${direction} Trade`;

    // Order type badge
    const orderTypeBadge = document.getElementById('confirmOrderType');
    const displayOrderType = useBbo ? 'BBO' : orderType;
    orderTypeBadge.textContent = displayOrderType;
    orderTypeBadge.className = `order-type-badge ${displayOrderType.toLowerCase()}`;

    const directionBadge = document.getElementById('confirmDirection');
    directionBadge.textContent = direction;
    directionBadge.className = `direction-badge ${direction.toLowerCase()}`;

    document.getElementById('confirmSymbol').textContent = strategy.symbol;
    document.getElementById('confirmEntry').textContent = `$${formatPrice(entryPrice)}`;
    document.getElementById('confirmSL').textContent = `$${formatPrice(directionData.sl_price)}`;
    document.getElementById('confirmSLPercent').textContent = `${slPercent.toFixed(2)}%`;
    document.getElementById('confirmSize').textContent = `$${positionSize.toFixed(2)}`;
    document.getElementById('confirmRisk').textContent = `$${strategyData.risk_amount.toFixed(2)}`;

    // Update execute button color based on direction
    const executeBtn = document.getElementById('executeTradeBtnConfirm');
    executeBtn.style.background = direction === 'LONG'
        ? 'linear-gradient(135deg, #22c55e, #16a34a)'
        : 'linear-gradient(135deg, #ef4444, #dc2626)';

    tradeConfirmModal.classList.add('active');
}

// Execute trade
async function executeTrade() {
    if (!pendingTrade) return;

    // Save values before they get cleared
    const strategyId = pendingTrade.strategyId;
    const direction = pendingTrade.direction;
    const orderType = pendingTrade.orderType || 'MARKET';
    const limitPrice = pendingTrade.limitPrice;
    const useBbo = pendingTrade.useBbo || false;

    const btn = document.getElementById('executeTradeBtnConfirm');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Executing...';

    try {
        const requestBody = {
            direction: direction,
            order_type: orderType
        };

        // Add limit price if it's a limit order
        if (orderType === 'LIMIT' && limitPrice) {
            requestBody.limit_price = limitPrice;
        }

        // Add use_bbo flag for BBO queue orders
        if (useBbo) {
            requestBody.use_bbo = true;
        }

        const response = await fetch(`/api/strategies/${strategyId}/trade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        console.log('[Quick Trade] Response:', { ok: response.ok, status: response.status, data });

        if (response.ok && data.success) {
            const orderTypeLabel = useBbo ? 'BBO' : (orderType === 'LIMIT' ? 'Limit' : 'Market');
            if (data.warning) {
                // Position opened but SL failed
                showToast(`${orderTypeLabel} ${direction} position opened, but SL failed! Set SL manually.`, 'warning');
            } else {
                showToast(`${orderTypeLabel} ${direction} trade executed successfully!`, 'success');
            }
            closeTradeConfirmModal();
            // Refresh the strategy data
            fetchStrategyData(strategyId);
        } else if (response.ok && !data.success) {
            // Response OK but success flag missing or false
            console.error('[Quick Trade] Response OK but success=false:', data);
            showToast(data.error || data.warning || 'Trade may have executed but response unclear', 'warning');
            closeTradeConfirmModal();
            fetchStrategyData(strategyId);
        } else {
            // HTTP error
            console.error('[Quick Trade] HTTP error:', response.status, data);
            showToast(data.error || `Trade failed (HTTP ${response.status})`, 'error');
        }
    } catch (error) {
        console.error('[Quick Trade] Exception:', error);
        showToast(`Failed to execute trade: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
        pendingTrade = null;
    }
}

// Close trade confirmation modal
function closeTradeConfirmModal() {
    tradeConfirmModal.classList.remove('active');
    pendingTrade = null;
}

// Open strategy modal for adding
function openAddStrategyModal() {
    editingStrategyId = null;
    document.getElementById('strategyModalTitle').textContent = 'Add Strategy';
    clearStrategyForm();
    strategyModal.classList.add('active');
}

// Open strategy modal for editing
function editStrategy(strategyId) {
    const strategy = strategies.find(s => s.id === strategyId);
    if (!strategy) return;

    editingStrategyId = strategyId;
    document.getElementById('strategyModalTitle').textContent = 'Edit Strategy';

    // Populate form
    document.getElementById('strategyName').value = strategy.name;
    document.getElementById('strategyAccount').value = strategy.account_id;
    document.getElementById('strategySymbol').value = strategy.symbol;
    document.getElementById('fastEma').value = strategy.fast_ema;
    document.getElementById('slowEma').value = strategy.slow_ema;
    document.getElementById('riskPercent').value = strategy.risk_percent;
    document.getElementById('leverage').value = strategy.leverage;
    document.getElementById('slLookback').value = strategy.sl_lookback;
    document.getElementById('timeframe').value = strategy.timeframe;
    document.getElementById('slMinPercent').value = strategy.sl_min_percent;
    document.getElementById('slMaxPercent').value = strategy.sl_max_percent;

    strategyModal.classList.add('active');
}

// Clear strategy form
function clearStrategyForm() {
    document.getElementById('strategyName').value = '';
    document.getElementById('strategyAccount').value = '';
    document.getElementById('strategySymbol').value = 'BTCUSDC';
    document.getElementById('fastEma').value = '7';
    document.getElementById('slowEma').value = '19';
    document.getElementById('riskPercent').value = '1.3';
    document.getElementById('leverage').value = '5';
    document.getElementById('slLookback').value = '4';
    document.getElementById('timeframe').value = '30m';
    document.getElementById('slMinPercent').value = '0.25';
    document.getElementById('slMaxPercent').value = '1.81';
}

// Close strategy modal
function closeStrategyModal() {
    strategyModal.classList.remove('active');
    editingStrategyId = null;
}

// Save strategy
async function saveStrategy() {
    const name = document.getElementById('strategyName').value.trim();
    const accountId = document.getElementById('strategyAccount').value;

    if (!name) {
        showToast('Please enter a strategy name', 'error');
        return;
    }
    if (!accountId) {
        showToast('Please select an account', 'error');
        return;
    }

    const strategyData = {
        name,
        account_id: parseInt(accountId),
        symbol: document.getElementById('strategySymbol').value.trim().toUpperCase(),
        fast_ema: parseInt(document.getElementById('fastEma').value),
        slow_ema: parseInt(document.getElementById('slowEma').value),
        risk_percent: parseFloat(document.getElementById('riskPercent').value),
        leverage: parseInt(document.getElementById('leverage').value),
        sl_lookback: parseInt(document.getElementById('slLookback').value),
        timeframe: document.getElementById('timeframe').value,
        sl_min_percent: parseFloat(document.getElementById('slMinPercent').value),
        sl_max_percent: parseFloat(document.getElementById('slMaxPercent').value)
    };

    const btn = document.getElementById('saveStrategyBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
        const url = editingStrategyId
            ? `/api/strategies/${editingStrategyId}`
            : '/api/strategies';
        const method = editingStrategyId ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(strategyData)
        });

        const data = await response.json();

        if (response.ok) {
            showToast(editingStrategyId ? 'Strategy updated!' : 'Strategy created!', 'success');
            closeStrategyModal();

            // Stop old interval if editing
            if (editingStrategyId && refreshIntervals[editingStrategyId]) {
                clearInterval(refreshIntervals[editingStrategyId]);
            }

            // Reload strategies
            await loadStrategies();
        } else {
            showToast(data.error || 'Failed to save strategy', 'error');
        }
    } catch (error) {
        console.error('Error saving strategy:', error);
        showToast('Failed to save strategy', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Strategy';
    }
}

// Delete strategy
async function deleteStrategy(strategyId) {
    const strategy = strategies.find(s => s.id === strategyId);
    if (!confirm(`Delete strategy "${strategy?.name || strategyId}"?`)) return;

    try {
        const response = await fetch(`/api/strategies/${strategyId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('Strategy deleted', 'success');

            // Stop refresh interval
            if (refreshIntervals[strategyId]) {
                clearInterval(refreshIntervals[strategyId]);
                delete refreshIntervals[strategyId];
            }

            // Remove from array and re-render
            strategies = strategies.filter(s => s.id !== strategyId);
            renderStrategies();
        } else {
            const data = await response.json();
            showToast(data.error || 'Failed to delete strategy', 'error');
        }
    } catch (error) {
        console.error('Error deleting strategy:', error);
        showToast('Failed to delete strategy', 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    // Add strategy button
    document.getElementById('addStrategyBtn').addEventListener('click', openAddStrategyModal);

    // Strategy modal
    document.getElementById('closeStrategyModal').addEventListener('click', closeStrategyModal);
    document.getElementById('cancelStrategyBtn').addEventListener('click', closeStrategyModal);
    document.getElementById('saveStrategyBtn').addEventListener('click', saveStrategy);

    // Trade confirm modal
    document.getElementById('closeTradeConfirmModal').addEventListener('click', closeTradeConfirmModal);
    document.getElementById('cancelTradeBtn').addEventListener('click', closeTradeConfirmModal);
    document.getElementById('executeTradeBtnConfirm').addEventListener('click', executeTrade);

    // Limit price modal
    const limitPriceModal = document.getElementById('limitPriceModal');
    document.getElementById('closeLimitPriceModal').addEventListener('click', closeLimitPriceModal);
    document.getElementById('cancelLimitPriceBtn').addEventListener('click', closeLimitPriceModal);
    document.getElementById('confirmLimitPriceBtn').addEventListener('click', confirmLimitPrice);
    document.getElementById('limitPriceInput').addEventListener('input', updateLimitPreview);

    // Close modals on overlay click
    strategyModal.addEventListener('click', (e) => {
        if (e.target === strategyModal) closeStrategyModal();
    });
    tradeConfirmModal.addEventListener('click', (e) => {
        if (e.target === tradeConfirmModal) closeTradeConfirmModal();
    });
    limitPriceModal.addEventListener('click', (e) => {
        if (e.target === limitPriceModal) closeLimitPriceModal();
    });

    // Close modals on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (limitPriceModal.classList.contains('active')) {
                closeLimitPriceModal();
            } else if (tradeConfirmModal.classList.contains('active')) {
                closeTradeConfirmModal();
            } else if (strategyModal.classList.contains('active')) {
                closeStrategyModal();
            }
        }
    });
}

// Helper: Format price
function formatPrice(price) {
    if (price >= 1000) return price.toFixed(2);
    if (price >= 1) return price.toFixed(4);
    return price.toFixed(6);
}

// Helper: Format crossover time
function formatCrossoverTime(timeStr) {
    if (!timeStr || timeStr === 'Just now') return 'Just now';
    try {
        const date = new Date(timeStr);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ${diffMins % 60}m ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    } catch {
        return timeStr;
    }
}

// Helper: Escape HTML
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Helper: Show toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after delay
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    Object.values(refreshIntervals).forEach(clearInterval);
});

// Expose functions for inline onclick handlers
window.setOrderType = setOrderType;
window.handleTradeClick = handleTradeClick;
window.editStrategy = editStrategy;
window.deleteStrategy = deleteStrategy;
