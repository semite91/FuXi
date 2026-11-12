import './notification_permission.less';

interface NotificationPermissionProps {
  stateText: string;
  buttonLabel: string;
  isDisabled: boolean;
  onEnable: () => void;
}

const NotificationPermission = ({ stateText, buttonLabel, isDisabled, onEnable }: NotificationPermissionProps) => (
  <div className="notification-permission">
    <p className="notification-permission__state" role="status">
      {stateText}
    </p>
    <button type="button" className="notification-permission__button" disabled={isDisabled} onClick={onEnable}>
      {buttonLabel}
    </button>
  </div>
);

export default NotificationPermission;
