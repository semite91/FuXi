// Notion sign-in: the API holds the secret and the token; the browser only reads the state and goes to the sign-in.
import { API_URL_KEY, createApiClient } from './api_client';
import { openInNewTab } from './page_location';

const GET_NOTION_CONNECTION = '/api/GetNotionConnection';
const NOTION_CONNECT = '/api/NotionConnect';

export interface NotionConnection {
  isConnected: boolean;
  workspaceName: string | null;
}

const client = createApiClient(API_URL_KEY);

export const getNotionConnection = (): Promise<NotionConnection> => client.get(GET_NOTION_CONNECTION);

/** Opens the Notion sign-in in a new tab; the API sends the browser back to /settings?notion=connected|failed. */
export const connectNotion = (): void => openInNewTab(client.url(NOTION_CONNECT));
