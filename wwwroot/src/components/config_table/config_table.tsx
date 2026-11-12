import IconButton from '../icon_button/icon_button';
import './config_table.less';

const EDIT_ICON_SIZE = 20;

export interface ConfigTableRow {
  id: string;
  name: string;
  value: string;
  editLabel: string;
}

interface ConfigTableProps {
  label: string;
  nameLabel: string;
  valueLabel: string;
  editColumnLabel: string;
  rows: readonly ConfigTableRow[];
  onEdit: (id: string) => void;
}

const ConfigTable = ({ label, nameLabel, valueLabel, editColumnLabel, rows, onEdit }: ConfigTableProps) => (
  <table className="config-table" aria-label={label}>
    <thead>
      <tr>
        <th scope="col">{nameLabel}</th>
        <th scope="col">{valueLabel}</th>
        <th scope="col">
          <span className="config-table__hidden">{editColumnLabel}</span>
        </th>
      </tr>
    </thead>
    <tbody>
      {rows.map((row) => (
        <tr key={row.id}>
          <td className="config-table__name">{row.name}</td>
          <td className="config-table__value">{row.value}</td>
          <td>
            <IconButton icon="edit" shape="plain" iconSize={EDIT_ICON_SIZE} label={row.editLabel} onClick={() => onEdit(row.id)} />
          </td>
        </tr>
      ))}
    </tbody>
  </table>
);

export default ConfigTable;
