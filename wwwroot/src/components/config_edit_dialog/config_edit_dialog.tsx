import type { ReactNode } from 'react';
import Dialog from '../dialog/dialog';
import './config_edit_dialog.less';

const NUMERIC_INPUT_MODE = 'numeric';

interface ConfigEditDialogProps {
  title: string;
  inputType: 'text' | 'number' | 'date';
  value: string;
  saveLabel: string;
  closeLabel: string;
  onChange: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
  /** A message above the button, such as a rejected value. */
  notice?: ReactNode;
}

const ConfigEditDialog = ({
  title,
  inputType,
  value,
  saveLabel,
  closeLabel,
  onChange,
  onSave,
  onClose,
  notice,
}: ConfigEditDialogProps) => (
  <Dialog label={title} closeLabel={closeLabel} onClose={onClose}>
    <h2>{title}</h2>
    <input
      className="config-edit-dialog__input"
      type={inputType}
      inputMode={inputType === 'number' ? NUMERIC_INPUT_MODE : undefined}
      aria-label={title}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
    {notice}
    <div className="config-edit-dialog__actions">
      <button type="button" className="config-edit-dialog__save" onClick={onSave}>
        {saveLabel}
      </button>
    </div>
  </Dialog>
);

export default ConfigEditDialog;
