// The Spotify row of the Settings page and its playlist pop-up.
import {
  connectSpotify,
  getSpotifyConnection,
  updateSpotifyPlaylist,
  type SpotifyConnection,
} from '../services/spotify_service';
import { useLinkChoice } from './use_link_choice';
import { useSourceConnection } from './use_source_connection';

const NOT_CONNECTED: SpotifyConnection = { isConnected: false, name: null, playlistId: null };
// The API sends the browser back to /settings?spotify=connected|failed after the sign-in.
const RESULT_PARAMETER = 'spotify';

export const useSpotifyConnection = () => {
  const { connection, setConnection, isReturningFromSignIn, hasSignInFailed } = useSourceConnection({
    resultParameter: RESULT_PARAMETER,
    load: getSpotifyConnection,
    notConnected: NOT_CONNECTED,
  });
  const playlist = useLinkChoice({
    save: updateSpotifyPlaylist,
    onSaved: (playlistId) => setConnection((current) => (current === null ? current : { ...current, playlistId })),
  });

  // Not connected, the button signs in; connected, it opens the playlist pop-up.
  const press = () => (connection?.isConnected ? playlist.open() : connectSpotify());

  return {
    connection,
    isReturningFromSignIn,
    hasSignInFailed,
    press,
    connectAgain: connectSpotify,
    isChoosingPlaylist: playlist.isOpen,
    isSaving: playlist.isSaving,
    saveError: playlist.saveError,
    closePlaylist: playlist.close,
    savePlaylist: playlist.saveLink,
  };
};
