import { API_URL_KEY, createApiClient } from './api_client';

const GET_CARD_WORDS = '/api/GetCardWords';
const GET_WORDS_BY_ACTIVE = '/api/GetWordsByActive';
const GET_WORD_HISTORY = '/api/GetWordHistory';
const GET_WORDS_BY_FILTER = '/api/GetWordsByFilter';
const UPDATE_WORD_CONTENT = '/api/UpdateWordContent';
const UPDATE_WORD_KNOWN_STATUS = '/api/UpdateWordKnownStatus';
const UPDATE_IS_REINFORCEMENT = '/api/UpdateIsReinforcement';

export interface CardWord {
  id: string;
  name: string;
  translation: string;
  counter: number;
  isReinforcement: boolean;
  lastShownDate: string | null;
  content: string | null;
}

export interface WordHistoryItem {
  isKnown: boolean;
  date: string;
}

export interface FilteredWord {
  id: string;
  name: string;
  isReinforcement: boolean;
  isKnown: boolean;
  lastShownDate: string | null;
  shownCount: number;
  knownCount: number;
  isRotated: boolean;
  counter: number | null;
}

/** An undefined field means any value. */
export interface WordFilter {
  name?: string;
  isReinforcement?: boolean;
  isKnown?: boolean;
  isRotated?: boolean;
}

const client = createApiClient(API_URL_KEY);

const flagText = (value: boolean | undefined): string | undefined =>
  value === undefined ? undefined : String(value);

export const getCardWords = (wordIds: string): Promise<CardWord[]> => client.get(GET_CARD_WORDS, { wordIds });

export const getWordsByActive = (): Promise<CardWord[]> => client.get(GET_WORDS_BY_ACTIVE);

export const getWordHistory = (wordId: string): Promise<WordHistoryItem[]> =>
  client.get(GET_WORD_HISTORY, { wordId });

export const getWordsByFilter = (filter: WordFilter): Promise<FilteredWord[]> =>
  client.get(GET_WORDS_BY_FILTER, {
    name: filter.name,
    isReinforcement: flagText(filter.isReinforcement),
    isKnown: flagText(filter.isKnown),
    isRotated: flagText(filter.isRotated),
  });

export const updateWordContent = (id: string, content: string): Promise<void> =>
  client.post(UPDATE_WORD_CONTENT, { id, content });

export const updateWordKnownStatus = (wordId: string, isKnown: boolean): Promise<void> =>
  client.post(UPDATE_WORD_KNOWN_STATUS, { wordId, isKnown });

export const updateIsReinforcement = (wordId: string, isReinforcement: boolean): Promise<void> =>
  client.post(UPDATE_IS_REINFORCEMENT, { wordId, isReinforcement });
