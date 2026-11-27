// Spotify sign-in and playlist: the API holds the secret and the refresh token; the browser reads the state,
// goes to the sign-in and saves the playlist link.
import { API_URL_KEY, createApiClient } from './api_client';
import { openInNewTab } from './page_location';

const GET_SPOTIFY_CONNECTION = '/api/GetSpotifyConnection';
const SPOTIFY_CONNECT = '/api/SpotifyConnect';
const UPDATE_SPOTIFY_PLAYLIST = '/api/UpdateSpotifyPlaylist';
const PLAYLIST_ADDRESS = 'https://open.spotify.com/playlist/';

export interface SpotifyConnection {
  isConnected: boolean;
  name: string | null;
  playlistId: string | null;
}

interface SpotifyPlaylistSaved {
  playlistId: string;
}

const client = createApiClient(API_URL_KEY);

export const getSpotifyConnection = (): Promise<SpotifyConnection> => client.get(GET_SPOTIFY_CONNECTION);

/** Opens the Spotify sign-in in a new tab; the API sends the browser back to /settings?spotify=connected|failed. */
export const connectSpotify = (): void => openInNewTab(client.url(SPOTIFY_CONNECT));

/** Saves the playlist the RAG engine reads. The API only checks the link's form. */
export const updateSpotifyPlaylist = async (playlistLink: string): Promise<string> =>
  (await client.post<SpotifyPlaylistSaved>(UPDATE_SPOTIFY_PLAYLIST, { playlistLink })).playlistId;

/** The playlist's page on Spotify. */
export const playlistAddress = (playlistId: string): string => `${PLAYLIST_ADDRESS}${playlistId}`;
