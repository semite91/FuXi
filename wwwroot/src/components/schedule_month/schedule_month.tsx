import './schedule_month.less';

export interface ScheduleChip {
  id: string;
  text: string;
  label: string;
}

export interface ScheduleMonthCell {
  key: string;
  dayNumber: number;
  isInMonth: boolean;
  isToday: boolean;
  chips: readonly ScheduleChip[];
  /** The "+N" button of a day with more Notification Windows than chips. */
  more?: { text: string; label: string };
}

interface ScheduleMonthProps {
  weekdays: readonly string[];
  cells: readonly ScheduleMonthCell[];
  onOpenChip: (id: string) => void;
  onOpenDay: (key: string) => void;
}

const ScheduleMonth = ({ weekdays, cells, onOpenChip, onOpenDay }: ScheduleMonthProps) => (
  <div className="schedule-month">
    <div className="schedule-month__weekdays">
      {weekdays.map((weekday) => (
        <span key={weekday}>{weekday}</span>
      ))}
    </div>
    <div className="schedule-month__grid">
      {cells.map((cell) => (
        <div key={cell.key} className={cell.isInMonth ? 'schedule-month__cell' : 'schedule-month__cell schedule-month__cell--outside'}>
          <span className="schedule-month__number" aria-current={cell.isToday ? 'date' : undefined}>
            {cell.dayNumber}
          </span>
          {cell.chips.map((chip) => (
            <button key={chip.id} type="button" className="schedule-month__chip" aria-label={chip.label} onClick={() => onOpenChip(chip.id)}>
              {chip.text}
            </button>
          ))}
          {cell.more && (
            <button type="button" className="schedule-month__more" aria-label={cell.more.label} onClick={() => onOpenDay(cell.key)}>
              {cell.more.text}
            </button>
          )}
        </div>
      ))}
    </div>
  </div>
);

export default ScheduleMonth;
