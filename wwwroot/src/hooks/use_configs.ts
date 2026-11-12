// The logic of the Configs page: the rows and the row that is being edited.
import { useEffect, useRef, useState } from 'react';
import { errorMessageOf } from '../services/api_client';
import { getConfigs, saveConfig, type ConfigItem } from '../services/config_service';

export type ConfigsStatus = 'loading' | 'loaded' | 'error';

interface Editing {
  config: ConfigItem;
  draft: string;
  error: string;
}

export const useConfigs = () => {
  const [status, setStatus] = useState<ConfigsStatus>('loading');
  const [loadError, setLoadError] = useState('');
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [editing, setEditing] = useState<Editing | null>(null);
  const isSaving = useRef(false);

  useEffect(() => {
    let isCurrent = true;

    getConfigs()
      .then((loaded) => {
        if (isCurrent) {
          setConfigs(loaded);
          setStatus('loaded');
        }
      })
      .catch((error: unknown) => {
        if (isCurrent) {
          setLoadError(errorMessageOf(error));
          setStatus('error');
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const edit = (configId: string) => {
    const config = configs.find((item) => item.configId === configId);

    if (config !== undefined) {
      setEditing({ config, draft: config.value, error: '' });
    }
  };

  const save = async () => {
    if (editing === null || editing.draft.trim() === '' || isSaving.current) {
      return;
    }

    const { config, draft } = editing;
    isSaving.current = true;

    try {
      await saveConfig(config, draft);
      setConfigs((current) => current.map((item) => (item.configId === config.configId ? { ...item, value: draft } : item)));
      setEditing(null);
    } catch (error) {
      setEditing((current) => current && { ...current, error: errorMessageOf(error) });
    } finally {
      isSaving.current = false;
    }
  };

  return {
    status,
    loadError,
    configs,
    editing,
    edit,
    changeDraft: (draft: string) => setEditing((current) => current && { ...current, draft }),
    cancel: () => setEditing(null),
    save,
  };
};
