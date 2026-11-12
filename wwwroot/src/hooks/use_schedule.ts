// The logic of the Schedule page: the shown range, its Notification Windows and the entry dialog.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, errorMessageOf } from '../services/api_client';
import {
  deleteNotificationWindow,
  getSchedule,
  saveNotificationWindow,
  type NotificationWindow,
} from '../services/schedule_service';
import { isWithin, moveDate, visibleRange, type CalendarView, type DateRange } from '../utils/calendar';
import { fromInputValue, toInputValue } from '../utils/date_format';

const DEFAULT_START_HOUR = 9;
const DEFAULT_END_HOUR = 10;
const CONFLICT_STATUS = 409;

export interface EntryDraft {
  /** Null for a new Notification Window. */
  id: string | null;
  start: string;
  end: string;
  isRangeInvalid: boolean;
  error: string;
}

const atHour = (date: Date, hour: number): Date => new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour);

export const useSchedule = (overlapMessage: string) => {
  const [view, setView] = useState<CalendarView>('month');
  const [date, setDate] = useState(() => new Date());
  const [windows, setWindows] = useState<NotificationWindow[]>([]);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState<EntryDraft | null>(null);
  const loadedRange = useRef<DateRange | null>(null);
  const latestLoad = useRef(0);
  const isBusy = useRef(false);

  const load = useCallback(async (range: DateRange) => {
    const loadNumber = ++latestLoad.current;
    loadedRange.current = range;

    try {
      const loaded = await getSchedule(range.from, range.to);

      if (loadNumber === latestLoad.current) {
        setWindows(loaded);
        setLoadError('');
      }
    } catch (error) {
      if (loadNumber === latestLoad.current) {
        loadedRange.current = null;
        setWindows([]);
        setLoadError(errorMessageOf(error));
      }
    }
  }, []);

  // Loads only when the view shows dates outside the loaded range.
  useEffect(() => {
    const range = visibleRange(view, date);

    if (loadedRange.current === null || !isWithin(range, loadedRange.current)) {
      void load(range);
    }
  }, [view, date, load]);

  const reload = (shownDate: Date) => {
    setDate(shownDate);

    return load(visibleRange(view, shownDate));
  };

  /** Runs one save or delete at a time and keeps the dialog open when it fails. */
  const runEntryAction = async (action: () => Promise<unknown>, shownDate: Date) => {
    if (isBusy.current) {
      return;
    }

    isBusy.current = true;

    try {
      await action();
      setDraft(null);
      await reload(shownDate);
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === CONFLICT_STATUS ? overlapMessage : errorMessageOf(error);
      setDraft((current) => current && { ...current, error: message });
    } finally {
      isBusy.current = false;
    }
  };

  const save = () => {
    if (draft === null) {
      return;
    }

    const start = fromInputValue(draft.start);
    const end = fromInputValue(draft.end);

    if (start === null || end === null || end <= start) {
      setDraft({ ...draft, isRangeInvalid: true, error: '' });
      return;
    }

    setDraft({ ...draft, isRangeInvalid: false, error: '' });
    void runEntryAction(() => saveNotificationWindow(draft.id, start, end), start);
  };

  const remove = () => {
    if (draft?.id != null) {
      const { id } = draft;
      void runEntryAction(() => deleteNotificationWindow(id), date);
    }
  };

  return {
    view,
    date,
    windows,
    loadError,
    draft,
    setView,
    showDay: (day: Date) => {
      setDate(day);
      setView('day');
    },
    goPrevious: () => setDate((current) => moveDate(view, current, -1)),
    goNext: () => setDate((current) => moveDate(view, current, 1)),
    goToday: () => setDate(new Date()),
    openNew: () =>
      setDraft({
        id: null,
        start: toInputValue(atHour(date, DEFAULT_START_HOUR)),
        end: toInputValue(atHour(date, DEFAULT_END_HOUR)),
        isRangeInvalid: false,
        error: '',
      }),
    openEdit: (id: string) => {
      const window = windows.find((item) => item.id === id);

      if (window !== undefined) {
        setDraft({
          id,
          start: toInputValue(window.start),
          end: toInputValue(window.end),
          isRangeInvalid: false,
          error: '',
        });
      }
    },
    changeStart: (start: string) => setDraft((current) => current && { ...current, start }),
    changeEnd: (end: string) => setDraft((current) => current && { ...current, end }),
    cancel: () => setDraft(null),
    save,
    remove,
  };
};
