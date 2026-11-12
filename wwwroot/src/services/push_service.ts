// The Push Subscription of this browser: it is created with the VAPID public key and stored by the backend.
import { decodeBase64Url } from '../utils/base64_url';
import { API_URL_KEY, createApiClient } from './api_client';

const GET_VAPID_PUBLIC_KEY = '/api/GetVapidPublicKey';
const SAVE_PUSH_SUBSCRIPTION = '/api/SavePushSubscription';
const MISSING_KEY_MESSAGE = 'The VAPID public key is missing.';
const INCOMPLETE_SUBSCRIPTION_MESSAGE = 'The push subscription has no endpoint or keys.';

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

/** The existing subscription is reused. Only without one is the key asked and a new one created. */
const findOrCreateSubscription = async (): Promise<PushSubscription> => {
  const { pushManager } = await navigator.serviceWorker.ready;
  const existing = await pushManager.getSubscription();

  if (existing !== null) {
    return existing;
  }

  const publicKey = await getVapidPublicKey();

  return pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodeBase64Url(publicKey) });
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
