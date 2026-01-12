// Service Worker for Trading Bot Manager PWA

// Cache name for offline support
const CACHE_NAME = 'tradingbot-v1';

// Install event - cache essential assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing service worker...');
    self.skipWaiting();
});

// Activate event - cleanup old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating service worker...');
    event.waitUntil(clients.claim());
});

// Push notification event
self.addEventListener('push', (event) => {
    console.log('[SW] Push notification received');

    let data = {
        title: 'Price Alert',
        body: 'A price alert was triggered!',
        symbol: ''
    };

    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    // Determine URL based on event type
    let notificationUrl = '/';
    let notificationTag = 'price-alert-' + (data.symbol || 'general');
    let actions = [
        { action: 'view', title: 'View Dashboard' },
        { action: 'dismiss', title: 'Dismiss' }
    ];

    if (data.event_type === 'signal') {
        notificationUrl = '/quick-trade';
        notificationTag = 'signal-' + (data.symbol || 'general');
        actions = [
            { action: 'trade', title: 'Open Quick Trade' },
            { action: 'dismiss', title: 'Dismiss' }
        ];
    }

    const options = {
        body: data.body,
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        vibrate: [200, 100, 200, 100, 200],
        tag: notificationTag,
        renotify: true,
        requireInteraction: true,
        data: {
            url: notificationUrl,
            symbol: data.symbol,
            event_type: data.event_type
        },
        actions: actions
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notification clicked:', event.action);

    event.notification.close();

    if (event.action === 'dismiss') {
        return;
    }

    // Determine URL based on action
    let targetUrl = event.notification.data.url || '/';
    if (event.action === 'trade') {
        targetUrl = '/quick-trade';
    } else if (event.action === 'view') {
        targetUrl = '/';
    }

    // Open the app when notification is clicked
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // If app is already open, focus it and navigate
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        client.navigate(targetUrl);
                        return client.focus();
                    }
                }
                // Otherwise open a new window
                if (clients.openWindow) {
                    return clients.openWindow(targetUrl);
                }
            })
    );
});

// Background sync (future enhancement)
self.addEventListener('sync', (event) => {
    console.log('[SW] Background sync:', event.tag);
});
