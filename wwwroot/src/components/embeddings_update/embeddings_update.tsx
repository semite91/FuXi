import { Icon } from '../../image/icons';
import Dialog from '../dialog/dialog';
import Tooltip from '../tooltip/tooltip';
import './embeddings_update.less';

const INFO_ICON_SIZE = 12;
const INFO_ICON_STROKE = 3.6;

interface EmbeddingsUpdateProps {
  linkLabel: string;
  aboutLabel: string;
  tipText: string;
  confirmTitle: string;
  confirmLabel: string;
  closeLabel: string;
  /** The title of the result dialog. Without it no result is shown. */
  resultTitle?: string;
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
  confirmLabel,
  closeLabel,
  resultTitle,
  isConfirmOpen,
  onAsk,
  onConfirm,
  onClose,
}: EmbeddingsUpdateProps) => (
  <div className="embeddings-update">
    <button type="button" className="embeddings-update__link" onClick={onAsk}>
      {linkLabel}
    </button>
    <Tooltip text={tipText}>
      <button type="button" className="embeddings-update__info" aria-label={aboutLabel}>
        <Icon name="info" size={INFO_ICON_SIZE} strokeWidth={INFO_ICON_STROKE} />
      </button>
    </Tooltip>

    {isConfirmOpen && (
      <Dialog label={confirmTitle} closeLabel={closeLabel} onClose={onClose}>
        <h2 className="embeddings-update__title">{confirmTitle}</h2>
        <button type="button" className="embeddings-update__confirm" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </Dialog>
    )}

    {resultTitle !== undefined && (
      <Dialog label={resultTitle} closeLabel={closeLabel} onClose={onClose}>
        <h2 className="embeddings-update__title" role="status">
          {resultTitle}
        </h2>
      </Dialog>
    )}
  </div>
);

export default EmbeddingsUpdate;
