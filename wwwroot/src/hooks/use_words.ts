// The logic of the Words page: the applied filter, the rows, their order and the Word History dialog.
import { useMemo, useRef, useState } from 'react';
import { errorMessageOf } from '../services/api_client';
import {
  getWordHistory,
  getWordsByFilter,
  type FilteredWord,
  type WordFilter,
  type WordHistoryItem,
} from '../services/words_service';

export type Choice = '' | 'yes' | 'no';
export type WordsStatus = 'idle' | 'loading' | 'loaded' | 'error';
export type SortKey = 'name' | 'isKnown' | 'isReinforcement' | 'knownCount' | 'shownCount' | 'counter' | 'lastShownDate';
export type SortDirection = 'ascending' | 'descending';

export interface FilterDraft {
  name: string;
  isReinforcement: Choice;
  isKnown: Choice;
  isRotated: Choice;
}

export interface WordSort {
  key: SortKey;
  direction: SortDirection;
}

export interface OpenedHistory {
  wordName: string;
  status: 'loading' | 'loaded' | 'error';
  rows: WordHistoryItem[];
}

export const EMPTY_FILTER: FilterDraft = { name: '', isReinforcement: '', isKnown: '', isRotated: '' };

const YES: Choice = 'yes';
const BEFORE = -1;
const AFTER = 1;

const toFlag = (choice: Choice): boolean | undefined => (choice === '' ? undefined : choice === YES);

const toFilter = (draft: FilterDraft): WordFilter => ({
  name: draft.name.trim() === '' ? undefined : draft.name.trim(),
  isReinforcement: toFlag(draft.isReinforcement),
  isKnown: toFlag(draft.isKnown),
  isRotated: toFlag(draft.isRotated),
});

const isEmptyFilter = (filter: WordFilter): boolean => Object.values(filter).every((value) => value === undefined);

/** Missing values come first when ascending. Texts ignore case. */
const compare = (first: FilteredWord, second: FilteredWord, key: SortKey): number => {
  const left = first[key];
  const right = second[key];

  if (left === right) {
    return 0;
  }

  if (left === null) {
    return BEFORE;
  }

  if (right === null) {
    return AFTER;
  }

  if (typeof left === 'string' && typeof right === 'string') {
    return left.localeCompare(right, undefined, { sensitivity: 'base' });
  }

  return left < right ? BEFORE : AFTER;
};

export const useWords = () => {
  const [applied, setApplied] = useState<FilterDraft>(EMPTY_FILTER);
  const [status, setStatus] = useState<WordsStatus>('idle');
  const [error, setError] = useState('');
  const [words, setWords] = useState<FilteredWord[]>([]);
  const [sort, setSort] = useState<WordSort | null>(null);
  const [history, setHistory] = useState<OpenedHistory | null>(null);
  // Only the answer of the latest request may change the page.
  const latestFilter = useRef(0);
  const latestHistory = useRef(0);

  const sortedWords = useMemo(() => {
    if (sort === null) {
      return words;
    }

    const direction = sort.direction === 'ascending' ? AFTER : BEFORE;

    return [...words].sort((first, second) => compare(first, second, sort.key) * direction);
  }, [words, sort]);

  const apply = async (draft: FilterDraft) => {
    const request = ++latestFilter.current;
    const filter = toFilter(draft);
    setApplied({ ...draft, name: draft.name.trim() });
    setWords([]);

    // The API answers an empty filter with an empty list, so the call is skipped.
    if (isEmptyFilter(filter)) {
      setStatus('idle');
      return;
    }

    setStatus('loading');

    try {
      const found = await getWordsByFilter(filter);

      if (request === latestFilter.current) {
        setWords(found);
        setStatus('loaded');
      }
    } catch (caught) {
      if (request === latestFilter.current) {
        setError(errorMessageOf(caught));
        setStatus('error');
      }
    }
  };

  const sortBy = (key: SortKey) =>
    setSort((current) => ({
      key,
      direction: current?.key === key && current.direction === 'ascending' ? 'descending' : 'ascending',
    }));

  const openHistory = async (word: FilteredWord) => {
    const request = ++latestHistory.current;
    setHistory({ wordName: word.name, status: 'loading', rows: [] });

    try {
      const rows = await getWordHistory(word.id);

      if (request === latestHistory.current) {
        setHistory((current) => current && { ...current, status: 'loaded', rows });
      }
    } catch {
      if (request === latestHistory.current) {
        setHistory((current) => current && { ...current, status: 'error' });
      }
    }
  };

  return {
    applied,
    status,
    error,
    words: sortedWords,
    sort,
    history,
    apply,
    sortBy,
    openHistory,
    closeHistory: () => {
      latestHistory.current += 1;
      setHistory(null);
    },
  };
};
