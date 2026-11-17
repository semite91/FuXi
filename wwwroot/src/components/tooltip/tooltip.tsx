import { cloneElement, useId, useRef, useState, type KeyboardEvent, type ReactElement } from 'react';
import './tooltip.less';

const ESCAPE_KEY = 'Escape';
const TEXT_CLASSES = {
  end: 'tooltip__text',
  start: 'tooltip__text tooltip__text--start',
} as const;

export type TooltipPlacement = keyof typeof TEXT_CLASSES;

interface TooltipProps {
  text: string;
  /** The control that the tooltip describes. */
  children: ReactElement<{ 'aria-describedby'?: string }>;
  /** end: the text ends at the control's right edge and grows to the left. start: it starts at its left edge, for a control near the left of the screen. */
  placement?: TooltipPlacement;
  /** For a control whose only job is the tip, such as an i button: a click or tap shows it, and a second one hides it. */
  opensOnClick?: boolean;
}

/** Shows its text while the control is hovered or focused. Escape hides it. */
const Tooltip = ({ text, children, placement = 'end', opensOnClick = false }: TooltipProps) => {
  const tooltipId = useId();
  const [isOpen, setIsOpen] = useState(false);
  // Read at the pointer down, before the focus of the same tap opens the tip.
  const wasOpenAtPointerDown = useRef(false);
  const open = () => setIsOpen(true);
  const close = () => setIsOpen(false);
  const closeOnEscape = (event: KeyboardEvent) => {
    if (event.key === ESCAPE_KEY) {
      close();
    }
  };
  const rememberOpenState = () => {
    wasOpenAtPointerDown.current = isOpen;
  };
  const toggle = () => {
    setIsOpen(!wasOpenAtPointerDown.current);
    wasOpenAtPointerDown.current = false;
  };

  return (
    <span
      className="tooltip"
      onMouseEnter={open}
      onMouseLeave={close}
      onFocus={open}
      onBlur={close}
      onPointerDown={opensOnClick ? rememberOpenState : undefined}
      onClick={opensOnClick ? toggle : undefined}
      onKeyDown={closeOnEscape}
    >
      {cloneElement(children, { 'aria-describedby': isOpen ? tooltipId : undefined })}
      {isOpen && (
        <span className={TEXT_CLASSES[placement]} id={tooltipId} role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
};

export default Tooltip;
