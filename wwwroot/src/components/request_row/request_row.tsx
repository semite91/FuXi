import type { ReactNode } from 'react';
import InfoTooltip from '../info_tooltip/info_tooltip';
import StatusMessage from '../status_message/status_message';
import './request_row.less';

interface RequestRowProps {
  /** The source's logo, drawn hidden from screen readers. */
  logo: ReactNode;
  /** Shown at the right of the logo, for example "Notion". */
  text: string;
  /** The button's name, for example "Connect Notion"; it holds the shown text. */
  connectLabel: string;
  aboutLabel: string;
  tipText: string;
  /** The connection state; without it no state is shown yet. */
  stateText?: string;
  /** Shown as an alert when the sign-in failed. */
  errorText?: string;
  onConnect: () => void;
  /** Lines of this source under its state, such as the chosen Google Drive folder. */
  children?: ReactNode;
}

/** One source of the Requests toggle: its logo button with its name, an i tooltip, the state and the sign-in error. */
const RequestRow = ({
  logo,
  text,
  connectLabel,
  aboutLabel,
  tipText,
  stateText,
  errorText,
  onConnect,
  children,
}: RequestRowProps) => (
  // A group named after the source, so its lines read as one row of the Requests toggle.
  <div className="request-row" role="group" aria-label={text}>
    <div className="request-row__row">
      <button type="button" className="request-row__button" aria-label={connectLabel} onClick={onConnect}>
        {logo}
        <span className="request-row__text">{text}</span>
      </button>
      {/* The row is at the left of the screen, so the tip grows to the right and stays under the row. */}
      <InfoTooltip label={aboutLabel} text={tipText} placement="start" />
    </div>
    {stateText !== undefined && (
      <p className="request-row__state" role="status">
        {stateText}
      </p>
    )}
    {errorText !== undefined && <StatusMessage kind="error" text={errorText} />}
    {children}
  </div>
);

export default RequestRow;
