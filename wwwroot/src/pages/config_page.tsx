import ConfigEditDialog from '../components/config_edit_dialog/config_edit_dialog';
import ConfigTable from '../components/config_table/config_table';
import PageCard from '../components/page_card/page_card';
import StatusMessage from '../components/status_message/status_message';
import { APP_TEXTS, CONFIG_TEXTS } from '../constants/texts';
import { useConfigs } from '../hooks/use_configs';
import type { InputType } from '../services/config_service';

const NUMBER_TYPE: InputType = 'Number';
const DATE_TYPE: InputType = 'Date';

/** Every InputType without its own input is edited as text. */
const inputTypeOf = (inputType: InputType) => {
  if (inputType === NUMBER_TYPE) {
    return 'number';
  }

  return inputType === DATE_TYPE ? 'date' : 'text';
};

const ConfigPage = () => {
  const configs = useConfigs();
  const { editing } = configs;

  return (
    <PageCard title={CONFIG_TEXTS.title}>

      {configs.status === 'loading' && <StatusMessage text={APP_TEXTS.loading} />}
      {configs.status === 'error' && <StatusMessage kind="error" text={configs.loadError} />}
      {configs.status === 'loaded' && (
        <ConfigTable
          label={CONFIG_TEXTS.title}
          nameLabel={CONFIG_TEXTS.name}
          valueLabel={CONFIG_TEXTS.value}
          editColumnLabel={CONFIG_TEXTS.edit}
          rows={configs.configs.map((config) => ({
            id: config.configId,
            name: config.name,
            value: config.value,
            editLabel: `${CONFIG_TEXTS.edit} ${config.name}`,
          }))}
          onEdit={configs.edit}
        />
      )}

      {editing && (
        <ConfigEditDialog
          title={editing.config.name}
          inputType={inputTypeOf(editing.config.inputType)}
          value={editing.draft}
          saveLabel={CONFIG_TEXTS.save}
          closeLabel={APP_TEXTS.closeDialog}
          onChange={configs.changeDraft}
          onSave={() => void configs.save()}
          onClose={configs.cancel}
          notice={editing.error === '' ? undefined : <StatusMessage kind="error" text={editing.error} />}
        />
      )}
    </PageCard>
  );
};

export default ConfigPage;
