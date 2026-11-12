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
}

const ERROR_KIND = 'error';

const StatusMessage = ({ text, kind = 'note' }: StatusMessageProps) => (
  <p className={KIND_CLASSES[kind]} role={kind === ERROR_KIND ? 'alert' : 'status'}>
    {text}
  </p>
);

export default StatusMessage;
