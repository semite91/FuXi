import type { ReactNode } from 'react';
import './page_card.less';

const LAYOUT_CLASSES = {
  page: 'page-card',
  centered: 'page-card page-card--centered',
} as const;

interface PageCardProps {
  children: ReactNode;
  /** The page title. Without it the card has no title row. */
  title?: string;
  /** A control at the right of the title. */
  action?: ReactNode;
  layout?: keyof typeof LAYOUT_CLASSES;
}

/** The white rounded container of every page. */
const PageCard = ({ children, title, action, layout = 'page' }: PageCardProps) => (
  <section className={LAYOUT_CLASSES[layout]}>
    {title !== undefined && (
      <div className="page-card__head">
        <h1 className="page-card__title">{title}</h1>
        {action}
      </div>
    )}
    {children}
  </section>
);

export default PageCard;
