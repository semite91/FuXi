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
  | 'info'
  | 'save';

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
  // A floppy disk: the outline with a cut corner, the label below and the shutter above.
  save: (
    <>
      <path d="M5 4h11l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
      <path d="M8 20v-6h8v6M8 4v4h7V4" />
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
const GOOGLE_DRIVE_LOGO_PATH =
  'M12.01 1.485c-2.082 0-3.754.02-3.743.047.01.02 1.708 3.001 3.774 6.62l3.76 6.574h3.76c2.081 0 3.753-.02 3.742-.047-.005-.02-1.708-3.001-3.775-6.62l-3.76-6.574zm-4.76 1.73a789.828 789.861 0 0 0-3.63 6.319L0 15.868l1.89 3.298 1.885 3.297 3.62-6.335 3.618-6.33-1.88-3.287C8.1 4.704 7.255 3.22 7.25 3.214zm2.259 12.653-.203.348c-.114.198-.96 1.672-1.88 3.287a423.93 423.948 0 0 1-1.698 2.97c-.01.026 3.24.042 7.222.042h7.244l1.796-3.157c.992-1.734 1.85-3.23 1.906-3.323l.104-.167h-7.249z';
const GOOGLE_DRIVE_LOGO_CLASS = 'google-drive-logo';

interface LogoProps {
  size?: number;
}

/** A filled brand mark (simple-icons 13.0.0, CC0), not a stroke icon; its button carries the name. */
const BrandLogo = ({ className, path, size = DEFAULT_SIZE }: LogoProps & { className: string; path: string }) => (
  <svg className={className} width={size} height={size} viewBox={VIEW_BOX} fill="currentColor" aria-hidden="true">
    <path d={path} />
  </svg>
);

export const NotionLogo = ({ size }: LogoProps) => <BrandLogo className={NOTION_LOGO_CLASS} path={NOTION_LOGO_PATH} size={size} />;

export const GoogleDriveLogo = ({ size }: LogoProps) => (
  <BrandLogo className={GOOGLE_DRIVE_LOGO_CLASS} path={GOOGLE_DRIVE_LOGO_PATH} size={size} />
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
