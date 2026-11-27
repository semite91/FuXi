// The logic of the Flashcard carousel: loading the cards, the Word Content flow,
// the answers, the Reinforced Word flag, the Word History and the moves.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, errorMessageOf } from '../services/api_client';
import { getWordContent, type WordMeaning } from '../services/rag_service';
import {
  getCardWords,
  getWordHistory,
  getWordsByActive,
  updateIsReinforcement,
  updateWordContent,
  updateWordKnownStatus,
  type CardWord,
  type WordHistoryItem,
} from '../services/words_service';

export type DeckStatus = 'loading' | 'ready' | 'empty' | 'error' | 'done';
export type ContentStatus = 'ready' | 'loading' | 'unavailable';
export type HistoryStatus = 'loading' | 'loaded' | 'error';

export interface Flashcard {
  word: CardWord;
  isAnswered: boolean;
  content: string | null;
  contentStatus: ContentStatus;
}

export interface WordHistory {
  status: HistoryStatus;
  rows: WordHistoryItem[];
}

const isEmptyContent = (content: string | null): boolean => content === null || content.trim() === '';

const toFlashcard = (word: CardWord): Flashcard => ({
  word,
  isAnswered: false,
  content: isEmptyContent(word.content) ? null : word.content,
  contentStatus: isEmptyContent(word.content) ? 'loading' : 'ready',
});

/** GetWordContent is asked for this many Words at a time. */
const CONTENT_GROUP_SIZE = 5;
/** Groups in flight together, so the cards ahead of the Learner fill before they are reached. */
const CONTENT_PARALLEL_GROUPS = 3;

const isWaiting = (card: Flashcard): boolean => card.contentStatus === 'loading';

/** Cards with the same name and translation share one content; a homonym with another translation gets its own. */
const meaningKey = ({ name, translation }: WordMeaning): string => JSON.stringify([name, translation]);

/** The waiting Words in card order, one per name and translation. */
const uniqueMeanings = (waiting: readonly Flashcard[]): WordMeaning[] => {
  const byMeaning = new Map<string, WordMeaning>();
  waiting.forEach(({ word }) => {
    const key = meaningKey(word);

    if (!byMeaning.has(key)) {
      byMeaning.set(key, { name: word.name, translation: word.translation });
    }
  });

  return [...byMeaning.values()];
};

const toGroups = <T>(items: readonly T[], size: number): T[][] =>
  Array.from({ length: Math.ceil(items.length / size) }, (_, group) => items.slice(group * size, (group + 1) * size));

/** The engine answers 503 while it builds or updates its collections; the Words keep waiting, they are not failed. */
const ENGINE_BUSY_STATUS = 503;
/** The wait before a group is asked again while the engine is busy. */
export const ENGINE_BUSY_RETRY_MILLISECONDS = 10_000;

const wait = (milliseconds: number) => new Promise<void>((done) => setTimeout(done, milliseconds));

/**
 * The generated contents by meaning key. While the engine is busy the group is asked again, until the deck closes.
 * Any other failure gives none, so its Words show that content is not available.
 */
const askContent = async (group: readonly WordMeaning[], isCurrent: () => boolean): Promise<Map<string, string>> => {
  while (isCurrent()) {
    try {
      const generated = await getWordContent(group);

      return new Map(generated.map((item) => [meaningKey(item), item.content]));
    } catch (error) {
      if (!(error instanceof ApiError && error.status === ENGINE_BUSY_STATUS)) {
        return new Map();
      }

      await wait(ENGINE_BUSY_RETRY_MILLISECONDS);
    }
  }

  return new Map();
};

/** Sets each generated content on the waiting cards of the group with the same name and translation. A Word without one gets none. */
const mergeContent = (
  cards: Flashcard[],
  groupKeys: ReadonlySet<string>,
  contentByMeaning: ReadonlyMap<string, string>,
): Flashcard[] =>
  cards.map((card) => {
    const key = meaningKey(card.word);

    if (!isWaiting(card) || !groupKeys.has(key)) {
      return card;
    }

    const content = contentByMeaning.get(key);

    return content === undefined || isEmptyContent(content)
      ? { ...card, contentStatus: 'unavailable' }
      : { ...card, content, contentStatus: 'ready' };
  });

/** The content stays on the card even when it cannot be stored. */
const storeContent = (
  waiting: readonly Flashcard[],
  groupKeys: ReadonlySet<string>,
  contentByMeaning: ReadonlyMap<string, string>,
) =>
  waiting
    .filter((card) => groupKeys.has(meaningKey(card.word)))
    .forEach((card) => {
      const content = contentByMeaning.get(meaningKey(card.word));

      if (content !== undefined && !isEmptyContent(content)) {
        updateWordContent(card.word.id, content).catch(() => undefined);
      }
    });

/** wordIds comes from a notification. Without it the Due Words are loaded. */
export const useFlashcardDeck = (wordIds: string | null) => {
  const [status, setStatus] = useState<DeckStatus>('loading');
  const [loadError, setLoadError] = useState('');
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [index, setIndex] = useState(0);
  const [actionError, setActionError] = useState('');
  const [histories, setHistories] = useState<Record<string, WordHistory>>({});
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const isBusy = useRef(false);

  useEffect(() => {
    let isCurrent = true;

    /** Groups are taken in card order by a few workers at once, so the first cards fill first. A closed deck sends no more groups. */
    const loadContent = async (loaded: Flashcard[]) => {
      const waiting = loaded.filter(isWaiting);
      const groups = toGroups(uniqueMeanings(waiting), CONTENT_GROUP_SIZE);
      let nextGroup = 0;

      const work = async () => {
        while (isCurrent && nextGroup < groups.length) {
          const group = groups[nextGroup];
          nextGroup += 1;
          const contentByMeaning = await askContent(group, () => isCurrent);

          if (!isCurrent) {
            return;
          }

          const groupKeys = new Set(group.map(meaningKey));
          setCards((current) => mergeContent(current, groupKeys, contentByMeaning));
          storeContent(waiting, groupKeys, contentByMeaning);
        }
      };

      await Promise.all(Array.from({ length: CONTENT_PARALLEL_GROUPS }, work));
    };

    const load = async () => {
      try {
        const words = await (wordIds === null ? getWordsByActive() : getCardWords(wordIds));

        if (!isCurrent) {
          return;
        }

        const loaded = words.map(toFlashcard);
        setCards(loaded);
        setStatus(loaded.length === 0 ? 'empty' : 'ready');
        void loadContent(loaded);
      } catch (error) {
        if (isCurrent) {
          setLoadError(errorMessageOf(error));
          setStatus('error');
        }
      }
    };

    void load();

    return () => {
      isCurrent = false;
    };
  }, [wordIds]);

  const card = cards[index] as Flashcard | undefined;
  const isLast = index === cards.length - 1;

  /** Runs one API action at a time and shows its failure on the card. */
  const runAction = useCallback(async (action: () => Promise<void>, onSuccess: () => void) => {
    if (isBusy.current) {
      return;
    }

    isBusy.current = true;
    setActionError('');

    try {
      await action();
      onSuccess();
    } catch (error) {
      setActionError(errorMessageOf(error));
    } finally {
      isBusy.current = false;
    }
  }, []);

  /** A card reached by a move always opens on its front side, even when it was answered before. */
  const moveTo = (nextIndex: number) => {
    setCards((current) => current.map((item, position) => (position === nextIndex ? { ...item, isAnswered: false } : item)));
    setIndex(nextIndex);
    setIsHistoryOpen(false);
    setActionError('');
  };

  const answer = (isKnown: boolean) => {
    if (card === undefined) {
      return;
    }

    const wordId = card.word.id;
    void runAction(
      () => updateWordKnownStatus(wordId, isKnown),
      () => setCards((current) => current.map((item) => (item.word.id === wordId ? { ...item, isAnswered: true } : item))),
    );
  };

  const reinforce = () => {
    if (card === undefined) {
      return;
    }

    void runAction(
      () => updateIsReinforcement(card.word.id, true),
      () => (isLast ? setStatus('done') : moveTo(index + 1)),
    );
  };

  const loadHistory = async (wordId: string) => {
    setHistories((current) => ({ ...current, [wordId]: { status: 'loading', rows: [] } }));

    try {
      const rows = await getWordHistory(wordId);
      setHistories((current) => ({ ...current, [wordId]: { status: 'loaded', rows } }));
    } catch {
      setHistories((current) => ({ ...current, [wordId]: { status: 'error', rows: [] } }));
    }
  };

  const toggleHistory = () => {
    if (card === undefined) {
      return;
    }

    const history = histories[card.word.id] as WordHistory | undefined;

    if (!isHistoryOpen && (history === undefined || history.status === 'error')) {
      void loadHistory(card.word.id);
    }

    setIsHistoryOpen(!isHistoryOpen);
  };

  /** A picture that cannot be loaded leaves the card without content. */
  const markContentUnavailable = (wordId: string) =>
    setCards((current) =>
      current.map((item) => (item.word.id === wordId ? { ...item, contentStatus: 'unavailable' } : item)),
    );

  return {
    status,
    loadError,
    card,
    cardCount: cards.length,
    index,
    isLast,
    actionError,
    isHistoryOpen,
    history: card === undefined ? undefined : (histories[card.word.id] as WordHistory | undefined),
    answer,
    reinforce,
    toggleHistory,
    markContentUnavailable,
    goNext: () => moveTo(index + 1),
    goPrevious: () => moveTo(index - 1),
    finish: () => setStatus('done'),
  };
};
