import { NotionLogo } from '../../image/icons';
import InfoTooltip from '../info_tooltip/info_tooltip';
import StatusMessage from '../status_message/status_message';
import './notion_connect.less';

interface NotionConnectProps {
  connectLabel: string;
  /** Shown at the right of the logo, for example "Notion". */
  text: string;
  aboutLabel: string;
  tipText: string;
  /** The connection state; without it no state is shown yet. */
  stateText?: string;
  /** Shown as an alert when the sign-in failed. */
  errorText?: string;
  onConnect: () => void;
}

/** The Notion row of the Requests toggle. */
const NotionConnect = ({ connectLabel, text, aboutLabel, tipText, stateText, errorText, onConnect }: NotionConnectProps) => (
  <div className="notion-connect">
    <div className="notion-connect__row">
      <button type="button" className="notion-connect__button" aria-label={connectLabel} onClick={onConnect}>
        <NotionLogo />
        <span className="notion-connect__text">{text}</span>
      </button>
      {/* The row is at the left of the screen, so the tip grows to the right and stays under the row. */}
      <InfoTooltip label={aboutLabel} text={tipText} placement="start" />
    </div>
    {stateText !== undefined && (
      <p className="notion-connect__state" role="status">
        {stateText}
      </p>
    )}
    {errorText !== undefined && <StatusMessage kind="error" text={errorText} />}
  </div>
);

export default NotionConnect;
