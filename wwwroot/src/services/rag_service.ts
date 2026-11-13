import { RAG_URL_KEY, createApiClient } from './api_client';

const GET_WORD_CONTENT = '/GetWordContent';
const INIT_RAG = '/Init_RAG';
const UPDATE_COLLECTIONS = '/Update_Collections';

/** A Word and its translation, which the engine uses as the meaning. */
export interface WordMeaning {
  name: string;
  translation: string;
}

/** content is the Word Content JSON as a string, for the name and translation as they were sent. A Word without content is left out. */
export interface WordContent extends WordMeaning {
  content: string;
}

/** The app does not act on the status yet. */
export interface RagState {
  status: 'ready' | 'building' | 'empty';
}

const client = createApiClient(RAG_URL_KEY);

export const getWordContent = (words: readonly WordMeaning[]): Promise<WordContent[]> =>
  client.post(GET_WORD_CONTENT, { words });

export const initRag = (): Promise<RagState> => client.post(INIT_RAG);

/** Starts the engine without waiting. A failure is not shown; the cards say their content is not available. */
export const startRag = (): void => {
  initRag().catch(() => undefined);
};

export const updateCollections = (): Promise<void> => client.post(UPDATE_COLLECTIONS);
