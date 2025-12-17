# Project Notes for Claude

## Project Overview
Trading website with setups management, folders, and image viewing functionality.

## Recent Changes (Dec 2024)

### Setup Viewer Modal Redesign
Completely redesigned the setup viewer modal with new layout:

**Structure (top to bottom):**
1. Setup name header (gold colored)
2. Image carousel with left/right nav arrows overlaid
3. Indicator dots (clickable, shows current image)
4. Setup description section
5. Previous/Next setup navigation buttons

**Key Files:**
- `templates/setups.html` - Modal HTML structure (lines ~308-368)
- `static/setups.js` - Viewer logic, swipe support, navigation functions
- `static/setups.css` - Styling with mobile responsive design

**JavaScript Functions:**
- `openImageViewer(setup)` - Opens modal, loads images, shows description
- `renderViewerIndicators()` - Creates dot indicators for images
- `showViewerImage(index)` - Displays specific image, updates dots
- `navigateViewerImage(direction)` - Navigate between images (-1 or 1)
- `handleSwipe()` - Touch gesture handling for mobile
- `updateNavButtons()` - Show/hide and enable/disable image nav buttons
- `navigateToSetup(direction)` - Go to prev/next setup in folder
- `updateSetupNavButtons()` - Update setup navigation state

**CSS Classes:**
- `.setup-viewer-modal` - Main modal container
- `.setup-viewer-carousel` - Image area with nav buttons
- `.carousel-nav-btn` - Left/right image navigation
- `.carousel-indicators` / `.carousel-dot` - Image position dots
- `.setup-viewer-description` - Description section
- `.setup-viewer-nav` / `.setup-nav-btn` - Setup navigation

**Features:**
- Mobile swipe gestures (touchstart/touchend)
- Keyboard navigation (left/right arrows)
- Fullscreen on mobile (<640px)
- Disabled states at boundaries

## Tech Stack
- Python Flask backend
- Vanilla JavaScript frontend
- SQLite database
- CSS with mobile-first responsive design

## File Structure
```
/static
  /setups.js    - Setups page logic
  /setups.css   - Setups page styles
/templates
  /setups.html  - Setups page template
/app.py         - Flask routes
/database.py    - Database models
```
