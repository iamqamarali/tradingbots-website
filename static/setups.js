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
let currentZoom = 100;
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

// Image Viewer Modal
const imageViewerModal = document.getElementById('imageViewerModal');
const viewerImage = document.getElementById('viewerImage');
const viewerTitle = document.getElementById('viewerTitle');
const viewerTabs = document.getElementById('viewerTabs');
const viewerImageContainer = document.getElementById('viewerImageContainer');
const viewerNotes = document.getElementById('viewerNotes');
const viewerNotesText = document.getElementById('viewerNotesText');
const closeImageViewer = document.getElementById('closeImageViewer');
const zoomInBtn = document.getElementById('zoomInBtn');
const zoomOutBtn = document.getElementById('zoomOutBtn');
const zoomResetBtn = document.getElementById('zoomResetBtn');
const zoomLevel = document.getElementById('zoomLevel');

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

    // Zoom controls
    zoomInBtn.addEventListener('click', () => setZoom(currentZoom + 25));
    zoomOutBtn.addEventListener('click', () => setZoom(currentZoom - 25));
    zoomResetBtn.addEventListener('click', () => setZoom(100));

    // Delete Setup Modal
    closeDeleteSetupModal.addEventListener('click', () => closeDeleteSetupModalFn());
    cancelDeleteSetupBtn.addEventListener('click', () => closeDeleteSetupModalFn());
    confirmDeleteSetupBtn.addEventListener('click', deleteSetup);

    // Image Viewer Modal
    closeImageViewer.addEventListener('click', () => closeImageViewerFn());
    imageViewerModal.addEventListener('click', (e) => {
        if (e.target === imageViewerModal) closeImageViewerFn();
    });

    // Close modals on escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeFolderModalFn();
            closeDeleteFolderModalFn();
            closeSetupModalFn();
            closeDeleteSetupModalFn();
            closeImageViewerFn();
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
        for (const img of setupImages) {
            if (img.toDelete && img.id) {
                // Delete existing image
                await fetch(`/api/setup-images/${img.id}`, { method: 'DELETE' });
            } else if (img.isNew && img.image_data) {
                // Create new image
                await fetch(`/api/setups/${setupId}/images`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        timeframe: img.timeframe,
                        image_data: img.image_data,
                        notes: img.notes || ''
                    })
                });
            } else if (img.isModified && img.id) {
                // Update existing image
                await fetch(`/api/setup-images/${img.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        timeframe: img.timeframe,
                        notes: img.notes || ''
                    })
                });
            }
        }

        showToast(editingSetupId ? 'Setup updated' : 'Setup created', 'success');
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
    viewerTitle.textContent = setup.name;
    viewerImages = [];
    viewerCurrentIndex = 0;
    currentZoom = 100;

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

    renderViewerTabs();
    showViewerImage(0);
    setZoom(100);
    imageViewerModal.classList.add('active');
}

function closeImageViewerFn() {
    imageViewerModal.classList.remove('active');
    currentZoom = 100;
    viewerImages = [];
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
    const allTimeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'];
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
function renderViewerTabs() {
    viewerTabs.innerHTML = '';

    if (viewerImages.length <= 1) {
        viewerTabs.style.display = 'none';
        return;
    }

    viewerTabs.style.display = 'flex';

    viewerImages.forEach((img, index) => {
        const tab = document.createElement('button');
        tab.className = `viewer-tab${viewerCurrentIndex === index ? ' active' : ''}`;
        tab.textContent = img.timeframe ? img.timeframe.toUpperCase() : `Image ${index + 1}`;
        tab.onclick = () => showViewerImage(index);
        viewerTabs.appendChild(tab);
    });
}

function showViewerImage(index) {
    if (index < 0 || index >= viewerImages.length) return;

    viewerCurrentIndex = index;
    const img = viewerImages[index];

    viewerImage.src = img.src;

    // Update tab active states
    viewerTabs.querySelectorAll('.viewer-tab').forEach((tab, i) => {
        tab.classList.toggle('active', i === index);
    });

    // Show notes if available
    if (img.notes && img.notes.trim()) {
        viewerNotesText.textContent = img.notes;
        viewerNotes.style.display = 'block';
    } else {
        viewerNotes.style.display = 'none';
    }

    // Reset zoom when switching images
    setZoom(100);
}

function setZoom(level) {
    currentZoom = Math.max(25, Math.min(300, level));
    zoomLevel.textContent = `${currentZoom}%`;
    viewerImage.style.transform = `scale(${currentZoom / 100})`;
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
