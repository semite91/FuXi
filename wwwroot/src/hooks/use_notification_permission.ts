// The notification permission of the browser. It is asked only when the Learner clicks the button.
import { useState } from 'react';
import { getPermissionState, requestPermission, type PermissionState } from '../services/notification_permission_service';

export const useNotificationPermission = () => {
  const [permission, setPermission] = useState<PermissionState>(getPermissionState);

  const enable = async () => setPermission(await requestPermission());

  return { permission, enable };
};
