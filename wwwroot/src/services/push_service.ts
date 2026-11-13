// The Push Subscription of this browser: it is created with the VAPID public key and stored by the backend.
import { decodeBase64Url } from '../utils/base64_url';
import { API_URL_KEY, createApiClient } from './api_client';

const GET_VAPID_PUBLIC_KEY = '/api/GetVapidPublicKey';
const SAVE_PUSH_SUBSCRIPTION = '/api/SavePushSubscription';
const MISSING_KEY_MESSAGE = 'The VAPID public key is missing.';
const INCOMPLETE_SUBSCRIPTION_MESSAGE = 'The push subscription has no endpoint or keys.';
const NOT_READY_MESSAGE = 'The service worker is not ready.';
// navigator.serviceWorker.ready never settles when the registration failed.
const SERVICE_WORKER_READY_TIMEOUT_MS = 10_000;

interface VapidPublicKey {
  publicKey: string;
}

/** The flat body of SavePushSubscription. The browser nests p256dh and auth under keys. */
export interface PushSubscriptionBody {
  endpoint: string;
  p256dh: string;
  auth: string;
}

const client = createApiClient(API_URL_KEY);

export const isPushSupported = (): boolean => 'serviceWorker' in navigator && 'PushManager' in window;

export const getVapidPublicKey = async (): Promise<string> => {
  const answer = await client.get<VapidPublicKey | undefined>(GET_VAPID_PUBLIC_KEY);

  if (!answer?.publicKey) {
    throw new Error(MISSING_KEY_MESSAGE);
  }

  return answer.publicKey;
};

export const savePushSubscription = (body: PushSubscriptionBody): Promise<void> =>
  client.post(SAVE_PUSH_SUBSCRIPTION, body);

/** The service worker registration, or a rejection when it is not ready in time. */
const waitForServiceWorker = (): Promise<ServiceWorkerRegistration> => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(NOT_READY_MESSAGE)), SERVICE_WORKER_READY_TIMEOUT_MS);
  });

  return Promise.race([navigator.serviceWorker.ready, timeout]).finally(() => clearTimeout(timer));
};

/** Compares the key of a subscription with the current key, byte by byte. O(n). */
const isSameKey = (subscriptionKey: ArrayBuffer | null, currentKey: Uint8Array): boolean => {
  if (subscriptionKey === null || subscriptionKey.byteLength !== currentKey.length) {
    return false;
  }

  const bytes = new Uint8Array(subscriptionKey);

  return bytes.every((byte, index) => byte === currentKey[index]);
};

/**
 * An existing subscription made with the current key is reused. One made with another key
 * (the key pair was rotated) or with no key is removed, and a new one is made with the current key.
 */
const findOrCreateSubscription = async (): Promise<PushSubscription> => {
  const { pushManager } = await waitForServiceWorker();
  const existing = await pushManager.getSubscription();
  const currentKey = decodeBase64Url(await getVapidPublicKey());

  if (existing !== null) {
    if (isSameKey(existing.options.applicationServerKey, currentKey)) {
      return existing;
    }

    await existing.unsubscribe();
  }

  return pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: currentKey });
};

/** toJSON gives the keys already in URL-safe Base64. */
const toSubscriptionBody = (subscription: PushSubscription): PushSubscriptionBody => {
  const { endpoint, keys } = subscription.toJSON();

  if (!endpoint || !keys?.p256dh || !keys.auth) {
    throw new Error(INCOMPLETE_SUBSCRIPTION_MESSAGE);
  }

  return { endpoint, p256dh: keys.p256dh, auth: keys.auth };
};

/** Subscribes this browser to push notifications and sends the subscription to the backend. */
export const subscribeToPush = async (): Promise<void> =>
  savePushSubscription(toSubscriptionBody(await findOrCreateSubscription()));
