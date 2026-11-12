import { useEffect, useRef, type ReactNode } from 'react';
import './dialog.less';

const ESCAPE_KEY = 'Escape';
const KEY_DOWN_EVENT = 'keydown';
const NOT_TABBABLE = -1;

const VARIANT_CLASSES = {
  center: 'dialog dialog--center',
  panel: 'dialog dialog--panel',
} as const;

interface DialogProps {
  /** The accessible name of the dialog. */
  label: string;
  /** The accessible name of the backdrop, which closes the dialog. */
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  variant?: keyof typeof VARIANT_CLASSES;
}

/**
 * A modal box over its page. It takes the focus when it opens, gives it back
 * when it closes, and closes on Escape or a click on the backdrop.
 */
const Dialog = ({ label, closeLabel, onClose, children, variant = 'center' }: DialogProps) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement;
    boxRef.current?.focus();

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === ESCAPE_KEY) {
        onCloseRef.current();
      }
    };
    document.addEventListener(KEY_DOWN_EVENT, closeOnEscape);

    return () => {
      document.removeEventListener(KEY_DOWN_EVENT, closeOnEscape);
      if (opener instanceof HTMLElement) {
        opener.focus();
      }
    };
  }, []);

  return (
    <div className={VARIANT_CLASSES[variant]}>
      <button
        type="button"
        className="dialog__backdrop"
        aria-label={closeLabel}
        tabIndex={NOT_TABBABLE}
        onClick={onClose}
      />
      <div className="dialog__box" role="dialog" aria-modal="true" aria-label={label} tabIndex={NOT_TABBABLE} ref={boxRef}>
        {children}
      </div>
    </div>
  );
};

export default Dialog;
