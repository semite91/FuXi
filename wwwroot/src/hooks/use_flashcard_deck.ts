// The logic of the Flashcard carousel: loading the cards, the Word Content flow,
// the answers, the Reinforced Word flag, the Word History and the moves.
import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessageOf } from '../services/api_client';
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

/** GetWordContent is asked for this many Words at a time, one group after another. */
const CONTENT_GROUP_SIZE = 5;

const isWaiting = (card: Flashcard): boolean => card.contentStatus === 'loading';

/** The waiting Words in card order, one per Name: cards with the same Name share one result. */
const uniqueMeanings = (waiting: readonly Flashcard[]): WordMeaning[] => {
  const byName = new Map<string, WordMeaning>();
  waiting.forEach(({ word }) => {
    if (!byName.has(word.name)) {
      byName.set(word.name, { name: word.name, translation: word.translation });
    }
  });

  return [...byName.values()];
};

const toGroups = <T>(items: readonly T[], size: number): T[][] =>
  Array.from({ length: Math.ceil(items.length / size) }, (_, group) => items.slice(group * size, (group + 1) * size));

/** The generated contents by Name. A failed request gives none, so its Words show that content is not available. */
const askContent = async (group: readonly WordMeaning[]): Promise<Map<string, string>> => {
  try {
    const generated = await getWordContent(group);

    return new Map(generated.map((item) => [item.name, item.content]));
  } catch {
    return new Map();
  }
};

/** Sets each generated content on the waiting cards of the group with the same Name. A Word without one gets none. */
const mergeContent = (
  cards: Flashcard[],
  groupNames: ReadonlySet<string>,
  contentByName: ReadonlyMap<string, string>,
): Flashcard[] =>
  cards.map((card) => {
    if (!isWaiting(card) || !groupNames.has(card.word.name)) {
      return card;
    }

    const content = contentByName.get(card.word.name);

    return content === undefined || isEmptyContent(content)
      ? { ...card, contentStatus: 'unavailable' }
      : { ...card, content, contentStatus: 'ready' };
  });

/** The content stays on the card even when it cannot be stored. */
const storeContent = (
  waiting: readonly Flashcard[],
  groupNames: ReadonlySet<string>,
  contentByName: ReadonlyMap<string, string>,
) =>
  waiting
    .filter((card) => groupNames.has(card.word.name))
    .forEach((card) => {
      const content = contentByName.get(card.word.name);

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

    /** Groups are asked one after another, so the first cards fill first. A closed deck sends no more groups. */
    const loadContent = async (loaded: Flashcard[]) => {
      const waiting = loaded.filter(isWaiting);

      for (const group of toGroups(uniqueMeanings(waiting), CONTENT_GROUP_SIZE)) {
        const contentByName = await askContent(group);

        if (!isCurrent) {
          return;
        }

        const groupNames = new Set(group.map((meaning) => meaning.name));
        setCards((current) => mergeContent(current, groupNames, contentByName));
        storeContent(waiting, groupNames, contentByName);
      }
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

  const moveTo = (nextIndex: number) => {
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
