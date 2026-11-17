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
  /** False for a plain note that is not news: no status role, so screen readers do not announce it. An error is always an alert. */
  isAnnounced?: boolean;
}

const ERROR_KIND = 'error';

/** An error is always an alert; any other kind is a status only when it is announced. */
const messageRole = (kind: keyof typeof KIND_CLASSES, isAnnounced: boolean) => {
  if (kind === ERROR_KIND) {
    return 'alert';
  }

  return isAnnounced ? 'status' : undefined;
};

const StatusMessage = ({ text, kind = 'note', isAnnounced = true }: StatusMessageProps) => (
  <p className={KIND_CLASSES[kind]} role={messageRole(kind, isAnnounced)}>
    {text}
  </p>
);

export default StatusMessage;
