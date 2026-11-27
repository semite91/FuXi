// How the tab a sign-in finished in tells the tab that opened it. Each source has its own result parameter.

const CHANNEL_NAME = 'fuxi-connection';

export interface ConnectionResult {
  /** The result parameter of the source, for example "spotify". */
  parameter: string;
  result: string;
}

const hasChannel = (): boolean => typeof BroadcastChannel !== 'undefined';

/** Tells the other tabs that a sign-in ended. */
export const announceConnection = (message: ConnectionResult): void => {
  if (!hasChannel()) {
    return;
  }

  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.postMessage(message);
  channel.close();
};

/** Calls onResult for each sign-in that ends in another tab; returns the function that stops listening. */
export const listenForConnection = (onResult: (message: ConnectionResult) => void): (() => void) => {
  if (!hasChannel()) {
    return () => undefined;
  }

  const channel = new BroadcastChannel(CHANNEL_NAME);
  channel.onmessage = (event: MessageEvent<ConnectionResult>) => onResult(event.data);

  return () => channel.close();
};
