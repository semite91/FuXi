import { Icon } from '../../image/icons';
import Dialog from '../dialog/dialog';
import InfoTooltip from '../info_tooltip/info_tooltip';
import './embeddings_update.less';

const WARNING_ICON_SIZE = 32;
const WARNING_ICON_STROKE = 2.5;

interface EmbeddingsUpdateProps {
  linkLabel: string;
  aboutLabel: string;
  tipText: string;
  confirmTitle: string;
  /** The line under the confirm title, which tells what the update does. */
  confirmNotice: string;
  confirmLabel: string;
  closeLabel: string;
  isConfirmOpen: boolean;
  onAsk: () => void;
  onConfirm: () => void;
  onClose: () => void;
}

const EmbeddingsUpdate = ({
  linkLabel,
  aboutLabel,
  tipText,
  confirmTitle,
  confirmNotice,
  confirmLabel,
  closeLabel,
  isConfirmOpen,
  onAsk,
  onConfirm,
  onClose,
}: EmbeddingsUpdateProps) => (
  <div className="embeddings-update">
    <button type="button" className="embeddings-update__link" onClick={onAsk}>
      {linkLabel}
    </button>
    <InfoTooltip label={aboutLabel} text={tipText} />

    {isConfirmOpen && (
      <Dialog
        label={confirmTitle}
        closeLabel={closeLabel}
        onClose={onClose}
        isTitleCentered
        icon={
          <span className="embeddings-update__warning" aria-hidden="true">
            <Icon name="info" size={WARNING_ICON_SIZE} strokeWidth={WARNING_ICON_STROKE} />
          </span>
        }
      >
        <p className="embeddings-update__notice">{confirmNotice}</p>
        <button type="button" className="embeddings-update__confirm" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </Dialog>
    )}
  </div>
);

export default EmbeddingsUpdate;
