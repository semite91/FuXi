import { Children, useEffect, useId, useRef, type ReactNode } from 'react';
import IconButton from '../icon_button/icon_button';
import './dialog.less';

const ESCAPE_KEY = 'Escape';
const KEY_DOWN_EVENT = 'keydown';
const NOT_TABBABLE = -1;
const STATUS_ROLE = 'status';

const VARIANT_CLASSES = {
  center: 'dialog dialog--center',
  panel: 'dialog dialog--panel',
} as const;

const HEADER_CLASSES = {
  start: 'dialog__header',
  center: 'dialog__header dialog__header--center',
} as const;

/** React draws nothing for undefined, null and booleans, also inside arrays, so such content gets no body. */
const hasContent = (children: ReactNode) => Children.toArray(children).length > 0;

interface DialogProps {
  /** The title in the header row, which is also the accessible name of the dialog. */
  label: string;
  /** The accessible name of the close (X) button. */
  closeLabel: string;
  onClose: () => void;
  /** The body under the header row. A dialog that only shows its title has none. */
  children?: ReactNode;
  variant?: keyof typeof VARIANT_CLASSES;
  /** A small line under the title. */
  subtitle?: string;
  /** A picture above the title, hidden from screen readers by its owner. */
  icon?: ReactNode;
  isTitleCentered?: boolean;
  /** The title is announced as a status, for a dialog that shows a result. */
  isTitleStatus?: boolean;
}

/**
 * A modal box over its page. A fixed header row holds the title and the close (X) button,
 * and only the body under it scrolls. It takes the focus when it opens, gives it back
 * when it closes, and closes on the X, Escape or a click on the backdrop.
 * The backdrop is for the pointer only; screen readers and keyboards get the X.
 */
const Dialog = ({
  label,
  closeLabel,
  onClose,
  children,
  variant = 'center',
  subtitle,
  icon,
  isTitleCentered = false,
  isTitleStatus = false,
}: DialogProps) => {
  const titleId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement;
    // Without preventScroll the browser scrolls the page toward a panel that is still sliding in.
    boxRef.current?.focus({ preventScroll: true });

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === ESCAPE_KEY) {
        onCloseRef.current();
      }
    };
    document.addEventListener(KEY_DOWN_EVENT, closeOnEscape);

    return () => {
      document.removeEventListener(KEY_DOWN_EVENT, closeOnEscape);
      if (opener instanceof HTMLElement) {
        opener.focus({ preventScroll: true });
      }
    };
  }, []);

  return (
    <div className={VARIANT_CLASSES[variant]}>
      <div className="dialog__backdrop" aria-hidden="true" onClick={onClose} />
      <div className="dialog__box" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={NOT_TABBABLE} ref={boxRef}>
        <div className={isTitleCentered ? HEADER_CLASSES.center : HEADER_CLASSES.start}>
          {/* First in the focus order; the stylesheet places it at the top right. */}
          <IconButton icon="close" shape="small" label={closeLabel} className="dialog__close" onClick={onClose} />
          {/* The status role sits on the heading block, so the title keeps its heading role. */}
          <div className="dialog__heading" role={isTitleStatus ? STATUS_ROLE : undefined}>
            {icon}
            <h2 id={titleId} className="dialog__title">
              {label}
            </h2>
            {subtitle !== undefined && <p className="dialog__subtitle">{subtitle}</p>}
          </div>
        </div>
        {hasContent(children) && <div className="dialog__body">{children}</div>}
      </div>
    </div>
  );
};

export default Dialog;
