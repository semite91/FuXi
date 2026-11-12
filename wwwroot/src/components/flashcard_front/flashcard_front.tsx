import type { ReactNode } from 'react';
import { Icon } from '../../image/icons';
import './flashcard_front.less';

const ANSWER_ICON_SIZE = 20;
const ANSWER_ICON_STROKE = 2.5;

interface FlashcardFrontProps {
  question: string;
  word: string;
  yesLabel: string;
  noLabel: string;
  onAnswer: (isKnown: boolean) => void;
  /** A message under the buttons, such as a failed answer. */
  notice?: ReactNode;
}

const FlashcardFront = ({ question, word, yesLabel, noLabel, onAnswer, notice }: FlashcardFrontProps) => (
  <div className="flashcard-front">
    <p className="flashcard-front__question">{question}</p>
    <div className="flashcard-front__word">
      <h1>{word}</h1>
    </div>
    <div className="flashcard-front__answers">
      <button type="button" className="flashcard-front__answer flashcard-front__answer--no" onClick={() => onAnswer(false)}>
        <Icon name="close" size={ANSWER_ICON_SIZE} strokeWidth={ANSWER_ICON_STROKE} />
        {noLabel}
      </button>
      <button type="button" className="flashcard-front__answer flashcard-front__answer--yes" onClick={() => onAnswer(true)}>
        <Icon name="check" size={ANSWER_ICON_SIZE} strokeWidth={ANSWER_ICON_STROKE} />
        {yesLabel}
      </button>
    </div>
    {notice}
  </div>
);

export default FlashcardFront;
