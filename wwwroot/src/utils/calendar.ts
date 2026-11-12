// Pure calendar arithmetic for the Schedule page, in the Learner's local time zone.
import type { NotificationWindow } from '../services/schedule_service';
import { addDays, isSameDay, startOfDay } from './date_format';

export type CalendarView = 'month' | 'week' | 'day';

export interface DateRange {
  from: Date;
  to: Date;
}

export interface MonthCell {
  date: Date;
  isInMonth: boolean;
  isToday: boolean;
  windows: NotificationWindow[];
}

export const DAYS_PER_WEEK = 7;
export const HOURS_PER_DAY = 24;
const MONTH_GRID_WEEKS = 6;
const MONTH_GRID_DAYS = MONTH_GRID_WEEKS * DAYS_PER_WEEK;
// JavaScript counts days from Sunday, the calendar starts on Monday.
const MONDAY_SHIFT = 6;
const LOCALE = 'en-GB';

const daysSinceMonday = (date: Date): number => (date.getDay() + MONDAY_SHIFT) % DAYS_PER_WEEK;

export const startOfWeek = (date: Date): Date => addDays(startOfDay(date), -daysSinceMonday(date));

const startOfMonthGrid = (date: Date): Date => startOfWeek(new Date(date.getFullYear(), date.getMonth(), 1));

/** The dates that the view shows. The month view shows six whole weeks. */
export const visibleRange = (view: CalendarView, date: Date): DateRange => {
  if (view === 'month') {
    const from = startOfMonthGrid(date);

    return { from, to: addDays(from, MONTH_GRID_DAYS) };
  }

  const from = view === 'week' ? startOfWeek(date) : startOfDay(date);

  return { from, to: addDays(from, view === 'week' ? DAYS_PER_WEEK : 1) };
};

export const isWithin = (inner: DateRange, outer: DateRange): boolean =>
  inner.from >= outer.from && inner.to <= outer.to;

/** Moves one month, one week or one day forward (1) or back (-1). */
export const moveDate = (view: CalendarView, date: Date, direction: number): Date => {
  if (view === 'month') {
    return new Date(date.getFullYear(), date.getMonth() + direction, 1);
  }

  return addDays(startOfDay(date), direction * (view === 'week' ? DAYS_PER_WEEK : 1));
};

/** The Notification Windows that overlap the range, earliest first. */
export const windowsBetween = (windows: readonly NotificationWindow[], from: Date, to: Date): NotificationWindow[] =>
  windows
    .filter((window) => window.start < to && window.end > from)
    .sort((first, second) => first.start.getTime() - second.start.getTime());

export const windowsOfDay = (windows: readonly NotificationWindow[], day: Date): NotificationWindow[] =>
  windowsBetween(windows, startOfDay(day), addDays(startOfDay(day), 1));

export const monthCells = (date: Date, windows: readonly NotificationWindow[], today: Date): MonthCell[] => {
  const first = startOfMonthGrid(date);

  return Array.from({ length: MONTH_GRID_DAYS }, (_, position) => {
    const day = addDays(first, position);

    return {
      date: day,
      isInMonth: day.getMonth() === date.getMonth(),
      isToday: isSameDay(day, today),
      windows: windowsOfDay(windows, day),
    };
  });
};

export const weekDays = (date: Date): Date[] =>
  Array.from({ length: DAYS_PER_WEEK }, (_, position) => addDays(startOfWeek(date), position));

export const dayHours = (date: Date): Date[] => {
  const day = startOfDay(date);

  return Array.from(
    { length: HOURS_PER_DAY },
    (_, hour) => new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour),
  );
};

export const addHours = (date: Date, hours: number): Date =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours() + hours, date.getMinutes());

/** "November 2026", "9 – 15 Nov 2026" or "Thu, 12 Nov 2026". */
export const rangeLabel = (view: CalendarView, date: Date): string => {
  if (view === 'month') {
    return date.toLocaleDateString(LOCALE, { month: 'long', year: 'numeric' });
  }

  if (view === 'day') {
    return date.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  }

  const monday = startOfWeek(date);
  const sunday = addDays(monday, DAYS_PER_WEEK - 1);

  return `${monday.getDate()} – ${sunday.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' })}`;
};

/** "Mon 9" */
export const weekDayLabel = (date: Date): string =>
  date.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric' });

/** "12 November" */
export const dayLabel = (date: Date): string => date.toLocaleDateString(LOCALE, { day: 'numeric', month: 'long' });

/** "Thu 14:00" */
export const weekDayTimeLabel = (date: Date, time: string): string =>
  `${date.toLocaleDateString(LOCALE, { weekday: 'short' })} ${time}`;
