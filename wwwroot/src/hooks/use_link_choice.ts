// The link pop-up of a source row (a Google Drive folder, a Spotify playlist): open, save once, show the failure.
import { useState } from 'react';
import { ApiError } from '../services/api_client';

const BAD_REQUEST_STATUS = 400;
const UNPROCESSABLE_STATUS = 422;

/** Why a save failed: the API refused the link's form, the source cannot read what the link names, or anything else. */
export type LinkSaveError = 'notALink' | 'notReadable' | 'failed';

interface LinkChoiceOptions {
  /** Saves the link and returns the ID the API took from it. */
  save: (link: string) => Promise<string>;
  /** Called with the saved ID after a successful save, before the pop-up closes. */
  onSaved: (id: string) => void;
}

const saveErrorOf = (error: unknown): LinkSaveError => {
  if (error instanceof ApiError && error.status === BAD_REQUEST_STATUS) {
    return 'notALink';
  }

  return error instanceof ApiError && error.status === UNPROCESSABLE_STATUS ? 'notReadable' : 'failed';
};

export const useLinkChoice = ({ save, onSaved }: LinkChoiceOptions) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<LinkSaveError | null>(null);

  const open = () => {
    setSaveError(null);
    setIsOpen(true);
  };

  const close = () => setIsOpen(false);

  const saveLink = async (link: string) => {
    if (isSaving) {
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    try {
      onSaved(await save(link));
      setIsOpen(false);
    } catch (error) {
      setSaveError(saveErrorOf(error));
    } finally {
      setIsSaving(false);
    }
  };

  return { isOpen, isSaving, saveError, open, close, saveLink };
};
