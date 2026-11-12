// Moves the tab when the service worker asks for it, because it cannot navigate a tab it does not control.
import { ROUTES } from '../constants/routes';

// The same message type is sent by public/service_worker.js.
const NAVIGATE_MESSAGE_TYPE = 'fuxi-navigate';
const MESSAGE_EVENT = 'message';
const QUERY_START = '?';

interface NavigateMessage {
  type?: unknown;
  url?: unknown;
}

/** Only the Flashcard page can be opened by a message. */
const isFlashcardAddress = (url: unknown): url is string =>
  typeof url === 'string' && (url === ROUTES.flashcard || url.startsWith(`${ROUTES.flashcard}${QUERY_START}`));

const moveTo = (url: string): void => window.location.assign(url);

export const listenForNavigation = (move: (url: string) => void = moveTo): void => {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  navigator.serviceWorker.addEventListener(MESSAGE_EVENT, (event: MessageEvent<NavigateMessage | null>) => {
    const { type, url } = event.data ?? {};

    if (type === NAVIGATE_MESSAGE_TYPE && isFlashcardAddress(url)) {
      move(url);
    }
  });
};
