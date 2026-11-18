// The Google Drive row of the Settings page and its folder pop-up.
import {
  connectGoogleDrive,
  getGoogleDriveConnection,
  updateGoogleDriveFolder,
  type GoogleDriveConnection,
} from '../services/google_drive_service';
import { useLinkChoice } from './use_link_choice';
import { useSourceConnection } from './use_source_connection';

const NOT_CONNECTED: GoogleDriveConnection = { isConnected: false, email: null, folderId: null };
// The API sends the browser back to /settings?drive=connected|failed after the sign-in.
const RESULT_PARAMETER = 'drive';

export const useGoogleDriveConnection = () => {
  const { connection, setConnection, isReturningFromSignIn, hasSignInFailed } = useSourceConnection({
    resultParameter: RESULT_PARAMETER,
    load: getGoogleDriveConnection,
    notConnected: NOT_CONNECTED,
  });
  const folder = useLinkChoice({
    save: updateGoogleDriveFolder,
    onSaved: (folderId) => setConnection((current) => (current === null ? current : { ...current, folderId })),
  });

  return {
    connection,
    isReturningFromSignIn,
    hasSignInFailed,
    connect: connectGoogleDrive,
    isChoosingFolder: folder.isOpen,
    isSaving: folder.isSaving,
    saveError: folder.saveError,
    chooseFolder: folder.open,
    closeFolder: folder.close,
    saveFolder: folder.saveLink,
  };
};
