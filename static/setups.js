/**
 * Setups Page JavaScript
 * Handles folders and setups CRUD operations with multi-image support
 */

// State
let folders = [];
let setups = [];
let currentFolderId = 'all';
let editingFolderId = null;
let editingSetupId = null;

// Multi-image state
let setupImages = []; // Array of {id, timeframe, image_data, notes, isNew, isModified, toDelete}
let currentImageIndex = -1;
let viewerImages = [];
let viewerCurrentIndex = 0;

// DOM Elements
const foldersList = document.getElementById('foldersList');
const setupsGrid = document.getElementById('setupsGrid');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const pageTitle = document.getElementById('pageTitle');
const allSetupsCount = document.getElementById('allSetupsCount');

// Folder Modal
const folderModal = document.getElementById('folderModal');
const folderModalTitle = document.getElementById('folderModalTitle');
const folderNameInput = document.getElementById('folderName');
const folderDescriptionInput = document.getElementById('folderDescription');
const folderColorInput = document.getElementById('folderColor');
const colorPreview = document.getElementById('colorPreview');
const addFolderBtn = document.getElementById('addFolderBtn');
const closeFolderModal = document.getElementById('closeFolderModal');
const cancelFolderBtn = document.getElementById('cancelFolderBtn');
const saveFolderBtn = document.getElementById('saveFolderBtn');

// Delete Folder Modal
const deleteFolderModal = document.getElementById('deleteFolderModal');
const deleteFolderName = document.getElementById('deleteFolderName');
const closeDeleteFolderModal = document.getElementById('closeDeleteFolderModal');
const cancelDeleteFolderBtn = document.getElementById('cancelDeleteFolderBtn');
const confirmDeleteFolderBtn = document.getElementById('confirmDeleteFolderBtn');
let folderToDelete = null;

// Setup Modal
const setupModal = document.getElementById('setupModal');
const setupModalTitle = document.getElementById('setupModalTitle');
const setupNameInput = document.getElementById('setupName');
const setupTimeframeSelect = document.getElementById('setupTimeframe');
const setupFolderSelect = document.getElementById('setupFolder');
const setupDescriptionInput = document.getElementById('setupDescription');
const setupNotesInput = document.getElementById('setupNotes');
const addSetupBtn = document.getElementById('addSetupBtn');
const closeSetupModal = document.getElementById('closeSetupModal');
const cancelSetupBtn = document.getElementById('cancelSetupBtn');
const saveSetupBtn = document.getElementById('saveSetupBtn');

// Multi-image elements
const imageTabs = document.getElementById('imageTabs');
const addImageTabBtn = document.getElementById('addImageTabBtn');
const imageTabContent = document.getElementById('imageTabContent');
const noImagesPlaceholder = document.getElementById('noImagesPlaceholder');
const imageEditor = document.getElementById('imageEditor');
const currentImageTimeframe = document.getElementById('currentImageTimeframe');
const deleteCurrentImageBtn = document.getElementById('deleteCurrentImageBtn');
const currentImageUpload = document.getElementById('currentImageUpload');
const currentUploadPlaceholder = document.getElementById('currentUploadPlaceholder');
const currentImagePreview = document.getElementById('currentImagePreview');
const currentPreviewImg = document.getElementById('currentPreviewImg');
const currentImageInput = document.getElementById('currentImageInput');
const currentImageNotes = document.getElementById('currentImageNotes');

// Delete Setup Modal
const deleteSetupModal = document.getElementById('deleteSetupModal');
const deleteSetupName = document.getElementById('deleteSetupName');
const closeDeleteSetupModal = document.getElementById('closeDeleteSetupModal');
const cancelDeleteSetupBtn = document.getElementById('cancelDeleteSetupBtn');
const confirmDeleteSetupBtn = document.getElementById('confirmDeleteSetupBtn');
let setupToDelete = null;

// Setup Viewer Modal
const imageViewerModal = document.getElementById('imageViewerModal');
const viewerImage = document.getElementById('viewerImage');
const viewerTitle = document.getElementById('viewerTitle');
const viewerImageContainer = document.getElementById('viewerImageContainer');
const viewerIndicators = document.getElementById('viewerIndicators');
const viewerDescription = document.getElementById('viewerDescription');
const viewerDescriptionText = document.getElementById('viewerDescriptionText');
const closeImageViewer = document.getElementById('closeImageViewer');
const viewerPrevBtn = document.getElementById('viewerPrevBtn');
const viewerNextBtn = document.getElementById('viewerNextBtn');
const viewerPrevSetupBtn = document.getElementById('viewerPrevSetupBtn');
const viewerNextSetupBtn = document.getElementById('viewerNextSetupBtn');
const viewerSetupNav = document.getElementById('viewerSetupNav');
const viewerSetupIndicator = document.getElementById('viewerSetupIndicator');
const imageWrapper = document.getElementById('imageWrapper');
const zoomControls = document.getElementById('zoomControls');
const zoomInBtn = document.getElementById('zoomInBtn');
const zoomOutBtn = document.getElementById('zoomOutBtn');
const zoomResetBtn = document.getElementById('zoomResetBtn');
const zoomLevelDisplay = document.getElementById('zoomLevel');
let currentViewerSetupIndex = -1;
let currentViewerSetup = null;
let touchStartX = 0;
let touchEndX = 0;

// Zoom state
let zoomLevel = 1;
let minZoom = 1;
let maxZoom = 5;
let zoomStep = 0.5;
let panX = 0;
let panY = 0;
let isPanning = false;
let panStartX = 0;
let panStartY = 0;
let lastTapTime = 0;
let initialPinchDistance = 0;
let initialZoomLevel = 1;

// Toast
const toastContainer = document.getElementById('toastContainer');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadFolders();
    loadSetups();
    setupEventListeners();
    updateColorPreview();
});

// Event Listeners
function setupEventListeners() {
    // Folder Modal
    addFolderBtn.addEventListener('click', () => openFolderModal());
    closeFolderModal.addEventListener('click', () => closeFolderModalFn());
    cancelFolderBtn.addEventListener('click', () => closeFolderModalFn());
    saveFolderBtn.addEventListener('click', saveFolder);
    folderColorInput.addEventListener('input', updateColorPreview);

    // Delete Folder Modal
    closeDeleteFolderModal.addEventListener('click', () => closeDeleteFolderModalFn());
    cancelDeleteFolderBtn.addEventListener('click', () => closeDeleteFolderModalFn());
    confirmDeleteFolderBtn.addEventListener('click', deleteFolder);

    // Setup Modal
    addSetupBtn.addEventListener('click', () => openSetupModal());
    closeSetupModal.addEventListener('click', () => closeSetupModalFn());
    cancelSetupBtn.addEventListener('click', () => closeSetupModalFn());
    saveSetupBtn.addEventListener('click', saveSetup);

    // Multi-image management
    addImageTabBtn.addEventListener('click', addNewImage);
    deleteCurrentImageBtn.addEventListener('click', deleteCurrentImage);
    currentImageTimeframe.addEventListener('change', updateCurrentImageTimeframe);
    currentImageNotes.addEventListener('input', updateCurrentImageNotes);

    // Image Upload for current tab
    currentImageUpload.addEventListener('click', () => currentImageInput.click());
    currentImageInput.addEventListener('change', handleCurrentImageSelect);

    // Drag and drop for current image
    currentImageUpload.addEventListener('dragover', (e) => {
        e.preventDefault();
        currentImageUpload.classList.add('dragover');
    });
    currentImageUpload.addEventListener('dragleave', () => {
        currentImageUpload.classList.remove('dragover');
    });
    currentImageUpload.addEventListener('drop', (e) => {
        e.preventDefault();
        currentImageUpload.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('image/')) {
            handleCurrentImageFile(files[0]);
        }
    });

    // Delete Setup Modal
    closeDeleteSetupModal.addEventListener('click', () => closeDeleteSetupModalFn());
    cancelDeleteSetupBtn.addEventListener('click', () => closeDeleteSetupModalFn());
    confirmDeleteSetupBtn.addEventListener('click', deleteSetup);

    // Image Viewer Modal
    closeImageViewer.addEventListener('click', () => closeImageViewerFn());
    imageViewerModal.addEventListener('click', (e) => {
        if (e.target === imageViewerModal) closeImageViewerFn();
    });
    viewerPrevBtn.addEventListener('click', () => navigateViewerImage(-1));
    viewerNextBtn.addEventListener('click', () => navigateViewerImage(1));
    viewerPrevSetupBtn.addEventListener('click', () => navigateToSetup(-1));
    viewerNextSetupBtn.addEventListener('click', () => navigateToSetup(1));

    // Zoom button controls
    zoomInBtn.addEventListener('click', () => zoomIn());
    zoomOutBtn.addEventListener('click', () => zoomOut());
    zoomResetBtn.addEventListener('click', () => resetZoom());

    // Mouse wheel zoom
    viewerImageContainer.addEventListener('wheel', handleWheelZoom, { passive: false });

    // Double-click to zoom (desktop)
    viewerImage.addEventListener('dblclick', handleDoubleClickZoom);

    // Touch/swipe and pinch-zoom support for mobile
    viewerImageContainer.addEventListener('touchstart', handleTouchStart, { passive: false });
    viewerImageContainer.addEventListener('touchmove', handleTouchMove, { passive: false });
    viewerImageContainer.addEventListener('touchend', handleTouchEnd, { passive: true });

    // Mouse pan when zoomed
    imageWrapper.addEventListener('mousedown', handlePanStart);
    document.addEventListener('mousemove', handlePanMove);
    document.addEventListener('mouseup', handlePanEnd);

    // Close modals on escape and keyboard navigation for image viewer
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeFolderModalFn();
            closeDeleteFolderModalFn();
            closeSetupModalFn();
            closeDeleteSetupModalFn();
            closeImageViewerFn();
        }
        // Arrow key navigation for image viewer
        if (imageViewerModal.classList.contains('active')) {
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                navigateViewerImage(-1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                navigateViewerImage(1);
            }
        }
    });

    // Close modals on overlay click
    folderModal.addEventListener('click', (e) => {
        if (e.target === folderModal) closeFolderModalFn();
    });
    deleteFolderModal.addEventListener('click', (e) => {
        if (e.target === deleteFolderModal) closeDeleteFolderModalFn();
    });
    setupModal.addEventListener('click', (e) => {
        if (e.target === setupModal) closeSetupModalFn();
    });
    deleteSetupModal.addEventListener('click', (e) => {
        if (e.target === deleteSetupModal) closeDeleteSetupModalFn();
    });
}

// API Functions
async function loadFolders() {
    try {
        const response = await fetch('/api/setup-folders');
        folders = await response.json();
        renderFolders();
    } catch (error) {
        console.error('Error loading folders:', error);
        showToast('Failed to load folders', 'error');
    }
}

async function loadSetups() {
    try {
        loadingState.style.display = 'flex';
        emptyState.style.display = 'none';

        let url = '/api/setups';
        if (currentFolderId !== 'all') {
            url += `?folder_id=${currentFolderId}`;
        }

        const response = await fetch(url);
        setups = await response.json();

        loadingState.style.display = 'none';
        renderSetups();
        updateAllSetupsCount();
    } catch (error) {
        console.error('Error loading setups:', error);
        loadingState.style.display = 'none';
        showToast('Failed to load setups', 'error');
    }
}

async function saveFolder() {
    const name = folderNameInput.value.trim();
    if (!name) {
        showToast('Folder name is required', 'error');
        return;
    }

    const data = {
        name: name,
        description: folderDescriptionInput.value.trim(),
        color: folderColorInput.value
    };

    try {
        let response;
        if (editingFolderId) {
            response = await fetch(`/api/setup-folders/${editingFolderId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch('/api/setup-folders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }

        if (response.ok) {
            showToast(editingFolderId ? 'Folder updated' : 'Folder created', 'success');
            closeFolderModalFn();
            loadFolders();
            loadSetups();
        } else {
            const result = await response.json();
            showToast(result.error || 'Failed to save folder', 'error');
        }
    } catch (error) {
        console.error('Error saving folder:', error);
        showToast('Failed to save folder', 'error');
    }
}

async function deleteFolder() {
    if (!folderToDelete) return;

    try {
        const response = await fetch(`/api/setup-folders/${folderToDelete}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('Folder deleted', 'success');
            closeDeleteFolderModalFn();
            if (currentFolderId === folderToDelete.toString()) {
                currentFolderId = 'all';
                pageTitle.textContent = 'All Setups';
            }
            loadFolders();
            loadSetups();
        } else {
            const result = await response.json();
            showToast(result.error || 'Failed to delete folder', 'error');
        }
    } catch (error) {
        console.error('Error deleting folder:', error);
        showToast('Failed to delete folder', 'error');
    }
}

async function saveSetup() {
    const name = setupNameInput.value.trim();
    if (!name) {
        showToast('Setup name is required', 'error');
        return;
    }

    // Get primary timeframe from first image if available
    const primaryTimeframe = setupImages.length > 0 ? setupImages[0].timeframe : setupTimeframeSelect.value;

    const data = {
        name: name,
        folder_id: setupFolderSelect.value ? parseInt(setupFolderSelect.value) : null,
        description: setupDescriptionInput.value.trim(),
        timeframe: primaryTimeframe,
        notes: setupNotesInput.value.trim()
    };

    try {
        let setupId = editingSetupId;
        let response;

        // Create or update the setup first
        if (editingSetupId) {
            response = await fetch(`/api/setups/${editingSetupId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } else {
            response = await fetch('/api/setups', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        }

        if (!response.ok) {
            const result = await response.json();
            showToast(result.error || 'Failed to save setup', 'error');
            return;
        }

        if (!editingSetupId) {
            const result = await response.json();
            setupId = result.id;
        }

        // Now handle images
        let imageErrors = [];
        for (const img of setupImages) {
            if (img.toDelete && img.id) {
                // Delete existing image
                const deleteRes = await fetch(`/api/setup-images/${img.id}`, { method: 'DELETE' });
                if (!deleteRes.ok) {
                    const errData = await deleteRes.json().catch(() => ({}));
                    imageErrors.push(errData.error || `Failed to delete image (${img.timeframe})`);
                }
            } else if (img.isNew && img.image_data) {
                // Create new image
                const uploadRes = await fetch(`/api/setups/${setupId}/images`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        timeframe: img.timeframe,
                        image_data: img.image_data,
                        notes: img.notes || ''
                    })
                });
                if (!uploadRes.ok) {
                    const errData = await uploadRes.json().catch(() => ({}));
                    imageErrors.push(errData.error || `Failed to upload image (${img.timeframe})`);
                }
            } else if (img.isModified && img.id) {
                // Update existing image
                const updateRes = await fetch(`/api/setup-images/${img.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        timeframe: img.timeframe,
                        notes: img.notes || ''
                    })
                });
                if (!updateRes.ok) {
                    const errData = await updateRes.json().catch(() => ({}));
                    imageErrors.push(errData.error || `Failed to update image (${img.timeframe})`);
                }
            }
        }

        // Show results
        if (imageErrors.length > 0) {
            showToast(`Setup saved but some images failed: ${imageErrors.join(', ')}`, 'error');
        } else {
            showToast(editingSetupId ? 'Setup updated' : 'Setup created', 'success');
        }
        closeSetupModalFn();
        loadFolders();
        loadSetups();
    } catch (error) {
        console.error('Error saving setup:', error);
        showToast('Failed to save setup', 'error');
    }
}

async function deleteSetup() {
    if (!setupToDelete) return;

    try {
        const response = await fetch(`/api/setups/${setupToDelete}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('Setup deleted', 'success');
            closeDeleteSetupModalFn();
            loadFolders();
            loadSetups();
        } else {
            const result = await response.json();
            showToast(result.error || 'Failed to delete setup', 'error');
        }
    } catch (error) {
        console.error('Error deleting setup:', error);
        showToast('Failed to delete setup', 'error');
    }
}

// Render Functions
function renderFolders() {
    // Keep the "All Setups" item
    const allSetupsItem = foldersList.querySelector('[data-folder-id="all"]');
    foldersList.innerHTML = '';
    foldersList.appendChild(allSetupsItem);

    folders.forEach(folder => {
        const folderItem = document.createElement('a');
        folderItem.href = '#';
        folderItem.className = `folder-item${currentFolderId === folder.id.toString() ? ' active' : ''}`;
        folderItem.dataset.folderId = folder.id;

        folderItem.innerHTML = `
            <span class="folder-color" style="background-color: ${folder.color}"></span>
            <span>${escapeHtml(folder.name)}</span>
            <span class="folder-count">${folder.setup_count}</span>
            <div class="folder-actions">
                <button class="folder-action-btn edit" onclick="event.stopPropagation(); editFolder(${folder.id})" title="Edit">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="folder-action-btn delete" onclick="event.stopPropagation(); confirmDeleteFolder(${folder.id}, '${escapeHtml(folder.name)}')" title="Delete">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `;

        folderItem.addEventListener('click', (e) => {
            e.preventDefault();
            selectFolder(folder.id, folder.name);
        });

        foldersList.appendChild(folderItem);
    });

    // Update All Setups active state
    const allItem = foldersList.querySelector('[data-folder-id="all"]');
    if (allItem) {
        allItem.className = `folder-item${currentFolderId === 'all' ? ' active' : ''}`;
        allItem.addEventListener('click', (e) => {
            e.preventDefault();
            selectFolder('all', 'All Setups');
        });
    }

    updateFolderSelect();
}

function renderSetups() {
    setupsGrid.innerHTML = '';

    if (setups.length === 0) {
        emptyState.style.display = 'flex';
        return;
    }

    emptyState.style.display = 'none';

    setups.forEach(setup => {
        const card = document.createElement('div');
        card.className = 'setup-card';
        card.onclick = () => {
            openImageViewer(setup);
        };

        // Check for images - prefer first from images array, fall back to image_data
        const hasImages = (setup.images && setup.images.length > 0) || setup.image_data;
        const firstImageSrc = setup.images && setup.images.length > 0
            ? setup.images[0].image_path
            : setup.image_data;

        const imageHtml = hasImages
            ? `<img src="${firstImageSrc}" alt="${escapeHtml(setup.name)}">`
            : `<div class="setup-image-placeholder">
                   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                       <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                       <circle cx="8.5" cy="8.5" r="1.5"/>
                       <polyline points="21 15 16 10 5 21"/>
                   </svg>
                   <span>No image</span>
               </div>`;

        // Show image count badge if multiple images
        const imageCount = setup.images ? setup.images.length : (setup.image_data ? 1 : 0);
        const imageCountBadge = imageCount > 1
            ? `<span class="image-count-badge">${imageCount} images</span>`
            : '';

        const timeframeBadge = setup.timeframe
            ? `<span class="setup-timeframe-badge">${setup.timeframe}</span>`
            : '';

        const folderTag = setup.folder_name
            ? `<div class="setup-folder-tag">
                   <span class="folder-dot" style="background-color: ${setup.folder_color || '#fbbf24'}"></span>
                   ${escapeHtml(setup.folder_name)}
               </div>`
            : '';

        // Performance stats
        let performanceHtml = '';
        if (setup.trade_count && setup.trade_count > 0) {
            const winRate = setup.win_rate !== null ? `${Math.round(setup.win_rate)}%` : '-';
            const pnl = setup.total_pnl !== null ? setup.total_pnl : 0;
            const pnlClass = pnl >= 0 ? 'positive' : 'negative';
            const pnlFormatted = pnl >= 0 ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`;

            performanceHtml = `
                <div class="setup-performance">
                    <span class="perf-stat win-rate" title="Win Rate">${winRate} WR</span>
                    <span class="perf-stat pnl ${pnlClass}" title="Total P&L">${pnlFormatted}</span>
                    <span class="perf-stat trades" title="Trades">${setup.trade_count} trades</span>
                </div>
            `;
        }

        const createdDate = new Date(setup.created_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });

        card.innerHTML = `
            <div class="setup-image">
                ${imageHtml}
                <div class="setup-badges">
                    ${timeframeBadge}
                    ${imageCountBadge}
                </div>
            </div>
            <div class="setup-content">
                <div class="setup-header">
                    <h3 class="setup-name">${escapeHtml(setup.name)}</h3>
                    <div class="setup-actions">
                        <button class="setup-action-btn" onclick="event.stopPropagation(); openSetupModal(getSetupById(${setup.id}))" title="Edit">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button>
                        <button class="setup-action-btn delete" onclick="event.stopPropagation(); confirmDeleteSetup(${setup.id}, '${escapeHtml(setup.name)}')" title="Delete">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
                ${setup.description ? `<p class="setup-description">${escapeHtml(setup.description)}</p>` : ''}
                ${performanceHtml}
                <div class="setup-meta">
                    ${folderTag}
                    <span class="setup-date">${createdDate}</span>
                </div>
            </div>
        `;

        setupsGrid.appendChild(card);
    });
}

function updateFolderSelect() {
    const currentValue = setupFolderSelect.value;
    setupFolderSelect.innerHTML = '<option value="">No folder</option>';

    folders.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder.id;
        option.textContent = folder.name;
        setupFolderSelect.appendChild(option);
    });

    // Restore previous selection if still valid
    if (currentValue) {
        setupFolderSelect.value = currentValue;
    }
}

function updateAllSetupsCount() {
    // Fetch total count
    fetch('/api/setups')
        .then(res => res.json())
        .then(data => {
            allSetupsCount.textContent = data.length;
        });
}

// Modal Functions
function openFolderModal(folder = null) {
    editingFolderId = folder ? folder.id : null;
    folderModalTitle.textContent = folder ? 'Edit Folder' : 'Add Folder';
    folderNameInput.value = folder ? folder.name : '';
    folderDescriptionInput.value = folder ? folder.description || '' : '';
    folderColorInput.value = folder ? folder.color : '#fbbf24';
    updateColorPreview();
    folderModal.classList.add('active');
    folderNameInput.focus();
}

function closeFolderModalFn() {
    folderModal.classList.remove('active');
    editingFolderId = null;
}

function openDeleteFolderModal(folderId, folderName) {
    folderToDelete = folderId;
    deleteFolderName.textContent = folderName;
    deleteFolderModal.classList.add('active');
}

function closeDeleteFolderModalFn() {
    deleteFolderModal.classList.remove('active');
    folderToDelete = null;
}

async function openSetupModal(setup = null) {
    editingSetupId = setup ? setup.id : null;
    setupModalTitle.textContent = setup ? 'Edit Setup' : 'Add Setup';
    setupNameInput.value = setup ? setup.name : '';
    setupTimeframeSelect.value = setup ? setup.timeframe || '' : '';
    setupFolderSelect.value = setup ? (setup.folder_id || '') : (currentFolderId !== 'all' ? currentFolderId : '');
    setupDescriptionInput.value = setup ? setup.description || '' : '';
    setupNotesInput.value = setup ? setup.notes || '' : '';

    // Reset multi-image state
    setupImages = [];
    currentImageIndex = -1;

    // Load existing images if editing
    if (setup && setup.id) {
        try {
            const response = await fetch(`/api/setups/${setup.id}/images`);
            if (response.ok) {
                const images = await response.json();
                setupImages = images.map(img => ({
                    id: img.id,
                    timeframe: img.timeframe,
                    image_data: img.image_path, // Use image_path from API
                    notes: img.notes || '',
                    isNew: false,
                    isModified: false,
                    toDelete: false
                }));
            }
        } catch (error) {
            console.error('Error loading setup images:', error);
        }

        // Fallback to legacy image_data if no images in new system
        if (setupImages.length === 0 && setup.image_data) {
            setupImages.push({
                id: null,
                timeframe: setup.timeframe || '1h',
                image_data: setup.image_data,
                notes: '',
                isNew: true,
                isModified: false,
                toDelete: false
            });
        }
    }

    renderImageTabs();
    updateImageEditor();

    setupModal.classList.add('active');
    setupNameInput.focus();
}

function closeSetupModalFn() {
    setupModal.classList.remove('active');
    editingSetupId = null;
    setupImages = [];
    currentImageIndex = -1;
}

function openDeleteSetupModal(setupId, setupName) {
    setupToDelete = setupId;
    deleteSetupName.textContent = setupName;
    deleteSetupModal.classList.add('active');
}

function closeDeleteSetupModalFn() {
    deleteSetupModal.classList.remove('active');
    setupToDelete = null;
}

async function openImageViewer(setup) {
    currentViewerSetup = setup;
    viewerTitle.textContent = setup.name;
    viewerImages = [];
    viewerCurrentIndex = 0;

    // Track current setup index in the setups array
    currentViewerSetupIndex = setups.findIndex(s => s.id === setup.id);
    updateSetupNavButtons();

    // Show description
    if (setup.description && setup.description.trim()) {
        viewerDescriptionText.textContent = setup.description;
        viewerDescription.style.display = 'block';
    } else {
        viewerDescription.style.display = 'none';
    }

    // Load images from API if setup has id
    if (setup.id) {
        try {
            const response = await fetch(`/api/setups/${setup.id}/images`);
            if (response.ok) {
                const images = await response.json();
                viewerImages = images.map(img => ({
                    timeframe: img.timeframe,
                    src: img.image_path,
                    notes: img.notes || ''
                }));
            }
        } catch (error) {
            console.error('Error loading images for viewer:', error);
        }
    }

    // Fallback to legacy image_data
    if (viewerImages.length === 0 && setup.image_data) {
        viewerImages.push({
            timeframe: setup.timeframe || '',
            src: setup.image_data,
            notes: ''
        });
    }

    // If no images at all, just open edit modal
    if (viewerImages.length === 0) {
        openSetupModal(setup);
        return;
    }

    renderViewerIndicators();
    showViewerImage(0);
    imageViewerModal.classList.add('active');
}

function closeImageViewerFn() {
    imageViewerModal.classList.remove('active');
    viewerImages = [];
    currentViewerSetup = null;
    // Reset zoom state
    resetZoom();
}

// Multi-image management functions
function renderImageTabs() {
    // Clear existing tabs except the add button
    const tabs = imageTabs.querySelectorAll('.image-tab:not(.add-tab)');
    tabs.forEach(tab => tab.remove());

    // Add tabs for each image
    const activeImages = setupImages.filter(img => !img.toDelete);
    activeImages.forEach((img, index) => {
        const tab = document.createElement('button');
        tab.type = 'button';
        tab.className = `image-tab${currentImageIndex === index ? ' active' : ''}`;
        tab.dataset.index = index;
        tab.textContent = img.timeframe.toUpperCase();
        tab.onclick = () => selectImageTab(index);
        imageTabs.insertBefore(tab, addImageTabBtn);
    });
}

function selectImageTab(index) {
    const activeImages = setupImages.filter(img => !img.toDelete);
    if (index < 0 || index >= activeImages.length) return;

    currentImageIndex = index;

    // Update tab active states
    imageTabs.querySelectorAll('.image-tab').forEach((tab, i) => {
        if (tab.classList.contains('add-tab')) return;
        tab.classList.toggle('active', i === index);
    });

    updateImageEditor();
}

function updateImageEditor() {
    const activeImages = setupImages.filter(img => !img.toDelete);

    if (activeImages.length === 0) {
        noImagesPlaceholder.style.display = 'flex';
        imageEditor.style.display = 'none';
        currentImageIndex = -1;
        return;
    }

    noImagesPlaceholder.style.display = 'none';
    imageEditor.style.display = 'block';

    // If no selection, select first
    if (currentImageIndex < 0 || currentImageIndex >= activeImages.length) {
        currentImageIndex = 0;
    }

    const img = activeImages[currentImageIndex];
    currentImageTimeframe.value = img.timeframe;
    currentImageNotes.value = img.notes || '';

    if (img.image_data) {
        currentPreviewImg.src = img.image_data;
        currentUploadPlaceholder.style.display = 'none';
        currentImagePreview.style.display = 'block';
    } else {
        currentPreviewImg.src = '';
        currentUploadPlaceholder.style.display = 'flex';
        currentImagePreview.style.display = 'none';
    }
}

function addNewImage() {
    // Find a timeframe not already used
    const usedTimeframes = setupImages.filter(img => !img.toDelete).map(img => img.timeframe);
    const allTimeframes = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w'];
    let newTimeframe = allTimeframes.find(tf => !usedTimeframes.includes(tf)) || '1h';

    setupImages.push({
        id: null,
        timeframe: newTimeframe,
        image_data: null,
        notes: '',
        isNew: true,
        isModified: false,
        toDelete: false
    });

    currentImageIndex = setupImages.filter(img => !img.toDelete).length - 1;
    renderImageTabs();
    updateImageEditor();
}

function deleteCurrentImage() {
    const activeImages = setupImages.filter(img => !img.toDelete);
    if (currentImageIndex < 0 || currentImageIndex >= activeImages.length) return;

    const imgToDelete = activeImages[currentImageIndex];
    const actualIndex = setupImages.indexOf(imgToDelete);

    if (imgToDelete.id) {
        // Mark for deletion
        setupImages[actualIndex].toDelete = true;
    } else {
        // Remove from array if it's a new unsaved image
        setupImages.splice(actualIndex, 1);
    }

    // Adjust current index
    const remainingImages = setupImages.filter(img => !img.toDelete);
    if (remainingImages.length === 0) {
        currentImageIndex = -1;
    } else if (currentImageIndex >= remainingImages.length) {
        currentImageIndex = remainingImages.length - 1;
    }

    renderImageTabs();
    updateImageEditor();
}

function updateCurrentImageTimeframe() {
    const activeImages = setupImages.filter(img => !img.toDelete);
    if (currentImageIndex < 0 || currentImageIndex >= activeImages.length) return;

    const img = activeImages[currentImageIndex];
    const actualIndex = setupImages.indexOf(img);
    setupImages[actualIndex].timeframe = currentImageTimeframe.value;
    setupImages[actualIndex].isModified = true;
    renderImageTabs();
}

function updateCurrentImageNotes() {
    const activeImages = setupImages.filter(img => !img.toDelete);
    if (currentImageIndex < 0 || currentImageIndex >= activeImages.length) return;

    const img = activeImages[currentImageIndex];
    const actualIndex = setupImages.indexOf(img);
    setupImages[actualIndex].notes = currentImageNotes.value;
    setupImages[actualIndex].isModified = true;
}

function handleCurrentImageSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleCurrentImageFile(file);
    }
}

function handleCurrentImageFile(file) {
    if (!file.type.startsWith('image/')) {
        showToast('Please select an image file', 'error');
        return;
    }

    if (file.size > 10 * 1024 * 1024) {
        showToast('Image must be less than 10MB', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const activeImages = setupImages.filter(img => !img.toDelete);
        if (currentImageIndex >= 0 && currentImageIndex < activeImages.length) {
            const img = activeImages[currentImageIndex];
            const actualIndex = setupImages.indexOf(img);
            setupImages[actualIndex].image_data = e.target.result;
            setupImages[actualIndex].isModified = true;
            if (!setupImages[actualIndex].id) {
                setupImages[actualIndex].isNew = true;
            }
        }
        currentPreviewImg.src = e.target.result;
        currentUploadPlaceholder.style.display = 'none';
        currentImagePreview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// Viewer functions
function renderViewerIndicators() {
    viewerIndicators.innerHTML = '';

    if (viewerImages.length <= 1) {
        viewerIndicators.style.display = 'none';
        return;
    }

    viewerIndicators.style.display = 'flex';

    viewerImages.forEach((img, index) => {
        const dot = document.createElement('button');
        dot.className = `carousel-dot${viewerCurrentIndex === index ? ' active' : ''}`;
        dot.onclick = () => showViewerImage(index);
        viewerIndicators.appendChild(dot);
    });
}

function showViewerImage(index) {
    if (index < 0 || index >= viewerImages.length) return;

    // Reset zoom when changing images
    resetZoom();

    viewerCurrentIndex = index;
    const img = viewerImages[index];

    viewerImage.src = img.src;

    // Update indicator dots
    viewerIndicators.querySelectorAll('.carousel-dot').forEach((dot, i) => {
        dot.classList.toggle('active', i === index);
    });

    // Update navigation button visibility
    updateNavButtons();
}

function navigateViewerImage(direction) {
    const newIndex = viewerCurrentIndex + direction;
    if (newIndex >= 0 && newIndex < viewerImages.length) {
        showViewerImage(newIndex);
    }
}

function handleSwipe() {
    // Don't swipe if zoomed in
    if (zoomLevel > 1) return;

    const swipeThreshold = 50;
    const diff = touchStartX - touchEndX;

    if (Math.abs(diff) > swipeThreshold) {
        if (diff > 0) {
            // Swipe left - next image
            navigateViewerImage(1);
        } else {
            // Swipe right - previous image
            navigateViewerImage(-1);
        }
    }
}

// Zoom Functions
function zoomIn() {
    if (zoomLevel < maxZoom) {
        zoomLevel = Math.min(zoomLevel + zoomStep, maxZoom);
        applyZoom();
    }
}

function zoomOut() {
    if (zoomLevel > minZoom) {
        zoomLevel = Math.max(zoomLevel - zoomStep, minZoom);
        if (zoomLevel === minZoom) {
            panX = 0;
            panY = 0;
        }
        applyZoom();
    }
}

function resetZoom() {
    zoomLevel = 1;
    panX = 0;
    panY = 0;
    applyZoom();
}

function applyZoom() {
    // Constrain pan to keep image in view when zoomed
    if (zoomLevel > 1) {
        const maxPanX = (viewerImage.offsetWidth * (zoomLevel - 1)) / 2;
        const maxPanY = (viewerImage.offsetHeight * (zoomLevel - 1)) / 2;
        panX = Math.max(-maxPanX, Math.min(maxPanX, panX));
        panY = Math.max(-maxPanY, Math.min(maxPanY, panY));
    } else {
        panX = 0;
        panY = 0;
    }

    viewerImage.style.transform = `scale(${zoomLevel}) translate(${panX / zoomLevel}px, ${panY / zoomLevel}px)`;
    zoomLevelDisplay.textContent = `${Math.round(zoomLevel * 100)}%`;

    // Update button states
    zoomInBtn.disabled = zoomLevel >= maxZoom;
    zoomOutBtn.disabled = zoomLevel <= minZoom;

    // Update cursor and class for pan state
    if (zoomLevel > 1) {
        imageWrapper.classList.add('zoomed');
        viewerImage.style.cursor = 'grab';
    } else {
        imageWrapper.classList.remove('zoomed');
        viewerImage.style.cursor = 'zoom-in';
    }
}

// Mouse wheel zoom
function handleWheelZoom(e) {
    if (!imageViewerModal.classList.contains('active')) return;

    e.preventDefault();

    const delta = e.deltaY > 0 ? -0.25 : 0.25;
    const newZoom = Math.max(minZoom, Math.min(maxZoom, zoomLevel + delta));

    if (newZoom !== zoomLevel) {
        // Zoom toward cursor position
        if (newZoom > zoomLevel) {
            const rect = viewerImage.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const offsetX = (e.clientX - centerX) * 0.1;
            const offsetY = (e.clientY - centerY) * 0.1;
            panX -= offsetX;
            panY -= offsetY;
        }

        zoomLevel = newZoom;
        if (zoomLevel === minZoom) {
            panX = 0;
            panY = 0;
        }
        applyZoom();
    }
}

// Double-click zoom (desktop)
function handleDoubleClickZoom(e) {
    e.preventDefault();

    if (zoomLevel === 1) {
        // Zoom in to 2x centered on click point
        const rect = viewerImage.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        panX = (centerX - e.clientX) * 0.5;
        panY = (centerY - e.clientY) * 0.5;
        zoomLevel = 2;
    } else {
        // Reset zoom
        zoomLevel = 1;
        panX = 0;
        panY = 0;
    }
    applyZoom();
}

// Touch handling for pinch zoom and double-tap
let touchCount = 0;

function handleTouchStart(e) {
    touchCount = e.touches.length;

    if (e.touches.length === 2) {
        // Pinch start
        e.preventDefault();
        initialPinchDistance = getPinchDistance(e.touches);
        initialZoomLevel = zoomLevel;
    } else if (e.touches.length === 1) {
        touchStartX = e.touches[0].screenX;

        // Double-tap detection
        const currentTime = new Date().getTime();
        const tapLength = currentTime - lastTapTime;

        if (tapLength < 300 && tapLength > 0) {
            e.preventDefault();
            handleDoubleTap(e);
        }
        lastTapTime = currentTime;

        // Pan start if zoomed
        if (zoomLevel > 1) {
            e.preventDefault();
            isPanning = true;
            panStartX = e.touches[0].clientX - panX;
            panStartY = e.touches[0].clientY - panY;
        }
    }
}

function handleTouchMove(e) {
    if (e.touches.length === 2) {
        // Pinch zoom
        e.preventDefault();
        const currentDistance = getPinchDistance(e.touches);
        const scale = currentDistance / initialPinchDistance;
        zoomLevel = Math.max(minZoom, Math.min(maxZoom, initialZoomLevel * scale));
        applyZoom();
    } else if (e.touches.length === 1 && isPanning && zoomLevel > 1) {
        // Pan while zoomed
        e.preventDefault();
        panX = e.touches[0].clientX - panStartX;
        panY = e.touches[0].clientY - panStartY;
        applyZoom();
    }
}

function handleTouchEnd(e) {
    if (touchCount === 1 && zoomLevel === 1 && !isPanning) {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }
    isPanning = false;
    touchCount = e.touches.length;
}

function handleDoubleTap(e) {
    if (zoomLevel === 1) {
        // Zoom in to 2.5x
        const touch = e.touches[0];
        const rect = viewerImage.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        panX = (centerX - touch.clientX) * 0.6;
        panY = (centerY - touch.clientY) * 0.6;
        zoomLevel = 2.5;
    } else {
        // Reset zoom
        zoomLevel = 1;
        panX = 0;
        panY = 0;
    }
    applyZoom();
}

function getPinchDistance(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
}

// Mouse pan handlers
function handlePanStart(e) {
    if (zoomLevel > 1 && e.button === 0) {
        e.preventDefault();
        isPanning = true;
        panStartX = e.clientX - panX;
        panStartY = e.clientY - panY;
        viewerImage.style.cursor = 'grabbing';
    }
}

function handlePanMove(e) {
    if (isPanning && zoomLevel > 1) {
        e.preventDefault();
        panX = e.clientX - panStartX;
        panY = e.clientY - panStartY;
        applyZoom();
    }
}

function handlePanEnd() {
    if (isPanning) {
        isPanning = false;
        if (zoomLevel > 1) {
            viewerImage.style.cursor = 'grab';
        }
    }
}

function updateNavButtons() {
    // Show/hide navigation buttons based on current position and image count
    const hasMultipleImages = viewerImages.length > 1;

    viewerPrevBtn.style.display = hasMultipleImages ? 'flex' : 'none';
    viewerNextBtn.style.display = hasMultipleImages ? 'flex' : 'none';

    // Disable buttons at boundaries
    viewerPrevBtn.disabled = viewerCurrentIndex === 0;
    viewerNextBtn.disabled = viewerCurrentIndex === viewerImages.length - 1;
}

async function navigateToSetup(direction) {
    const newIndex = currentViewerSetupIndex + direction;
    if (newIndex >= 0 && newIndex < setups.length) {
        const nextSetup = setups[newIndex];
        // Check if the next setup has images before navigating
        if (nextSetup.id) {
            await openImageViewer(nextSetup);
        }
    }
}

function updateSetupNavButtons() {
    const hasMultipleSetups = setups.length > 1;

    // Show setup navigation only if there are multiple setups
    viewerSetupNav.style.display = hasMultipleSetups ? 'flex' : 'none';

    if (hasMultipleSetups && currentViewerSetupIndex >= 0) {
        // Update indicator
        viewerSetupIndicator.textContent = `${currentViewerSetupIndex + 1} / ${setups.length}`;

        // Disable buttons at boundaries
        viewerPrevSetupBtn.disabled = currentViewerSetupIndex === 0;
        viewerNextSetupBtn.disabled = currentViewerSetupIndex === setups.length - 1;
    }
}

// Helper Functions
function selectFolder(folderId, folderName) {
    currentFolderId = folderId.toString();
    pageTitle.textContent = folderName;

    // Update active state in folder list
    document.querySelectorAll('.folder-item').forEach(item => {
        item.classList.toggle('active', item.dataset.folderId === currentFolderId);
    });

    loadSetups();
}

function editFolder(folderId) {
    const folder = folders.find(f => f.id === folderId);
    if (folder) {
        openFolderModal(folder);
    }
}

function confirmDeleteFolder(folderId, folderName) {
    openDeleteFolderModal(folderId, folderName);
}

function confirmDeleteSetup(setupId, setupName) {
    openDeleteSetupModal(setupId, setupName);
}

function getSetupById(id) {
    return setups.find(s => s.id === id);
}

function updateColorPreview() {
    colorPreview.style.backgroundColor = folderColorInput.value;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = type === 'success'
        ? `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
               <polyline points="22 4 12 14.01 9 11.01"/>
           </svg>`
        : `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <circle cx="12" cy="12" r="10"/>
               <line x1="15" y1="9" x2="9" y2="15"/>
               <line x1="9" y1="9" x2="15" y2="15"/>
           </svg>`;

    toast.innerHTML = `
        ${icon}
        <span class="toast-message">${escapeHtml(message)}</span>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Make functions globally available
window.editFolder = editFolder;
window.confirmDeleteFolder = confirmDeleteFolder;
window.confirmDeleteSetup = confirmDeleteSetup;
window.getSetupById = getSetupById;
window.openSetupModal = openSetupModal;
