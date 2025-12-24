/**
 * Dashboard - Positions Management JavaScript
 * Handles positions display and management on the dashboard
 */

// ==================== DASHBOARD POSITIONS ====================

let allPositions = [];
let currentPositionData = null;
let closeOrderType = 'MARKET';  // Track close order type (MARKET or BBO)

// DOM elements for positions
const positionElements = {
    positionsLoading: document.getElementById('positionsLoading'),
    positionsTableWrapper: document.getElementById('positionsTableWrapper'),
    positionsTableBody: document.getElementById('positionsTableBody'),
    emptyPositions: document.getElementById('emptyPositions'),
    positionCount: document.getElementById('positionCount'),
    refreshPositionsBtn: document.getElementById('refreshPositionsBtn'),
    toastContainer: document.getElementById('toastContainer'),
    // Close position modal
    closePositionModal: document.getElementById('closePositionModal'),
    closePositionModalClose: document.getElementById('closePositionModalClose'),
    closePositionSymbol: document.getElementById('closePositionSymbol'),
    closePositionSide: document.getElementById('closePositionSide'),
    closePositionAccount: document.getElementById('closePositionAccount'),
    closePositionSize: document.getElementById('closePositionSize'),
    closePositionPnl: document.getElementById('closePositionPnl'),
    closePercentageSlider: document.getElementById('closePercentageSlider'),
    closePercentageValue: document.getElementById('closePercentageValue'),
    closeQuantityValue: document.getElementById('closeQuantityValue'),
    cancelClosePosition: document.getElementById('cancelClosePosition'),
    confirmClosePosition: document.getElementById('confirmClosePosition'),
    // Stop loss modal
    editStopLossModal: document.getElementById('editStopLossModal'),
    editStopLossModalClose: document.getElementById('editStopLossModalClose'),
    slSymbol: document.getElementById('slSymbol'),
    slSide: document.getElementById('slSide'),
    slAccount: document.getElementById('slAccount'),
    slCurrentStop: document.getElementById('slCurrentStop'),
    newStopPrice: document.getElementById('newStopPrice'),
    slHint: document.getElementById('slHint'),
    removeStopLossBtn: document.getElementById('removeStopLossBtn'),
    cancelEditStopLoss: document.getElementById('cancelEditStopLoss'),
    confirmEditStopLoss: document.getElementById('confirmEditStopLoss'),
    // Take profit modal
    editTakeProfitModal: document.getElementById('editTakeProfitModal'),
    editTakeProfitModalClose: document.getElementById('editTakeProfitModalClose'),
    tpSymbol: document.getElementById('tpSymbol'),
    tpSide: document.getElementById('tpSide'),
    tpAccount: document.getElementById('tpAccount'),
    tpCurrentTP: document.getElementById('tpCurrentTP'),
    newTakeProfitPrice: document.getElementById('newTakeProfitPrice'),
    tpHint: document.getElementById('tpHint'),
    removeTakeProfitBtn: document.getElementById('removeTakeProfitBtn'),
    cancelEditTakeProfit: document.getElementById('cancelEditTakeProfit'),
    confirmEditTakeProfit: document.getElementById('confirmEditTakeProfit'),
    // Add to position modal
    addToPositionModal: document.getElementById('addToPositionModal'),
    closeAddToPositionModal: document.getElementById('closeAddToPositionModal'),
    addPosSymbol: document.getElementById('addPosSymbol'),
    addPosSide: document.getElementById('addPosSide'),
    addPosAccount: document.getElementById('addPosAccount'),
    addPosCurrentSize: document.getElementById('addPosCurrentSize'),
    addPosEntryPrice: document.getElementById('addPosEntryPrice'),
    addPosMarkPrice: document.getElementById('addPosMarkPrice'),
    addPosLeverage: document.getElementById('addPosLeverage'),
    addPosUsdc: document.getElementById('addPosUsdc'),
    addPosCalcQty: document.getElementById('addPosCalcQty'),
    cancelAddToPosition: document.getElementById('cancelAddToPosition'),
    confirmAddToPosition: document.getElementById('confirmAddToPosition')
};

// Load all positions on page load (uses server-side cache)
document.addEventListener('DOMContentLoaded', () => {
    loadAllPositions();  // Uses cached data if < 15 min old
    setupPositionEventListeners();
});

// Setup event listeners for positions
function setupPositionEventListeners() {
    // Refresh button - force refresh from Binance API
    if (positionElements.refreshPositionsBtn) {
        positionElements.refreshPositionsBtn.addEventListener('click', () => loadAllPositions(true));
    }

    // Close position modal
    if (positionElements.closePositionModalClose) {
        positionElements.closePositionModalClose.addEventListener('click', closeClosePositionModal);
    }
    if (positionElements.cancelClosePosition) {
        positionElements.cancelClosePosition.addEventListener('click', closeClosePositionModal);
    }
    if (positionElements.confirmClosePosition) {
        positionElements.confirmClosePosition.addEventListener('click', executeClosePosition);
    }
    if (positionElements.closePositionModal) {
        positionElements.closePositionModal.addEventListener('click', (e) => {
            if (e.target === positionElements.closePositionModal) closeClosePositionModal();
        });
    }

    // Percentage buttons
    document.querySelectorAll('#closePositionModal .pct-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const pct = parseInt(btn.dataset.pct);
            positionElements.closePercentageSlider.value = pct;
            updateCloseQuantity();
        });
    });

    // Slider
    if (positionElements.closePercentageSlider) {
        positionElements.closePercentageSlider.addEventListener('input', () => {
            document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
            updateCloseQuantity();
        });
    }

    // Order type toggle buttons
    document.querySelectorAll('#closeOrderTypeToggle .toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setCloseOrderType(btn.dataset.type);
        });
    });

    // Stop loss modal
    if (positionElements.editStopLossModalClose) {
        positionElements.editStopLossModalClose.addEventListener('click', closeEditStopLossModal);
    }
    if (positionElements.cancelEditStopLoss) {
        positionElements.cancelEditStopLoss.addEventListener('click', closeEditStopLossModal);
    }
    if (positionElements.confirmEditStopLoss) {
        positionElements.confirmEditStopLoss.addEventListener('click', executeUpdateStopLoss);
    }
    if (positionElements.removeStopLossBtn) {
        positionElements.removeStopLossBtn.addEventListener('click', executeRemoveStopLoss);
    }
    if (positionElements.editStopLossModal) {
        positionElements.editStopLossModal.addEventListener('click', (e) => {
            if (e.target === positionElements.editStopLossModal) closeEditStopLossModal();
        });
    }
    // Calculate potential loss on input change
    if (positionElements.newStopPrice) {
        positionElements.newStopPrice.addEventListener('input', calculateStopLossPotentialLoss);
    }

    // Take profit modal
    if (positionElements.editTakeProfitModalClose) {
        positionElements.editTakeProfitModalClose.addEventListener('click', closeEditTakeProfitModal);
    }
    if (positionElements.cancelEditTakeProfit) {
        positionElements.cancelEditTakeProfit.addEventListener('click', closeEditTakeProfitModal);
    }
    if (positionElements.confirmEditTakeProfit) {
        positionElements.confirmEditTakeProfit.addEventListener('click', executeUpdateTakeProfit);
    }
    if (positionElements.removeTakeProfitBtn) {
        positionElements.removeTakeProfitBtn.addEventListener('click', executeRemoveTakeProfit);
    }
    if (positionElements.editTakeProfitModal) {
        positionElements.editTakeProfitModal.addEventListener('click', (e) => {
            if (e.target === positionElements.editTakeProfitModal) closeEditTakeProfitModal();
        });
    }

    // Add to position modal
    if (positionElements.closeAddToPositionModal) {
        positionElements.closeAddToPositionModal.addEventListener('click', closeAddToPositionModal);
    }
    if (positionElements.cancelAddToPosition) {
        positionElements.cancelAddToPosition.addEventListener('click', closeAddToPositionModal);
    }
    if (positionElements.confirmAddToPosition) {
        positionElements.confirmAddToPosition.addEventListener('click', executeAddToPosition);
    }
    if (positionElements.addToPositionModal) {
        positionElements.addToPositionModal.addEventListener('click', (e) => {
            if (e.target === positionElements.addToPositionModal) closeAddToPositionModal();
        });
    }
    // Calculate quantity on USDC input change
    if (positionElements.addPosUsdc) {
        positionElements.addPosUsdc.addEventListener('input', calculateAddPositionQty);
    }
    // Quick percentage buttons for add to position
    document.querySelectorAll('#addToPositionModal .quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (!currentPositionData || !currentPositionData.availableBalance) return;
            const pct = parseInt(btn.dataset.pct);
            const maxUsdc = currentPositionData.availableBalance * currentPositionData.leverage;
            const usdcAmount = (maxUsdc * pct / 100).toFixed(2);
            positionElements.addPosUsdc.value = usdcAmount;
            calculateAddPositionQty();
        });
    });
}

// Load all positions from all accounts
async function loadAllPositions(forceRefresh = false) {
    if (!positionElements.positionsLoading) return;

    positionElements.positionsLoading.style.display = 'flex';
    positionElements.positionsTableWrapper.style.display = 'none';
    positionElements.emptyPositions.style.display = 'none';
    positionElements.refreshPositionsBtn.classList.add('loading');

    try {
        const url = forceRefresh ? '/api/positions/all?force=true' : '/api/positions/all';
        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            allPositions = data;
            renderPositions();
        } else {
            console.error('Error loading positions:', data.error);
            showToast(data.error || 'Failed to load positions', 'error');
        }
    } catch (error) {
        console.error('Error loading positions:', error);
        showToast('Failed to load positions', 'error');
    } finally {
        positionElements.positionsLoading.style.display = 'none';
        positionElements.refreshPositionsBtn.classList.remove('loading');
    }
}

// Render positions table
function renderPositions() {
    positionElements.positionCount.textContent = allPositions.length;

    if (allPositions.length === 0) {
        positionElements.positionsTableWrapper.style.display = 'none';
        positionElements.emptyPositions.style.display = 'flex';
        return;
    }

    positionElements.emptyPositions.style.display = 'none';
    positionElements.positionsTableWrapper.style.display = 'block';

    positionElements.positionsTableBody.innerHTML = allPositions.map(pos => {
        const pnlClass = pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const pnlPrefix = pos.unrealized_pnl >= 0 ? '+' : '';
        const testnetBadge = pos.is_testnet ? '<span class="testnet-badge">TESTNET</span>' : '';
        const sizeInUsd = Math.abs(pos.quantity * pos.mark_price);

        return `
            <tr>
                <td><a href="/accounts/${pos.account_id}" class="account-link">${escapeHtml(pos.account_name)}${testnetBadge}</a></td>
                <td class="symbol">${pos.symbol}</td>
                <td><span class="side ${pos.side.toLowerCase()}">${pos.side}</span></td>
                <td><span class="size-qty">${pos.quantity}</span><span class="size-usd">$${sizeInUsd.toFixed(2)}</span></td>
                <td>${formatPrice(pos.entry_price)}</td>
                <td>${formatPrice(pos.mark_price)}</td>
                <td class="sl-tp-cell">
                    <div class="sl-tp-row">
                        <span class="sl-label">SL:</span>
                        <span class="${pos.stop_price ? 'has-sl' : 'no-sl'}">${pos.stop_price ? formatPrice(pos.stop_price) : '—'}</span>
                        <button class="edit-sl-btn" onclick="openEditStopLossModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.stop_price || 'null'}, ${pos.stop_order_id || 'null'}, '${escapeHtml(pos.account_name)}', ${pos.entry_price})" title="Edit Stop Loss">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="sl-tp-row">
                        <span class="tp-label">TP:</span>
                        <span class="${pos.tp_price ? 'has-tp' : 'no-tp'}">${pos.tp_price ? formatPrice(pos.tp_price) : '—'}</span>
                        <button class="edit-tp-btn" onclick="openEditTakeProfitModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.tp_price || 'null'}, ${pos.tp_order_id || 'null'}, '${escapeHtml(pos.account_name)}')" title="Edit Take Profit">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button>
                    </div>
                </td>
                <td class="${pnlClass}">${pnlPrefix}$${pos.unrealized_pnl.toFixed(2)}</td>
                <td><span class="leverage-badge">${pos.leverage}x</span></td>
                <td class="actions-cell">
                    <button class="add-position-btn" onclick="openAddToPositionModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.entry_price}, ${pos.mark_price}, ${pos.leverage}, '${escapeHtml(pos.account_name)}')">Add</button>
                    <button class="close-position-btn" onclick="openClosePositionModal(${pos.account_id}, '${pos.symbol}', '${pos.side}', ${pos.quantity}, ${pos.unrealized_pnl}, '${escapeHtml(pos.account_name)}')">Close</button>
                </td>
            </tr>
        `;
    }).join('');
}

// Format price for display
function formatPrice(price) {
    if (price >= 1000) return price.toFixed(2);
    if (price >= 1) return price.toFixed(4);
    return price.toFixed(6);
}

// Open close position modal
function openClosePositionModal(accountId, symbol, side, quantity, pnl, accountName) {
    currentPositionData = { accountId, symbol, side, quantity, pnl, accountName };

    positionElements.closePositionSymbol.textContent = symbol;
    positionElements.closePositionSide.textContent = side;
    positionElements.closePositionSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.closePositionAccount.textContent = accountName;
    positionElements.closePositionSize.textContent = quantity;
    positionElements.closePositionPnl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    positionElements.closePositionPnl.className = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

    // Reset to 100%
    positionElements.closePercentageSlider.value = 100;
    document.querySelectorAll('#closePositionModal .pct-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('#closePositionModal .pct-btn[data-pct="100"]').classList.add('active');
    updateCloseQuantity();

    // Reset order type to MARKET
    closeOrderType = 'MARKET';
    const toggleBtns = document.querySelectorAll('#closeOrderTypeToggle .toggle-btn');
    toggleBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.type === 'MARKET'));
    updateCloseButtonText();

    positionElements.closePositionModal.classList.add('active');
}

// Set close order type
function setCloseOrderType(type) {
    closeOrderType = type;
    const toggleBtns = document.querySelectorAll('#closeOrderTypeToggle .toggle-btn');
    toggleBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.type === type));
    updateCloseButtonText();
}

// Update close button text based on order type
function updateCloseButtonText() {
    const btn = document.getElementById('confirmClosePosition');
    if (btn) {
        btn.textContent = closeOrderType === 'BBO' ? 'BBO Close' : 'Market Close';
    }
}

// Close the close position modal
function closeClosePositionModal() {
    positionElements.closePositionModal.classList.remove('active');
    currentPositionData = null;
}

// Update close quantity based on slider
function updateCloseQuantity() {
    if (!currentPositionData) return;
    const percentage = parseInt(positionElements.closePercentageSlider.value);
    positionElements.closePercentageValue.textContent = `${percentage}%`;
    const closeQty = (currentPositionData.quantity * percentage / 100).toFixed(6);
    positionElements.closeQuantityValue.textContent = closeQty;
}

// Execute close position
async function executeClosePosition() {
    if (!currentPositionData) return;

    const percentage = parseInt(positionElements.closePercentageSlider.value);
    const closeQty = currentPositionData.quantity * percentage / 100;
    const isBbo = closeOrderType === 'BBO';
    const orderTypeLabel = isBbo ? 'BBO' : 'Market';

    positionElements.confirmClosePosition.disabled = true;
    positionElements.confirmClosePosition.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Closing...</span>';

    try {
        const requestBody = {
            symbol: currentPositionData.symbol,
            side: currentPositionData.side,
            quantity: closeQty
        };

        // BBO uses LIMIT order type with price_match
        if (isBbo) {
            requestBody.order_type = 'LIMIT';
            requestBody.price_match = 'QUEUE';  // Queue at best bid/ask
        } else {
            requestBody.order_type = 'MARKET';
        }

        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/close-position`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (response.ok) {
            showToast(`${orderTypeLabel} closed: ${currentPositionData.symbol}`, 'success');
            closeClosePositionModal();
            loadAllPositions();
        } else {
            showToast(data.error || 'Failed to close position', 'error');
        }
    } catch (error) {
        console.error('Error closing position:', error);
        showToast('Failed to close position', 'error');
    } finally {
        positionElements.confirmClosePosition.disabled = false;
        positionElements.confirmClosePosition.textContent = closeOrderType === 'BBO' ? 'BBO Close' : 'Market Close';
    }
}

// Open edit stop loss modal
function openEditStopLossModal(accountId, symbol, side, quantity, stopPrice, stopOrderId, accountName, entryPrice) {
    currentPositionData = { accountId, symbol, side, quantity, stopPrice, stopOrderId, accountName, entryPrice };

    positionElements.slSymbol.textContent = symbol;
    positionElements.slSide.textContent = side;
    positionElements.slSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.slAccount.textContent = accountName;

    if (stopPrice && stopOrderId) {
        positionElements.slCurrentStop.textContent = formatPrice(stopPrice);
        positionElements.slCurrentStop.className = 'has-sl';
        positionElements.removeStopLossBtn.style.display = 'block';
    } else {
        positionElements.slCurrentStop.textContent = stopPrice ? formatPrice(stopPrice) : 'None';
        positionElements.slCurrentStop.className = stopPrice ? 'has-sl' : 'no-sl';
        positionElements.removeStopLossBtn.style.display = 'none';
    }

    positionElements.newStopPrice.value = '';
    positionElements.slHint.textContent = side === 'LONG' ? 'Set below entry price' : 'Set above entry price';

    // Calculate initial potential loss
    calculateStopLossPotentialLoss();

    positionElements.editStopLossModal.classList.add('active');
}

// Calculate potential loss based on stop price
function calculateStopLossPotentialLoss() {
    const stopPriceInput = positionElements.newStopPrice;
    const lossSection = document.getElementById('slPotentialLossSection');
    const lossDisplay = document.getElementById('slPotentialLoss');

    if (!stopPriceInput || !lossSection || !lossDisplay || !currentPositionData || !currentPositionData.entryPrice) {
        if (lossSection) lossSection.style.display = 'none';
        return;
    }

    const stopPrice = parseFloat(stopPriceInput.value);

    if (!stopPrice || stopPrice <= 0) {
        lossSection.style.display = 'none';
        return;
    }

    const entryPrice = currentPositionData.entryPrice;
    const quantity = currentPositionData.quantity;
    const side = currentPositionData.side;

    // Calculate loss: For LONG, loss = qty * (entry - stop), For SHORT, loss = qty * (stop - entry)
    let loss;
    if (side === 'LONG') {
        loss = quantity * (entryPrice - stopPrice);
    } else {
        loss = quantity * (stopPrice - entryPrice);
    }

    // Only show if it's a valid stop (would result in a loss, not a profit)
    if (loss > 0) {
        lossSection.style.display = 'block';
        lossDisplay.textContent = `-$${loss.toFixed(2)}`;
        lossDisplay.className = 'loss-amount negative';
    } else if (loss < 0) {
        // This would actually be a profit (invalid stop placement)
        lossSection.style.display = 'block';
        lossDisplay.textContent = `+$${Math.abs(loss).toFixed(2)}`;
        lossDisplay.className = 'loss-amount positive';
    } else {
        lossSection.style.display = 'none';
    }
}

// Close edit stop loss modal
function closeEditStopLossModal() {
    positionElements.editStopLossModal.classList.remove('active');
    currentPositionData = null;
}

// Execute update stop loss
async function executeUpdateStopLoss() {
    if (!currentPositionData) return;

    const newPrice = parseFloat(positionElements.newStopPrice.value);
    if (!newPrice || isNaN(newPrice)) {
        showToast('Please enter a valid stop price', 'error');
        return;
    }

    positionElements.confirmEditStopLoss.disabled = true;
    positionElements.confirmEditStopLoss.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Updating...</span>';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/update-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                position_side: currentPositionData.side,
                stop_price: newPrice,
                old_order_id: currentPositionData.stopOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Stop loss updated', 'success');
            closeEditStopLossModal();
            loadAllPositions(true);  // Force refresh to get updated data
        } else {
            showToast(data.error || 'Failed to update stop loss', 'error');
        }
    } catch (error) {
        console.error('Error updating stop loss:', error);
        showToast('Failed to update stop loss', 'error');
    } finally {
        positionElements.confirmEditStopLoss.disabled = false;
        positionElements.confirmEditStopLoss.innerHTML = 'Update Stop Loss';
    }
}

// Execute remove stop loss
async function executeRemoveStopLoss() {
    if (!currentPositionData) {
        showToast('No position selected', 'error');
        return;
    }
    if (!currentPositionData.stopOrderId) {
        showToast('No stop loss order to remove', 'error');
        return;
    }

    positionElements.removeStopLossBtn.disabled = true;
    positionElements.removeStopLossBtn.innerHTML = 'Removing...';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/cancel-stop-loss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                order_id: currentPositionData.stopOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Stop loss removed', 'success');
            closeEditStopLossModal();
            loadAllPositions(true);  // Force refresh to get updated data
        } else {
            showToast(data.error || 'Failed to remove stop loss', 'error');
        }
    } catch (error) {
        console.error('Error removing stop loss:', error);
        showToast('Failed to remove stop loss', 'error');
    } finally {
        positionElements.removeStopLossBtn.disabled = false;
        positionElements.removeStopLossBtn.innerHTML = 'Remove SL';
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <span class="toast-message">${escapeHtml(message)}</span>
    `;

    positionElements.toastContainer.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== TAKE PROFIT FUNCTIONS ====================

// Open edit take profit modal
function openEditTakeProfitModal(accountId, symbol, side, quantity, tpPrice, tpOrderId, accountName) {
    currentPositionData = { accountId, symbol, side, quantity, tpPrice, tpOrderId, accountName };

    positionElements.tpSymbol.textContent = symbol;
    positionElements.tpSide.textContent = side;
    positionElements.tpSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.tpAccount.textContent = accountName;

    if (tpPrice && tpOrderId) {
        positionElements.tpCurrentTP.textContent = formatPrice(tpPrice);
        positionElements.tpCurrentTP.className = 'has-tp';
        positionElements.removeTakeProfitBtn.style.display = 'block';
    } else {
        positionElements.tpCurrentTP.textContent = tpPrice ? formatPrice(tpPrice) : 'None';
        positionElements.tpCurrentTP.className = tpPrice ? 'has-tp' : 'no-tp';
        positionElements.removeTakeProfitBtn.style.display = 'none';
    }

    positionElements.newTakeProfitPrice.value = '';
    positionElements.tpHint.textContent = side === 'LONG' ? 'Set above entry price' : 'Set below entry price';

    positionElements.editTakeProfitModal.classList.add('active');
}

// Close edit take profit modal
function closeEditTakeProfitModal() {
    positionElements.editTakeProfitModal.classList.remove('active');
    currentPositionData = null;
}

// Execute update take profit
async function executeUpdateTakeProfit() {
    if (!currentPositionData) return;

    const newPrice = parseFloat(positionElements.newTakeProfitPrice.value);
    if (!newPrice || isNaN(newPrice)) {
        showToast('Please enter a valid take profit price', 'error');
        return;
    }

    positionElements.confirmEditTakeProfit.disabled = true;
    positionElements.confirmEditTakeProfit.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Updating...</span>';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/update-take-profit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                position_side: currentPositionData.side,
                tp_price: newPrice,
                old_order_id: currentPositionData.tpOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Take profit updated', 'success');
            closeEditTakeProfitModal();
            loadAllPositions(true);  // Force refresh to get updated data
        } else {
            showToast(data.error || 'Failed to update take profit', 'error');
        }
    } catch (error) {
        console.error('Error updating take profit:', error);
        showToast('Failed to update take profit', 'error');
    } finally {
        positionElements.confirmEditTakeProfit.disabled = false;
        positionElements.confirmEditTakeProfit.innerHTML = 'Update Take Profit';
    }
}

// Execute remove take profit
async function executeRemoveTakeProfit() {
    if (!currentPositionData) {
        showToast('No position selected', 'error');
        return;
    }
    if (!currentPositionData.tpOrderId) {
        showToast('No take profit order to remove', 'error');
        return;
    }

    positionElements.removeTakeProfitBtn.disabled = true;
    positionElements.removeTakeProfitBtn.innerHTML = 'Removing...';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/cancel-take-profit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                order_id: currentPositionData.tpOrderId
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Take profit removed', 'success');
            closeEditTakeProfitModal();
            loadAllPositions(true);  // Force refresh to get updated data
        } else {
            showToast(data.error || 'Failed to remove take profit', 'error');
        }
    } catch (error) {
        console.error('Error removing take profit:', error);
        showToast('Failed to remove take profit', 'error');
    } finally {
        positionElements.removeTakeProfitBtn.disabled = false;
        positionElements.removeTakeProfitBtn.innerHTML = 'Remove TP';
    }
}

// ==================== ADD TO POSITION ====================

// Open add to position modal
async function openAddToPositionModal(accountId, symbol, side, quantity, entryPrice, markPrice, leverage, accountName) {
    currentPositionData = { accountId, symbol, side, quantity, entryPrice, markPrice, leverage, accountName, availableBalance: 0 };

    positionElements.addPosSymbol.textContent = symbol;
    positionElements.addPosSide.textContent = side;
    positionElements.addPosSide.className = `position-side ${side.toLowerCase()}`;
    positionElements.addPosAccount.textContent = accountName;
    positionElements.addPosCurrentSize.textContent = quantity.toFixed(6);
    positionElements.addPosEntryPrice.textContent = `$${formatPrice(entryPrice)}`;
    positionElements.addPosMarkPrice.textContent = `$${formatPrice(markPrice)}`;
    positionElements.addPosLeverage.textContent = `${leverage}x`;

    // Clear inputs
    positionElements.addPosUsdc.value = '';
    positionElements.addPosCalcQty.textContent = '0.00';

    // Fetch available balance
    try {
        const response = await fetch(`/api/accounts/${accountId}/balance`);
        if (response.ok) {
            const data = await response.json();
            currentPositionData.availableBalance = data.available || data.balance || 0;
        }
    } catch (error) {
        console.error('Error fetching balance:', error);
    }

    positionElements.addToPositionModal.classList.add('active');
}

// Close add to position modal
function closeAddToPositionModal() {
    positionElements.addToPositionModal.classList.remove('active');
    currentPositionData = null;
}

// Calculate quantity based on USDC input
function calculateAddPositionQty() {
    if (!currentPositionData || !positionElements.addPosUsdc) return;

    const usdcAmount = parseFloat(positionElements.addPosUsdc.value) || 0;
    const markPrice = currentPositionData.markPrice || 0;

    if (markPrice > 0 && usdcAmount > 0) {
        const qty = usdcAmount / markPrice;
        positionElements.addPosCalcQty.textContent = qty.toFixed(6);
    } else {
        positionElements.addPosCalcQty.textContent = '0.00';
    }
}

// Execute add to position
async function executeAddToPosition() {
    if (!currentPositionData) return;

    const usdcAmount = parseFloat(positionElements.addPosUsdc.value);
    if (!usdcAmount || usdcAmount <= 0) {
        showToast('Please enter a valid USDC amount', 'error');
        return;
    }

    const markPrice = currentPositionData.markPrice || 0;
    if (markPrice <= 0) {
        showToast('Invalid mark price', 'error');
        return;
    }

    const quantity = usdcAmount / markPrice;

    positionElements.confirmAddToPosition.disabled = true;
    positionElements.confirmAddToPosition.innerHTML = '<span class="btn-loading"><span class="btn-spinner"></span>Adding...</span>';

    try {
        const response = await fetch(`/api/accounts/${currentPositionData.accountId}/add-to-position`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentPositionData.symbol,
                side: currentPositionData.side,
                quantity: quantity
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast(`Added to ${currentPositionData.symbol} position`, 'success');
            closeAddToPositionModal();
            loadAllPositions(true);  // Force refresh to get updated data
        } else {
            showToast(data.error || 'Failed to add to position', 'error');
        }
    } catch (error) {
        console.error('Error adding to position:', error);
        showToast('Failed to add to position', 'error');
    } finally {
        positionElements.confirmAddToPosition.disabled = false;
        positionElements.confirmAddToPosition.innerHTML = 'Add to Position';
    }
}

// ==================== POSITION SIZE CALCULATOR ====================

function setupPositionCalculator() {
    const modal = document.getElementById('positionCalcModal');
    const openBtn = document.getElementById('positionCalcBtn');
    const closeBtn = document.getElementById('closePositionCalcModal');
    const doneBtn = document.getElementById('doneCalcBtn');
    const clearBtn = document.getElementById('clearCalcBtn');

    if (!modal) return;

    // Open modal
    if (openBtn) {
        openBtn.addEventListener('click', () => {
            modal.classList.add('active');
        });
    }

    // Close handlers
    if (closeBtn) closeBtn.addEventListener('click', () => modal.classList.remove('active'));
    if (doneBtn) doneBtn.addEventListener('click', () => modal.classList.remove('active'));

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
    });

    // Risk percentage buttons
    document.querySelectorAll('.risk-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.risk-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('calcRiskPercent').value = btn.dataset.risk;
            calculatePositionSize();
        });
    });

    // Clear button
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            document.getElementById('calcBalance').value = '';
            document.getElementById('calcEntryPrice').value = '';
            document.getElementById('calcStopLoss').value = '';
            document.getElementById('calcRiskPercent').value = '2';
            document.querySelectorAll('.risk-btn').forEach(b => b.classList.remove('active'));
            document.querySelector('.risk-btn[data-risk="2"]').classList.add('active');
            clearCalculatorResults();
        });
    }

    // Auto-calculate on input change
    ['calcBalance', 'calcRiskPercent', 'calcEntryPrice', 'calcStopLoss'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', () => {
                // Update risk button state when manually typing
                if (id === 'calcRiskPercent') {
                    const val = el.value;
                    document.querySelectorAll('.risk-btn').forEach(b => {
                        b.classList.toggle('active', b.dataset.risk === val);
                    });
                }
                calculatePositionSize();
            });
        }
    });
}

function calculatePositionSize() {
    const balance = parseFloat(document.getElementById('calcBalance').value) || 0;
    const riskPercent = parseFloat(document.getElementById('calcRiskPercent').value) || 0;
    const entryPrice = parseFloat(document.getElementById('calcEntryPrice').value) || 0;
    const stopLoss = parseFloat(document.getElementById('calcStopLoss').value) || 0;

    if (!balance || !riskPercent || !entryPrice || !stopLoss) {
        clearCalculatorResults();
        return;
    }

    // Calculate risk in USD
    const riskUsd = balance * (riskPercent / 100);

    // Calculate stop distance
    const stopDistance = Math.abs(entryPrice - stopLoss);
    const stopDistancePct = (stopDistance / entryPrice) * 100;

    if (stopDistance === 0) {
        clearCalculatorResults();
        return;
    }

    // Position size in contracts (quantity)
    const positionQty = riskUsd / stopDistance;

    // Position size in USD
    const positionUsd = positionQty * entryPrice;

    // Update display
    document.getElementById('calcRiskUsd').textContent = `$${riskUsd.toFixed(2)}`;
    document.getElementById('calcStopDistance').textContent = `${stopDistancePct.toFixed(2)}%`;
    document.getElementById('calcPositionUsd').textContent = `$${positionUsd.toFixed(2)}`;
    document.getElementById('calcPositionQty').textContent = positionQty.toFixed(6);
}

function clearCalculatorResults() {
    document.getElementById('calcRiskUsd').textContent = '$0.00';
    document.getElementById('calcStopDistance').textContent = '0.00%';
    document.getElementById('calcPositionUsd').textContent = '$0.00';
    document.getElementById('calcPositionQty').textContent = '0.000';
}

// Initialize calculator when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    setupPositionCalculator();
});

// Expose functions to global scope
window.openClosePositionModal = openClosePositionModal;
window.openEditStopLossModal = openEditStopLossModal;
window.openEditTakeProfitModal = openEditTakeProfitModal;
window.openAddToPositionModal = openAddToPositionModal;
