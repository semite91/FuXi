import PageCard from '../components/page_card/page_card';
import ScheduleEntryDialog from '../components/schedule_entry_dialog/schedule_entry_dialog';
import ScheduleList, { type ScheduleListRow } from '../components/schedule_list/schedule_list';
import ScheduleMonth, { type ScheduleChip, type ScheduleMonthCell } from '../components/schedule_month/schedule_month';
import ScheduleToolbar, { type ViewOption } from '../components/schedule_toolbar/schedule_toolbar';
import StatusMessage from '../components/status_message/status_message';
import { APP_TEXTS, SCHEDULE_TEXTS } from '../constants/texts';
import { useSchedule } from '../hooks/use_schedule';
import type { NotificationWindow } from '../services/schedule_service';
import {
  addHours,
  dayHours,
  dayLabel,
  monthCells,
  rangeLabel,
  weekDayLabel,
  weekDayTimeLabel,
  weekDays,
  windowsBetween,
  windowsOfDay,
  type CalendarView,
  type MonthCell,
} from '../utils/calendar';
import { addDays, formatTime, isSameDay, startOfDay } from '../utils/date_format';

const MONTH_CHIP_LIMIT = 2;
const TIME_RANGE_SEPARATOR = '–';

const VIEWS: readonly ViewOption<CalendarView>[] = [
  { view: 'month', label: SCHEDULE_TEXTS.month },
  { view: 'week', label: SCHEDULE_TEXTS.week },
  { view: 'day', label: SCHEDULE_TEXTS.day },
];

const chipLabel = (window: NotificationWindow): string => `${SCHEDULE_TEXTS.editEntryAt} ${formatTime(window.start)}`;

/** The start time on the day the window starts, "cont." on its later days. */
const monthChip = (window: NotificationWindow, day: Date): ScheduleChip => ({
  id: window.id,
  text: isSameDay(window.start, day) ? formatTime(window.start) : SCHEDULE_TEXTS.continued,
  label: chipLabel(window),
});

/** "09:00–10:00", "09:00–Thu 10:00", "Until 10:00" or "All day". */
const dayText = (window: NotificationWindow, day: Date): string => {
  const end = formatTime(window.end);
  // A window that ends at midnight ends with the day before.
  const endsToday = window.end <= addDays(startOfDay(day), 1);

  if (isSameDay(window.start, day)) {
    return formatTime(window.start) + TIME_RANGE_SEPARATOR + (endsToday ? end : weekDayTimeLabel(window.end, end));
  }

  return endsToday ? `${SCHEDULE_TEXTS.until} ${end}` : SCHEDULE_TEXTS.allDay;
};

const toMonthCell = (cell: MonthCell): ScheduleMonthCell => {
  const hiddenCount = cell.windows.length - MONTH_CHIP_LIMIT;

  return {
    key: cell.date.toISOString(),
    dayNumber: cell.date.getDate(),
    isInMonth: cell.isInMonth,
    isToday: cell.isToday,
    chips: cell.windows.slice(0, MONTH_CHIP_LIMIT).map((window) => monthChip(window, cell.date)),
    more:
      hiddenCount > 0
        ? { text: `+${hiddenCount}`, label: `${SCHEDULE_TEXTS.showAllEntriesOf} ${dayLabel(cell.date)}` }
        : undefined,
  };
};

const weekRows = (date: Date, windows: readonly NotificationWindow[]): ScheduleListRow[] =>
  weekDays(date).map((day) => ({
    key: day.toISOString(),
    label: weekDayLabel(day),
    chips: windowsOfDay(windows, day).map((window) => ({
      id: window.id,
      text: dayText(window, day),
      label: chipLabel(window),
    })),
  }));

/** A window shows its text in its first hour row of the day and an empty block in the next ones. */
const dayRows = (date: Date, windows: readonly NotificationWindow[]): ScheduleListRow[] => {
  const day = startOfDay(date);

  return dayHours(date).map((hour) => ({
    key: hour.toISOString(),
    label: formatTime(hour),
    chips: windowsBetween(windows, hour, addHours(hour, 1)).map((window) => ({
      id: window.id,
      text: window.start >= hour || hour.getTime() === day.getTime() ? dayText(window, day) : '',
      label: chipLabel(window),
    })),
  }));
};

const SchedulePage = () => {
  const schedule = useSchedule(SCHEDULE_TEXTS.overlap);
  const { draft, view, date, windows } = schedule;
  const draftError = draft?.isRangeInvalid ? SCHEDULE_TEXTS.invalidRange : (draft?.error ?? '');

  return (
    <PageCard>
      <h1>{SCHEDULE_TEXTS.title}</h1>
      <ScheduleToolbar
        newEntryLabel={SCHEDULE_TEXTS.newEntry}
        viewGroupLabel={SCHEDULE_TEXTS.view}
        views={VIEWS}
        activeView={view}
        previousLabel={SCHEDULE_TEXTS.previous}
        nextLabel={SCHEDULE_TEXTS.next}
        todayLabel={SCHEDULE_TEXTS.today}
        rangeLabel={rangeLabel(view, date)}
        onNewEntry={schedule.openNew}
        onView={schedule.setView}
        onPrevious={schedule.goPrevious}
        onNext={schedule.goNext}
        onToday={schedule.goToday}
      />

      {schedule.loadError !== '' && <StatusMessage kind="error" text={schedule.loadError} />}

      {view === 'month' ? (
        <ScheduleMonth
          weekdays={SCHEDULE_TEXTS.weekdays}
          cells={monthCells(date, windows, new Date()).map(toMonthCell)}
          onOpenChip={schedule.openEdit}
          onOpenDay={(key) => schedule.showDay(new Date(key))}
        />
      ) : (
        <ScheduleList
          rows={view === 'week' ? weekRows(date, windows) : dayRows(date, windows)}
          onOpenChip={schedule.openEdit}
        />
      )}

      {draft && (
        <ScheduleEntryDialog
          title={draft.id === null ? SCHEDULE_TEXTS.newEntry : SCHEDULE_TEXTS.editEntry}
          closeLabel={APP_TEXTS.closeDialog}
          titleLabel={SCHEDULE_TEXTS.entryTitle}
          titleValue={SCHEDULE_TEXTS.entryTitleValue}
          startLabel={SCHEDULE_TEXTS.start}
          endLabel={SCHEDULE_TEXTS.end}
          cancelLabel={SCHEDULE_TEXTS.cancel}
          saveLabel={SCHEDULE_TEXTS.save}
          deleteLabel={SCHEDULE_TEXTS.delete}
          start={draft.start}
          end={draft.end}
          onChangeStart={schedule.changeStart}
          onChangeEnd={schedule.changeEnd}
          onCancel={schedule.cancel}
          onSave={schedule.save}
          onDelete={draft.id === null ? undefined : schedule.remove}
          notice={draftError === '' ? undefined : <StatusMessage kind="error" text={draftError} />}
        />
      )}
    </PageCard>
  );
};

export default SchedulePage;
