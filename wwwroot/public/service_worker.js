// FuXi service worker: shows the push notifications and opens the Flashcard page on a click.
// It is plain JavaScript, served unbundled at /service_worker.js, so it cannot import app code.

const NOTIFICATION_ICON = '/fuxi_192.png';
const FLASHCARD_PATH = '/flashcard';
const WORD_IDS_QUERY = 'wordIds';
const WINDOW_CLIENT_TYPE = 'window';
// The same message type is read by src/services/service_worker_message_service.ts.
const NAVIGATE_MESSAGE_TYPE = 'fuxi-navigate';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

const isFilledText = (value) => typeof value === 'string' && value !== '';

/** The payload {title, wordIds} of a push, or null when it is missing or not valid. */
const readPayload = (data) => {
  if (!data) {
    return null;
  }

  try {
    const payload = data.json();

    return payload && isFilledText(payload.title) && isFilledText(payload.wordIds) ? payload : null;
  } catch {
    return null;
  }
};

const showWordsNotification = async (data) => {
  const payload = readPayload(data);

  if (payload === null) {
    return;
  }

  await self.registration.showNotification(payload.title, {
    data: { wordIds: payload.wordIds },
    icon: NOTIFICATION_ICON,
  });
};

self.addEventListener('push', (event) => {
  event.waitUntil(showWordsNotification(event.data));
});

const flashcardUrl = (wordIds) =>
  isFilledText(wordIds) ? `${FLASHCARD_PATH}?${WORD_IDS_QUERY}=${encodeURIComponent(wordIds)}` : FLASHCARD_PATH;

/**
 * Moves an open tab to the url. navigate() fails on a tab that this worker does not control,
 * so the tab is then asked by a message to move itself.
 */
const moveTab = async (tab, url) => {
  try {
    if (typeof tab.navigate === 'function') {
      await tab.navigate(url);
      return;
    }
  } catch {
    // Falls back to the message below.
  }

  tab.postMessage({ type: NAVIGATE_MESSAGE_TYPE, url });
};

/** Focuses an open FuXi tab and moves it to the url. Only when none is open, a new window opens. */
const openFlashcard = async (url) => {
  const tabs = await self.clients.matchAll({ type: WINDOW_CLIENT_TYPE, includeUncontrolled: true });
  const tab = tabs[0];

  if (tab === undefined) {
    await self.clients.openWindow(url);
    return;
  }

  await tab.focus();
  await moveTab(tab, url);
};

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(openFlashcard(flashcardUrl(event.notification.data?.wordIds)));
});
