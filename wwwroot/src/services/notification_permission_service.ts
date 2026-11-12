// Reads and asks the browser's notification permission. Subscribing is added in the Notifications phase.

export type PermissionState = NotificationPermission | 'unsupported';

const UNSUPPORTED: PermissionState = 'unsupported';

const isSupported = (): boolean => 'Notification' in window;

export const getPermissionState = (): PermissionState => (isSupported() ? Notification.permission : UNSUPPORTED);

export const requestPermission = async (): Promise<PermissionState> =>
  isSupported() ? Notification.requestPermission() : UNSUPPORTED;
