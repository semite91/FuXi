import './status_message.less';

const KIND_CLASSES = {
  message: 'status-message status-message--message',
  note: 'status-message status-message--note',
  error: 'status-message status-message--error',
  hidden: 'status-message status-message--hidden',
} as const;

interface StatusMessageProps {
  text: string;
  /** message: large centered text. note: small text. error: an alert. hidden: only for screen readers. */
  kind?: keyof typeof KIND_CLASSES;
  /** False for a plain note that is not news: no status or alert role, so screen readers do not announce it. */
  isAnnounced?: boolean;
}

const ERROR_KIND = 'error';

const announcedRole = (kind: keyof typeof KIND_CLASSES) => (kind === ERROR_KIND ? 'alert' : 'status');

const StatusMessage = ({ text, kind = 'note', isAnnounced = true }: StatusMessageProps) => (
  <p className={KIND_CLASSES[kind]} role={isAnnounced ? announcedRole(kind) : undefined}>
    {text}
  </p>
);

export default StatusMessage;
