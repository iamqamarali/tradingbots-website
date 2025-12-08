<!-- 8ea47c13-5896-41e3-83e1-7e7c7f28e894 b2a2b858-d360-4b5d-8e43-caa458678adc -->
# Smooth Log Display

## Changes to script.js

1. **Track displayed logs** - Keep count of logs already shown to only append new ones
2. **Smart auto-scroll** - Only scroll if user is already near the bottom (not reading old logs)
3. **Append-only updates** - Add new log lines instead of replacing entire content
4. **Slower polling** - Increase interval from 2s to 10s (no need for instant updates)
5. **Fade-in animation** - New logs appear with subtle animation

## Changes to style.css

1. **Add smooth scroll behavior** to logs container
2. **Add fade-in animation** for new log entries

## Files to Modify

- `static/script.js` - Log fetching and rendering logic
- `static/style.css` - Animations and smooth scroll

### To-dos

- [ ] Add restart_persistent_scripts() function that runs on app startup
- [ ] Update run_script to save was_running: true to metadata
- [ ] Update stop_script to save was_running: false to metadata
- [ ] Add PUT /api/scripts/<id>/auto-restart endpoint
- [ ] Add auto-restart toggle switch to index.html
- [ ] Add toggle handler and state management in script.js