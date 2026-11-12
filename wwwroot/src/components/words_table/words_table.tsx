import { Icon } from '../../image/icons';
import Skeleton from '../skeleton/skeleton';
import './words_table.less';

const SORT_ICON_SIZE = 12;
const SORT_ICON_STROKE = 3;
const ANSWER_ICON_SIZE = 14;
const ANSWER_ICON_STROKE = 2.5;
const SKELETON_ROWS = [0, 1, 2, 3, 4, 5];

export interface WordsTableColumn<Key extends string> {
  key: Key;
  label: string;
  sortLabel: string;
}

export interface WordsTableRow {
  id: string;
  name: string;
  isKnown: boolean;
  isReinforcement: boolean;
  knownCount: string;
  shownCount: string;
  recursiveKnownCount: string;
  lastShownDate: string;
}

interface WordsTableProps<Key extends string> {
  label: string;
  columns: readonly WordsTableColumn<Key>[];
  rows: readonly WordsTableRow[];
  isLoading: boolean;
  sortKey: Key | null;
  sortDirection: 'ascending' | 'descending' | null;
  yesLabel: string;
  noLabel: string;
  onSort: (key: Key) => void;
  onOpenWord: (id: string) => void;
}

const WordsTable = <Key extends string>({
  label,
  columns,
  rows,
  isLoading,
  sortKey,
  sortDirection,
  yesLabel,
  noLabel,
  onSort,
  onOpenWord,
}: WordsTableProps<Key>) => (
  <div className="words-table">
    <table aria-label={label} aria-busy={isLoading}>
      <thead>
        <tr>
          {columns.map((column) => {
            const direction = column.key === sortKey ? sortDirection : null;

            return (
              <th key={column.key} scope="col" aria-sort={direction ?? 'none'}>
                <span className="words-table__header">
                  {column.label}
                  <button type="button" className="words-table__sort" aria-label={column.sortLabel} onClick={() => onSort(column.key)}>
                    <Icon
                      name={direction === 'descending' ? 'down' : 'up'}
                      size={SORT_ICON_SIZE}
                      strokeWidth={SORT_ICON_STROKE}
                      className={direction === null ? 'words-table__sort-icon' : 'words-table__sort-icon--active'}
                    />
                  </button>
                </span>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {isLoading
          ? SKELETON_ROWS.map((row) => (
              <tr key={row} aria-hidden="true">
                {columns.map((column) => (
                  <td key={column.key}>
                    <Skeleton size="cell" />
                  </td>
                ))}
              </tr>
            ))
          : rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <button type="button" className="words-table__word" onClick={() => onOpenWord(row.id)}>
                    {row.name}
                  </button>
                </td>
                <td>
                  <span className={row.isKnown ? 'words-table__flag--yes' : 'words-table__flag--no'}>
                    <Icon name={row.isKnown ? 'check' : 'close'} size={ANSWER_ICON_SIZE} strokeWidth={ANSWER_ICON_STROKE} />
                    {row.isKnown ? yesLabel : noLabel}
                  </span>
                </td>
                <td>{row.isReinforcement ? yesLabel : noLabel}</td>
                <td>{row.knownCount}</td>
                <td>{row.shownCount}</td>
                <td>{row.recursiveKnownCount}</td>
                <td>{row.lastShownDate}</td>
              </tr>
            ))}
      </tbody>
    </table>
  </div>
);

export default WordsTable;
