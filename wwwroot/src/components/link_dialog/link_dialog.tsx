import { useId, useState, type FormEvent } from 'react';
import { Icon } from '../../image/icons';
import Dialog from '../dialog/dialog';
import StatusMessage from '../status_message/status_message';
import './link_dialog.less';

const SAVE_ICON_SIZE = 18;

interface LinkDialogProps {
  /** The dialog's title, for example "Choose folder". */
  title: string;
  /** The label of the link box, for example "Folder link". */
  linkLabel: string;
  /** The link the box starts with; empty when none is saved. */
  initialLink: string;
  saveLabel: string;
  closeLabel: string;
  /** True while the save waits for the API; Save is then disabled. */
  isSaving: boolean;
  /** Shown as an alert under the box when the last save failed. */
  errorText?: string;
  onSave: (link: string) => void;
  onClose: () => void;
}

/** A pop-up with one link box and a Save button with an icon, such as a Google Drive folder or a Spotify list link. */
const LinkDialog = ({
  title,
  linkLabel,
  initialLink,
  saveLabel,
  closeLabel,
  isSaving,
  errorText,
  onSave,
  onClose,
}: LinkDialogProps) => {
  const inputId = useId();
  // A url box strips the spaces around its value itself, so the value needs no trim.
  const [link, setLink] = useState(initialLink);
  const canSave = link !== '' && !isSaving;

  // A form, so Enter in the box saves like the button.
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSave) {
      onSave(link);
    }
  };

  return (
    <Dialog label={title} closeLabel={closeLabel} onClose={onClose}>
      <form className="link-dialog" onSubmit={submit}>
        <label className="link-dialog__label" htmlFor={inputId}>
          {linkLabel}
        </label>
        <input
          id={inputId}
          className="link-dialog__input"
          type="url"
          inputMode="url"
          autoComplete="off"
          value={link}
          onChange={(event) => setLink(event.target.value)}
        />
        {errorText !== undefined && <StatusMessage kind="error" text={errorText} />}
        <div className="link-dialog__actions">
          <button type="submit" className="link-dialog__save" disabled={!canSave}>
            <Icon name="save" size={SAVE_ICON_SIZE} />
            <span>{saveLabel}</span>
          </button>
        </div>
      </form>
    </Dialog>
  );
};

export default LinkDialog;
