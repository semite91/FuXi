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

const NOTION_LOGO_PATH =
  'M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.139c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z';
const NOTION_LOGO_CLASS = 'notion-logo';

/** The Notion logo, a filled mark (simple-icons, CC0), not a stroke icon; its button carries the name. */
export const NotionLogo = ({ size = DEFAULT_SIZE }: { size?: number }) => (
  <svg className={NOTION_LOGO_CLASS} width={size} height={size} viewBox={VIEW_BOX} fill="currentColor" aria-hidden="true">
    <path d={NOTION_LOGO_PATH} />
  </svg>
);

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
