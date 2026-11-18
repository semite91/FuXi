import { useRef, type ChangeEvent } from 'react';
import { Icon } from '../../image/icons';
import Dialog from '../dialog/dialog';
import StatusMessage from '../status_message/status_message';
import './upload_guide_dialog.less';

const UPLOAD_ICON_SIZE = 18;

export interface UploadGuideStep {
  /** The address of the step's screenshot, a local file. */
  image: string;
  /** What the screenshot shows, for screen readers. */
  imageAlt: string;
  caption: string;
}

interface UploadGuideDialogProps {
  /** The dialog's title, for example "Upload your liked movies". */
  title: string;
  /** The steps of the guide, in order. */
  steps: readonly UploadGuideStep[];
  /** A line above the upload button that says which file to upload. */
  hint: string;
  uploadLabel: string;
  closeLabel: string;
  /** The file types the chooser offers, for example ".csv". */
  accept: string;
  /** True while the upload waits for the API; the button is then disabled. */
  isUploading: boolean;
  /** Shown as an alert under the button when the last upload failed. */
  errorText?: string;
  onFile: (file: File) => void;
  onClose: () => void;
}

/** A pop-up with a numbered guide of screenshots and an upload button, such as the Letterboxd export. */
const UploadGuideDialog = ({
  title,
  steps,
  hint,
  uploadLabel,
  closeLabel,
  accept,
  isUploading,
  errorText,
  onFile,
  onClose,
}: UploadGuideDialogProps) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // The same file can be chosen again after a failure.
    event.target.value = '';
    if (file !== undefined) {
      onFile(file);
    }
  };

  return (
    <Dialog label={title} closeLabel={closeLabel} onClose={onClose}>
      <div className="upload-guide">
        <ol className="upload-guide__steps">
          {steps.map((step) => (
            <li key={step.imageAlt} className="upload-guide__step">
              <img className="upload-guide__image" src={step.image} alt={step.imageAlt} />
              <p className="upload-guide__caption">{step.caption}</p>
            </li>
          ))}
        </ol>
        <p className="upload-guide__hint">{hint}</p>
        <input ref={inputRef} type="file" accept={accept} hidden onChange={chooseFile} />
        {errorText !== undefined && <StatusMessage kind="error" text={errorText} />}
        <div className="upload-guide__actions">
          <button
            type="button"
            className="upload-guide__upload"
            disabled={isUploading}
            onClick={() => inputRef.current?.click()}
          >
            <Icon name="upload" size={UPLOAD_ICON_SIZE} />
            <span>{uploadLabel}</span>
          </button>
        </div>
      </div>
    </Dialog>
  );
};

export default UploadGuideDialog;
