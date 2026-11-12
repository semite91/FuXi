import type { ScheduleChip } from '../schedule_month/schedule_month';
import './schedule_list.less';

export interface ScheduleListRow {
  key: string;
  label: string;
  chips: readonly ScheduleChip[];
}

interface ScheduleListProps {
  rows: readonly ScheduleListRow[];
  onOpenChip: (id: string) => void;
}

/** The rows of the Week view (one per day) and of the Day view (one per hour). */
const ScheduleList = ({ rows, onOpenChip }: ScheduleListProps) => (
  <ul className="schedule-list">
    {rows.map((row) => (
      <li key={row.key} className="schedule-list__row">
        <span className="schedule-list__label">{row.label}</span>
        <div className="schedule-list__chips">
          {row.chips.map((chip) => (
            <button key={chip.id} type="button" className="schedule-list__chip" aria-label={chip.label} onClick={() => onOpenChip(chip.id)}>
              {chip.text}
            </button>
          ))}
        </div>
      </li>
    ))}
  </ul>
);

export default ScheduleList;
