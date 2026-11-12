import { useId, useState, type ReactElement } from 'react';
import { cloneElement } from 'react';
import './tooltip.less';

interface TooltipProps {
  text: string;
  /** The control that the tooltip describes. */
  children: ReactElement<{ 'aria-describedby'?: string }>;
}

/** Shows its text while the control is hovered or focused. */
const Tooltip = ({ text, children }: TooltipProps) => {
  const tooltipId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const open = () => setIsOpen(true);
  const close = () => setIsOpen(false);

  return (
    <span className="tooltip" onMouseEnter={open} onMouseLeave={close} onFocus={open} onBlur={close}>
      {cloneElement(children, { 'aria-describedby': isOpen ? tooltipId : undefined })}
      {isOpen && (
        <span className="tooltip__text" id={tooltipId} role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
};

export default Tooltip;
