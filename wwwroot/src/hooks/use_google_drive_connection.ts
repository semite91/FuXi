// The Google Drive row of the Settings page and its folder pop-up.
import { useState } from 'react';
import { ApiError } from '../services/api_client';
import {
  connectGoogleDrive,
  getGoogleDriveConnection,
  updateGoogleDriveFolder,
  type GoogleDriveConnection,
} from '../services/google_drive_service';
import { useSourceConnection } from './use_source_connection';

const NOT_CONNECTED: GoogleDriveConnection = { isConnected: false, email: null, folderId: null };
// The API sends the browser back to /settings?drive=connected|failed after the sign-in.
const RESULT_PARAMETER = 'drive';
const BAD_REQUEST_STATUS = 400;

/** Why a save failed: the API refused the link's form, or anything else. */
export type FolderSaveError = 'notAFolderLink' | 'failed';

export const useGoogleDriveConnection = () => {
  const { connection, setConnection, isReturningFromSignIn, hasSignInFailed } = useSourceConnection({
    resultParameter: RESULT_PARAMETER,
    load: getGoogleDriveConnection,
    notConnected: NOT_CONNECTED,
  });
  const [isChoosingFolder, setIsChoosingFolder] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<FolderSaveError | null>(null);

  const chooseFolder = () => {
    setSaveError(null);
    setIsChoosingFolder(true);
  };

  const closeFolder = () => setIsChoosingFolder(false);

  const saveFolder = async (folderLink: string) => {
    if (isSaving) {
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    try {
      const folderId = await updateGoogleDriveFolder(folderLink);
      setConnection((current) => (current === null ? current : { ...current, folderId }));
      setIsChoosingFolder(false);
    } catch (error) {
      setSaveError(error instanceof ApiError && error.status === BAD_REQUEST_STATUS ? 'notAFolderLink' : 'failed');
    } finally {
      setIsSaving(false);
    }
  };

  return {
    connection,
    isReturningFromSignIn,
    hasSignInFailed,
    connect: connectGoogleDrive,
    isChoosingFolder,
    isSaving,
    saveError,
    chooseFolder,
    closeFolder,
    saveFolder,
  };
};
