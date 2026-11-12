import type { ReactNode } from 'react';
import './page_card.less';

const LAYOUT_CLASSES = {
  page: 'page-card',
  centered: 'page-card page-card--centered',
} as const;

interface PageCardProps {
  children: ReactNode;
  layout?: keyof typeof LAYOUT_CLASSES;
}

/** The white rounded container of every page. */
const PageCard = ({ children, layout = 'page' }: PageCardProps) => (
  <section className={LAYOUT_CLASSES[layout]}>{children}</section>
);

export default PageCard;
