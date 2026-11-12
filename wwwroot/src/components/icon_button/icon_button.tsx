import type { ButtonHTMLAttributes } from 'react';
import { Icon, type IconName } from '../../image/icons';
import './icon_button.less';

const SHAPE_CLASSES = {
  round: 'icon-button icon-button--round',
  small: 'icon-button icon-button--small',
  square: 'icon-button icon-button--square',
  plain: 'icon-button icon-button--plain',
} as const;

const ICON_SIZES = { round: 18, small: 16, square: 24, plain: 24 } as const;

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label'> {
  icon: IconName;
  /** The accessible name, because the button has no text. */
  label: string;
  shape?: keyof typeof SHAPE_CLASSES;
  iconSize?: number;
}

const IconButton = ({ icon, label, shape = 'round', iconSize, className, ...buttonProps }: IconButtonProps) => (
  <button
    type="button"
    {...buttonProps}
    className={className ? `${SHAPE_CLASSES[shape]} ${className}` : SHAPE_CLASSES[shape]}
    aria-label={label}
  >
    <Icon name={icon} size={iconSize ?? ICON_SIZES[shape]} />
  </button>
);

export default IconButton;
