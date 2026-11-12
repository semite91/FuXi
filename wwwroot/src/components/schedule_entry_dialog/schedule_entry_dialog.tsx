import { useId, type ReactNode } from 'react';
import Dialog from '../dialog/dialog';
import './schedule_entry_dialog.less';

interface ScheduleEntryDialogProps {
  title: string;
  closeLabel: string;
  titleLabel: string;
  titleValue: string;
  startLabel: string;
  endLabel: string;
  cancelLabel: string;
  saveLabel: string;
  deleteLabel: string;
  start: string;
  end: string;
  onChangeStart: (value: string) => void;
  onChangeEnd: (value: string) => void;
  onCancel: () => void;
  onSave: () => void;
  /** Without a handler the Delete button is not shown. */
  onDelete?: () => void;
  /** A message above the buttons, such as an invalid range. */
  notice?: ReactNode;
}

const ScheduleEntryDialog = ({
  title,
  closeLabel,
  titleLabel,
  titleValue,
  startLabel,
  endLabel,
  cancelLabel,
  saveLabel,
  deleteLabel,
  start,
  end,
  onChangeStart,
  onChangeEnd,
  onCancel,
  onSave,
  onDelete,
  notice,
}: ScheduleEntryDialogProps) => {
  const idPrefix = useId();

  return (
    <Dialog label={title} closeLabel={closeLabel} onClose={onCancel}>
      <h2>{title}</h2>
      <div className="schedule-entry-dialog__field">
        <label htmlFor={`${idPrefix}title`}>{titleLabel}</label>
        <input id={`${idPrefix}title`} type="text" value={titleValue} disabled readOnly />
      </div>
      <div className="schedule-entry-dialog__field">
        <label htmlFor={`${idPrefix}start`}>{startLabel}</label>
        <input id={`${idPrefix}start`} type="datetime-local" value={start} onChange={(event) => onChangeStart(event.target.value)} />
      </div>
      <div className="schedule-entry-dialog__field">
        <label htmlFor={`${idPrefix}end`}>{endLabel}</label>
        <input id={`${idPrefix}end`} type="datetime-local" value={end} onChange={(event) => onChangeEnd(event.target.value)} />
      </div>
      {notice}
      <div className="schedule-entry-dialog__actions">
        {onDelete && (
          <button type="button" className="schedule-entry-dialog__delete" onClick={onDelete}>
            {deleteLabel}
          </button>
        )}
        <button type="button" className="schedule-entry-dialog__cancel" onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" className="schedule-entry-dialog__save" onClick={onSave}>
          {saveLabel}
        </button>
      </div>
    </Dialog>
  );
};

export default ScheduleEntryDialog;
