import { RAG_URL_KEY, createApiClient } from './api_client';

// Assumed contract until the RAG phase builds the engine.
const GET_WORD_CONTENT = '/GetWordContent';
const UPDATE_COLLECTIONS = '/Update_Collections';
const NAME_SEPARATOR = ',';

export interface WordContent {
  name: string;
  content: string;
}

const client = createApiClient(RAG_URL_KEY);

export const getWordContent = (names: readonly string[]): Promise<WordContent[]> =>
  client.get(GET_WORD_CONTENT, { words: names.join(NAME_SEPARATOR) });

export const updateCollections = (): Promise<void> => client.post(UPDATE_COLLECTIONS);
