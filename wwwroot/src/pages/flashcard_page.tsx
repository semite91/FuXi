import { useSearchParams } from 'react-router';
import FlashcardBack from '../components/flashcard_back/flashcard_back';
import FlashcardCarousel from '../components/flashcard_carousel/flashcard_carousel';
import FlashcardFront from '../components/flashcard_front/flashcard_front';
import PageCard from '../components/page_card/page_card';
import Skeleton from '../components/skeleton/skeleton';
import StatusMessage from '../components/status_message/status_message';
import { WORD_IDS_QUERY } from '../constants/routes';
import { APP_TEXTS, FLASHCARD_TEXTS, HISTORY_TEXTS } from '../constants/texts';
import { useFlashcardDeck, type Flashcard } from '../hooks/use_flashcard_deck';
import { renderWordHistory } from './word_history_content';

const FRONT_SIDE = 'front';
const BACK_SIDE = 'back';

const renderContent = (card: Flashcard) => {
  if (card.contentStatus === 'loading') {
    return (
      <>
        <StatusMessage kind="hidden" text={FLASHCARD_TEXTS.loadingContent} />
        <Skeleton size="block" />
      </>
    );
  }

  return card.contentStatus === 'ready' ? (
    <p>{card.content}</p>
  ) : (
    <StatusMessage text={FLASHCARD_TEXTS.contentUnavailable} />
  );
};

interface FlashcardDeckProps {
  /** Null loads the Due Words. */
  wordIds: string | null;
}

const FlashcardDeck = ({ wordIds }: FlashcardDeckProps) => {
  const deck = useFlashcardDeck(wordIds);
  const { card } = deck;

  if (deck.status === 'loading') {
    return (
      <PageCard layout="centered">
        <StatusMessage text={APP_TEXTS.loading} />
      </PageCard>
    );
  }

  if (deck.status === 'error') {
    return (
      <PageCard layout="centered">
        <StatusMessage kind="error" text={deck.loadError} />
      </PageCard>
    );
  }

  if (deck.status === 'empty' || deck.status === 'done' || card === undefined) {
    return (
      <PageCard layout="centered">
        <StatusMessage
          kind="message"
          text={deck.status === 'done' ? FLASHCARD_TEXTS.done : FLASHCARD_TEXTS.noWords}
        />
      </PageCard>
    );
  }

  const notice = deck.actionError === '' ? undefined : <StatusMessage kind="error" text={deck.actionError} />;
  const side = card.isAnswered ? BACK_SIDE : FRONT_SIDE;

  return (
    <FlashcardCarousel slideKey={`${card.word.id}-${side}`}>
      <PageCard>
        {card.isAnswered ? (
          <FlashcardBack
            translation={card.word.translation}
            content={renderContent(card)}
            cardCount={deck.cardCount}
            cardIndex={deck.index}
            reinforcementLabel={FLASHCARD_TEXTS.reinforcement}
            previousLabel={FLASHCARD_TEXTS.previous}
            nextLabel={FLASHCARD_TEXTS.next}
            doneLabel={FLASHCARD_TEXTS.done}
            historyLabel={HISTORY_TEXTS.title}
            onReinforce={deck.reinforce}
            onPrevious={deck.index > 0 ? deck.goPrevious : undefined}
            onNext={deck.isLast ? undefined : deck.goNext}
            onDone={deck.isLast ? deck.finish : undefined}
            isHistoryOpen={deck.isHistoryOpen}
            onToggleHistory={deck.toggleHistory}
            history={renderWordHistory(deck.history)}
            notice={notice}
          />
        ) : (
          <FlashcardFront
            question={FLASHCARD_TEXTS.question}
            word={card.word.name}
            yesLabel={APP_TEXTS.yes}
            noLabel={APP_TEXTS.no}
            onAnswer={deck.answer}
            notice={notice}
          />
        )}
      </PageCard>
    </FlashcardCarousel>
  );
};

interface FlashcardPageProps {
  /** True for the notification route, which reads the Word ids from the address. */
  usesWordIds: boolean;
}

const DUE_WORDS_KEY = 'due';

/**
 * The Flashcard carousel. It is filled by a notification's Word ids or by the Due Words.
 * New Word ids start a new deck, so the position of the old one is not kept.
 */
const FlashcardPage = ({ usesWordIds }: FlashcardPageProps) => {
  const [searchParams] = useSearchParams();
  const queryValue = usesWordIds ? searchParams.get(WORD_IDS_QUERY) : null;
  const wordIds = queryValue === '' ? null : queryValue;

  return <FlashcardDeck key={wordIds ?? DUE_WORDS_KEY} wordIds={wordIds} />;
};

export default FlashcardPage;
