// "Enable notifications": the permission is asked only on a click, then this browser is subscribed to push.
import { useRef, useState } from 'react';
import { getPermissionState, requestPermission, type PermissionState } from '../services/notification_permission_service';
import { subscribeToPush } from '../services/push_service';

const GRANTED: PermissionState = 'granted';
const BLOCKING_STATES: readonly PermissionState[] = ['denied', 'unsupported'];

export const useNotificationPermission = () => {
  const [permission, setPermission] = useState<PermissionState>(getPermissionState);
  const [isPending, setIsPending] = useState(false);
  const [hasFailed, setHasFailed] = useState(false);
  const isEnabling = useRef(false);

  const enable = async () => {
    if (isEnabling.current) {
      return;
    }

    isEnabling.current = true;
    setIsPending(true);
    setHasFailed(false);

    try {
      const answer = await requestPermission();

      if (answer !== GRANTED) {
        setPermission(answer);
        return;
      }

      // "allowed" is shown only once the subscription is saved; on a failure the previous state stays.
      await subscribeToPush();
      setPermission(GRANTED);
    } catch {
      setHasFailed(true);
    } finally {
      isEnabling.current = false;
      setIsPending(false);
    }
  };

  return {
    permission,
    hasFailed,
    canEnable: !isPending && !BLOCKING_STATES.includes(permission),
    enable,
  };
};
