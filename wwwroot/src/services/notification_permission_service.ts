// Reads and asks the browser's notification permission. A browser without push is "unsupported".
import { isPushSupported } from './push_service';

export type PermissionState = NotificationPermission | 'unsupported';

const UNSUPPORTED: PermissionState = 'unsupported';

const isSupported = (): boolean => 'Notification' in window && isPushSupported();

export const getPermissionState = (): PermissionState => (isSupported() ? Notification.permission : UNSUPPORTED);

export const requestPermission = async (): Promise<PermissionState> =>
  isSupported() ? Notification.requestPermission() : UNSUPPORTED;
