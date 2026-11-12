// Date texts and date arithmetic in the Learner's local time zone.

const PAD_LENGTH = 2;
const PAD_CHARACTER = '0';
const DATE_SEPARATOR = '.';
const TIME_SEPARATOR = ':';

const pad = (value: number): string => String(value).padStart(PAD_LENGTH, PAD_CHARACTER);

/** dd.MM.yyyy */
export const formatDate = (date: Date): string =>
  [pad(date.getDate()), pad(date.getMonth() + 1), String(date.getFullYear())].join(DATE_SEPARATOR);

/** HH:mm */
export const formatTime = (date: Date): string => pad(date.getHours()) + TIME_SEPARATOR + pad(date.getMinutes());

/** The value format of a datetime-local input: yyyy-MM-ddTHH:mm. */
export const toInputValue = (date: Date): string =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${formatTime(date)}`;

/** Reads a datetime-local value as local time. Returns null when it is not a date-time. */
export const fromInputValue = (value: string): Date | null => {
  const date = new Date(value);

  return value === '' || Number.isNaN(date.getTime()) ? null : date;
};

export const startOfDay = (date: Date): Date => new Date(date.getFullYear(), date.getMonth(), date.getDate());

export const addDays = (date: Date, days: number): Date =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days, date.getHours(), date.getMinutes());

export const isSameDay = (first: Date, second: Date): boolean =>
  startOfDay(first).getTime() === startOfDay(second).getTime();
