// The steps of "Update embeddings" on the Settings page. The progress and the result are toasts, which stay on screen
// when the Learner leaves the page.
import { useState } from 'react';
import { SETTINGS_TEXTS } from '../constants/texts';
import { updateCollections } from '../services/rag_service';
import { clearWordContent } from '../services/words_service';
import { changeToast, showToast } from '../services/toast_store';

export type EmbeddingsStep = 'idle' | 'confirm';

// One update at a time for the whole app, even when the Settings page is opened again while it runs.
let isUpdating = false;

export const useEmbeddingsUpdate = () => {
  const [step, setStep] = useState<EmbeddingsStep>('idle');

  const update = async () => {
    setStep('idle');

    if (isUpdating) {
      return;
    }

    isUpdating = true;
    const toastId = showToast('progress', SETTINGS_TEXTS.updating);

    try {
      await updateCollections();
      // The stored Content came from the old embeddings; every card makes it again when it is shown.
      await clearWordContent();
      changeToast(toastId, 'success', SETTINGS_TEXTS.updated);
    } catch {
      changeToast(toastId, 'error', SETTINGS_TEXTS.failed);
    } finally {
      isUpdating = false;
    }
  };

  return {
    step,
    ask: () => setStep('confirm'),
    close: () => setStep('idle'),
    update,
  };
};
