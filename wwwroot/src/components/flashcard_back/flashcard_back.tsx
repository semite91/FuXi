import { useRef, type ReactNode, type TouchEvent } from 'react';
import DisclosureToggle from '../disclosure_toggle/disclosure_toggle';
import IconButton from '../icon_button/icon_button';
import { Icon } from '../../image/icons';
import Tooltip from '../tooltip/tooltip';
import './flashcard_back.less';

/** A horizontal swipe shorter than this many pixels is a tap or a scroll, not a change of word. */
const SWIPE_DISTANCE = 60;
const EDGE_ICON_SIZE = 34;

interface FlashcardBackProps {
  translation: string;
  /** The Word's name, shown small under the translation. */
  name: string;
  /** The Word Content, its loading state or its missing state. */
  content: ReactNode;
  reinforcementLabel: string;
  previousLabel: string;
  nextLabel: string;
  historyLabel: string;
  onReinforce: () => void;
  /** Without a handler the left edge is not shown. */
  onPrevious?: () => void;
  onNext: () => void;
  isHistoryOpen: boolean;
  onToggleHistory: () => void;
  /** The Word History list or its state. Shown while the toggle is open. */
  history: ReactNode;
  notice?: ReactNode;
}

/**
 * The back of a Flashcard. The words change by a swipe, or by the two card edges, which show an arrow
 * over a faint tint only while the pointer is on them. The History sits right under the content.
 */
const FlashcardBack = ({
  translation,
  name,
  content,
  reinforcementLabel,
  previousLabel,
  nextLabel,
  historyLabel,
  onReinforce,
  onPrevious,
  onNext,
  isHistoryOpen,
  onToggleHistory,
  history,
  notice,
}: FlashcardBackProps) => {
  const touchStartX = useRef<number | null>(null);

  const startSwipe = (event: TouchEvent) => {
    touchStartX.current = event.touches[0]?.clientX ?? null;
  };
  const endSwipe = (event: TouchEvent) => {
    const startX = touchStartX.current;
    touchStartX.current = null;
    const endX = event.changedTouches[0]?.clientX;
    if (startX === null || endX === undefined) {
      return;
    }
    const distance = endX - startX;
    if (distance >= SWIPE_DISTANCE) {
      onPrevious?.();
    } else if (distance <= -SWIPE_DISTANCE) {
      onNext();
    }
  };

  return (
    <div className="flashcard-back" onTouchStart={startSwipe} onTouchEnd={endSwipe}>
      <div className="flashcard-back__reinforcement">
        <Tooltip text={reinforcementLabel}>
          <IconButton icon="close" shape="small" label={reinforcementLabel} onClick={onReinforce} />
        </Tooltip>
      </div>

      {onPrevious && (
        <button
          type="button"
          className="flashcard-back__edge flashcard-back__edge--previous"
          aria-label={previousLabel}
          onClick={onPrevious}
        >
          <Icon name="previous" size={EDGE_ICON_SIZE} />
        </button>
      )}
      <button
        type="button"
        className="flashcard-back__edge flashcard-back__edge--next"
        aria-label={nextLabel}
        onClick={onNext}
      >
        <Icon name="next" size={EDGE_ICON_SIZE} />
      </button>

      <div className="flashcard-back__body" aria-live="polite">
        <h2 className="flashcard-back__translation">{translation}</h2>
        <p className="flashcard-back__name">{name}</p>
        <div className="flashcard-back__content">{content}</div>
      </div>

      {notice}

      <div className="flashcard-back__history">
        <DisclosureToggle label={historyLabel} isOpen={isHistoryOpen} onToggle={onToggleHistory}>
          {history}
        </DisclosureToggle>
      </div>
    </div>
  );
};

export default FlashcardBack;
