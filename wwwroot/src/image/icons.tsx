// The stroke icons of the design. Every icon is decoration; its button carries the name.
import type { ReactNode } from 'react';

export type IconName =
  | 'menu'
  | 'close'
  | 'check'
  | 'previous'
  | 'next'
  | 'down'
  | 'up'
  | 'filter'
  | 'edit'
  | 'plus'
  | 'info';

const VIEW_BOX = '0 0 24 24';
const DEFAULT_SIZE = 24;
const DEFAULT_STROKE_WIDTH = 2;

const PATHS: Record<IconName, ReactNode> = {
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  previous: <path d="M15 5l-7 7 7 7" />,
  next: <path d="M9 5l7 7-7 7" />,
  down: <path d="M6 9l6 6 6-6" />,
  up: <path d="M6 15l6-6 6 6" />,
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  edit: (
    <>
      <path d="M4 20h4L19 9a2.1 2.1 0 0 0-4-4L4 16v4z" />
      <path d="M13.5 6.5l4 4" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  info: (
    <>
      <path d="M12 11v7" />
      <circle cx="12" cy="6" r="0.5" />
    </>
  ),
};

interface IconProps {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
}

export const Icon = ({ name, size = DEFAULT_SIZE, strokeWidth = DEFAULT_STROKE_WIDTH, className }: IconProps) => (
  <svg
    className={className}
    width={size}
    height={size}
    viewBox={VIEW_BOX}
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {PATHS[name]}
  </svg>
);
