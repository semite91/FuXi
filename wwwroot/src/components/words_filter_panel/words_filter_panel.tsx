import { useId, useState } from 'react';
import Dialog from '../dialog/dialog';
import IconButton from '../icon_button/icon_button';
import './words_filter_panel.less';

export interface FilterChoice {
  value: string;
  label: string;
}

export interface FilterField<Name extends string> {
  name: Name;
  label: string;
  /** Without choices the field is a text input. */
  choices?: readonly FilterChoice[];
}

interface WordsFilterPanelProps<Name extends string> {
  title: string;
  closeLabel: string;
  clearLabel: string;
  applyLabel: string;
  fields: readonly FilterField<Name>[];
  /** The applied values, which fill the fields when the panel opens. */
  values: Readonly<Record<Name, string>>;
  emptyValues: Readonly<Record<Name, string>>;
  onApply: (values: Record<Name, string>) => void;
  onClose: () => void;
}

/** The fields keep a draft. Nothing is applied until Apply is clicked. */
const WordsFilterPanel = <Name extends string>({
  title,
  closeLabel,
  clearLabel,
  applyLabel,
  fields,
  values,
  emptyValues,
  onApply,
  onClose,
}: WordsFilterPanelProps<Name>) => {
  const idPrefix = useId();
  const [draft, setDraft] = useState<Record<Name, string>>({ ...values });
  const change = (name: Name, value: string) => setDraft((current) => ({ ...current, [name]: value }));

  return (
    <Dialog variant="panel" label={title} closeLabel={closeLabel} onClose={onClose}>
      <div className="words-filter-panel__head">
        <h2>{title}</h2>
        <IconButton icon="close" shape="small" label={closeLabel} onClick={onClose} />
      </div>
      {fields.map((field) => (
        <div key={field.name} className="words-filter-panel__field">
          <label htmlFor={idPrefix + field.name}>{field.label}</label>
          {field.choices ? (
            <select id={idPrefix + field.name} value={draft[field.name]} onChange={(event) => change(field.name, event.target.value)}>
              {field.choices.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={idPrefix + field.name}
              type="text"
              value={draft[field.name]}
              onChange={(event) => change(field.name, event.target.value)}
            />
          )}
        </div>
      ))}
      <div className="words-filter-panel__actions">
        <button type="button" className="words-filter-panel__clear" onClick={() => setDraft({ ...emptyValues })}>
          {clearLabel}
        </button>
        <button type="button" className="words-filter-panel__apply" onClick={() => onApply(draft)}>
          {applyLabel}
        </button>
      </div>
    </Dialog>
  );
};

export default WordsFilterPanel;
