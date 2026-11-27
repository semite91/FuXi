import { dismissToast, useToasts, type ToastKind } from '../../services/toast_store';
import './toast.less';

interface ToastRegionProps {
  closeLabel: string;
}

const KIND_ROLES: Record<ToastKind, 'status' | 'alert'> = {
  progress: 'status',
  success: 'status',
  error: 'alert',
};

/** The toasts at the top right of every page. A progress toast has no close button: it changes when its work ends. */
const ToastRegion = ({ closeLabel }: ToastRegionProps) => {
  const toasts = useToasts();

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="toast-region">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast--${toast.kind}`} role={KIND_ROLES[toast.kind]}>
          {toast.kind === 'progress' && <span className="toast__spinner" aria-hidden="true" />}
          <span className="toast__text">{toast.text}</span>
          {toast.kind !== 'progress' && (
            <button type="button" className="toast__close" aria-label={closeLabel} onClick={() => dismissToast(toast.id)}>
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
};

export default ToastRegion;
