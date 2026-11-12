import type { ReactNode } from 'react';
import { Icon } from '../../image/icons';
import IconButton from '../icon_button/icon_button';
import Tooltip from '../tooltip/tooltip';
import './flashcard_back.less';

const HISTORY_ICON_SIZE = 18;
const HISTORY_ICON_STROKE = 2.25;

interface FlashcardBackProps {
  translation: string;
  /** The Word Content, its loading state or its missing state. */
  content: ReactNode;
  cardCount: number;
  cardIndex: number;
  reinforcementLabel: string;
  previousLabel: string;
  nextLabel: string;
  doneLabel: string;
  historyLabel: string;
  onReinforce: () => void;
  /** Without a handler the arrow or the button is not shown. */
  onPrevious?: () => void;
  onNext?: () => void;
  onDone?: () => void;
  isHistoryOpen: boolean;
  onToggleHistory: () => void;
  /** The Word History list or its state. Shown while the toggle is open. */
  history: ReactNode;
  notice?: ReactNode;
}

const FlashcardBack = ({
  translation,
  content,
  cardCount,
  cardIndex,
  reinforcementLabel,
  previousLabel,
  nextLabel,
  doneLabel,
  historyLabel,
  onReinforce,
  onPrevious,
  onNext,
  onDone,
  isHistoryOpen,
  onToggleHistory,
  history,
  notice,
}: FlashcardBackProps) => (
  <div className="flashcard-back">
    <div className="flashcard-back__reinforcement">
      <Tooltip text={reinforcementLabel}>
        <IconButton icon="close" shape="small" label={reinforcementLabel} onClick={onReinforce} />
      </Tooltip>
    </div>

    <div className="flashcard-back__main">
      {onPrevious ? (
        <IconButton icon="previous" shape="plain" label={previousLabel} onClick={onPrevious} />
      ) : (
        <span className="flashcard-back__arrow-space" />
      )}
      <div className="flashcard-back__body" aria-live="polite">
        <h2 className="flashcard-back__translation">{translation}</h2>
        <div className="flashcard-back__content">{content}</div>
        <div className="flashcard-back__dots" aria-hidden="true">
          {Array.from({ length: cardCount }, (_, position) => (
            <span
              key={position}
              className={position === cardIndex ? 'flashcard-back__dot flashcard-back__dot--current' : 'flashcard-back__dot'}
              data-current={position === cardIndex}
            />
          ))}
        </div>
        {onDone && (
          <button type="button" className="flashcard-back__done" onClick={onDone}>
            {doneLabel}
          </button>
        )}
      </div>
      {onNext ? (
        <IconButton icon="next" shape="plain" label={nextLabel} onClick={onNext} />
      ) : (
        <span className="flashcard-back__arrow-space" />
      )}
    </div>

    {notice}

    <div className="flashcard-back__history">
      <button type="button" className="flashcard-back__history-toggle" aria-expanded={isHistoryOpen} onClick={onToggleHistory}>
        {historyLabel}
        <Icon
          name="down"
          size={HISTORY_ICON_SIZE}
          strokeWidth={HISTORY_ICON_STROKE}
          className={isHistoryOpen ? 'flashcard-back__history-icon--open' : 'flashcard-back__history-icon'}
        />
      </button>
      {isHistoryOpen && <div className="flashcard-back__history-list">{history}</div>}
    </div>
  </div>
);

export default FlashcardBack;
