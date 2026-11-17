import { Icon } from '../../image/icons';
import Tooltip, { type TooltipPlacement } from '../tooltip/tooltip';
import './info_tooltip.less';

const INFO_ICON_SIZE = 12;
const INFO_ICON_STROKE = 3.6;

interface InfoTooltipProps {
  /** The button's name, for example "About Notion". */
  label: string;
  text: string;
  placement?: TooltipPlacement;
}

/** A small round i button that shows a tip on hover, focus or a tap; a second tap hides it. */
const InfoTooltip = ({ label, text, placement }: InfoTooltipProps) => (
  <Tooltip text={text} placement={placement} opensOnClick>
    <button type="button" className="info-tooltip__button" aria-label={label}>
      <Icon name="info" size={INFO_ICON_SIZE} strokeWidth={INFO_ICON_STROKE} />
    </button>
  </Tooltip>
);

export default InfoTooltip;
