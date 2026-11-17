import { useId, type ReactNode } from 'react';
import { Icon } from '../../image/icons';
import './disclosure_toggle.less';

const ARROW_ICON_SIZE = 18;
const ARROW_ICON_STROKE = 2.25;

interface DisclosureToggleProps {
  label: string;
  /** The page keeps the open state; the toggle only shows it. */
  isOpen: boolean;
  onToggle: () => void;
  /** Shown under the toggle while it is open. */
  children: ReactNode;
  /** Lines the toggle up with the rows above it instead of insetting it. */
  isFlush?: boolean;
}

const BUTTON_CLASSES = {
  inset: 'disclosure-toggle__button',
  flush: 'disclosure-toggle__button disclosure-toggle__button--flush',
} as const;

const ICON_CLASSES = {
  closed: 'disclosure-toggle__icon',
  open: 'disclosure-toggle__icon disclosure-toggle__icon--open',
} as const;

/**
 * A text button with a down arrow that turns when open, and the content it shows.
 * The content is drawn only while open, so aria-controls names it only then; it never points to a missing element.
 */
const DisclosureToggle = ({ label, isOpen, onToggle, children, isFlush = false }: DisclosureToggleProps) => {
  const contentId = useId();

  return (
    <div className="disclosure-toggle">
      <button
        type="button"
        className={isFlush ? BUTTON_CLASSES.flush : BUTTON_CLASSES.inset}
        aria-expanded={isOpen}
        aria-controls={isOpen ? contentId : undefined}
        onClick={onToggle}
      >
        {label}
        <Icon
          name="down"
          size={ARROW_ICON_SIZE}
          strokeWidth={ARROW_ICON_STROKE}
          className={isOpen ? ICON_CLASSES.open : ICON_CLASSES.closed}
        />
      </button>
      {isOpen && (
        <div id={contentId} className="disclosure-toggle__content">
          {children}
        </div>
      )}
    </div>
  );
};

export default DisclosureToggle;
