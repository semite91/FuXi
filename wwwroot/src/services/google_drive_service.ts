// Google Drive sign-in and folder: the API holds the secret and the refresh token; the browser reads the state,
// goes to the sign-in and saves the folder link.
import { API_URL_KEY, createApiClient } from './api_client';
import { openInNewTab } from './page_location';

const GET_GOOGLE_DRIVE_CONNECTION = '/api/GetGoogleDriveConnection';
const GOOGLE_DRIVE_CONNECT = '/api/GoogleDriveConnect';
const UPDATE_GOOGLE_DRIVE_FOLDER = '/api/UpdateGoogleDriveFolder';
const DRIVE_FOLDER_ADDRESS = 'https://drive.google.com/drive/folders/';

export interface GoogleDriveConnection {
  isConnected: boolean;
  email: string | null;
  folderId: string | null;
}

interface GoogleDriveFolderSaved {
  folderId: string;
}

const client = createApiClient(API_URL_KEY);

export const getGoogleDriveConnection = (): Promise<GoogleDriveConnection> => client.get(GET_GOOGLE_DRIVE_CONNECTION);

/** Opens the Google sign-in in a new tab; the API sends the browser back to /settings?drive=connected|failed. */
export const connectGoogleDrive = (): void => openInNewTab(client.url(GOOGLE_DRIVE_CONNECT));

/** Saves the folder the RAG engine reads. The API only checks the link's form. */
export const updateGoogleDriveFolder = async (folderLink: string): Promise<string> =>
  (await client.post<GoogleDriveFolderSaved>(UPDATE_GOOGLE_DRIVE_FOLDER, { folderLink })).folderId;

/** The folder's page in Drive. */
export const folderAddress = (folderId: string): string => `${DRIVE_FOLDER_ADDRESS}${folderId}`;
