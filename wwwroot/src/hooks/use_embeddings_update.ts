// The steps of "Update embeddings" on the Settings page.
import { useRef, useState } from 'react';
import { updateCollections } from '../services/rag_service';

export type EmbeddingsStep = 'idle' | 'confirm' | 'updated' | 'failed';

export const useEmbeddingsUpdate = () => {
  const [step, setStep] = useState<EmbeddingsStep>('idle');
  const isUpdating = useRef(false);

  const update = async () => {
    if (isUpdating.current) {
      return;
    }

    isUpdating.current = true;

    try {
      await updateCollections();
      setStep('updated');
    } catch {
      setStep('failed');
    } finally {
      isUpdating.current = false;
    }
  };

  return {
    step,
    ask: () => setStep('confirm'),
    close: () => setStep('idle'),
    update,
  };
};
