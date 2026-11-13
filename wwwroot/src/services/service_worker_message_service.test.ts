// H3 fallback: a tab that the service worker cannot navigate moves itself on its message.
import { expect, onTestFinished, test, vi } from 'vitest';
import { listenForNavigation } from './service_worker_message_service';

const FLASHCARD_URL = '/flashcard?wordIds=id-1%2Cid-2';

const stubServiceWorker = () => {
  const serviceWorker = new EventTarget();
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: serviceWorker });
  onTestFinished(() => {
    delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  });

  return serviceWorker;
};

const send = (serviceWorker: EventTarget, data: unknown) =>
  serviceWorker.dispatchEvent(new MessageEvent('message', { data }));

test('a navigate message of the service worker moves the tab to /flashcard?wordIds', () => {
  const serviceWorker = stubServiceWorker();
  const move = vi.fn();
  listenForNavigation(move);

  send(serviceWorker, { type: 'fuxi-navigate', url: FLASHCARD_URL });

  expect(move).toHaveBeenCalledWith(FLASHCARD_URL);
});

test.each([
  ['another type', { type: 'other', url: FLASHCARD_URL }],
  ['an address outside /flashcard', { type: 'fuxi-navigate', url: 'https://evil.test/flashcard' }],
  ['an address that only starts like /flashcard', { type: 'fuxi-navigate', url: '/flashcards' }],
  ['no data', null],
])('a message with %s does not move the tab', (_, data) => {
  const serviceWorker = stubServiceWorker();
  const move = vi.fn();
  listenForNavigation(move);

  send(serviceWorker, data);

  expect(move).not.toHaveBeenCalled();
});

test('a browser without service workers listens to nothing and throws nothing', () => {
  expect(() => listenForNavigation(vi.fn())).not.toThrow();
});
