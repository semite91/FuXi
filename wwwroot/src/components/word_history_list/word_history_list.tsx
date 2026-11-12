import { Icon } from '../../image/icons';
import './word_history_list.less';

const ANSWER_ICON_SIZE = 16;
const ANSWER_ICON_STROKE = 2.5;

export interface WordHistoryRow {
  isKnown: boolean;
  dateText: string;
}

interface WordHistoryListProps {
  rows: readonly WordHistoryRow[];
  isKnownLabel: string;
  dateLabel: string;
  yesLabel: string;
  noLabel: string;
}

const WordHistoryList = ({ rows, isKnownLabel, dateLabel, yesLabel, noLabel }: WordHistoryListProps) => (
  <table className="word-history-list">
    <thead>
      <tr>
        <th scope="col">{isKnownLabel}</th>
        <th scope="col">{dateLabel}</th>
      </tr>
    </thead>
    <tbody>
      {rows.map((row, position) => (
        // A Word History entry has no id, and the list is never reordered.
        <tr key={position}>
          <td>
            <span className={row.isKnown ? 'word-history-list__answer--yes' : 'word-history-list__answer--no'}>
              <Icon name={row.isKnown ? 'check' : 'close'} size={ANSWER_ICON_SIZE} strokeWidth={ANSWER_ICON_STROKE} />
              {row.isKnown ? yesLabel : noLabel}
            </span>
          </td>
          <td>{row.dateText}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

export default WordHistoryList;
