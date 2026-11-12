import { API_URL_KEY, createApiClient } from './api_client';

const GET_SCHEDULE = '/api/GetSchedule';
const UPDATE_SCHEDULE = '/api/UpdateSchedule';
const DELETE_SCHEDULE = '/api/DeleteSchedule';

/** A Notification Window with local Date values. */
export interface NotificationWindow {
  id: string;
  start: Date;
  end: Date;
}

interface ScheduleItem {
  id: string;
  startDate: string;
  endDate: string;
}

const client = createApiClient(API_URL_KEY);

/** Date-times go to the backend as UTC. */
const toUtcText = (date: Date): string => date.toISOString();

export const getSchedule = async (from: Date, to: Date): Promise<NotificationWindow[]> => {
  const items = await client.get<ScheduleItem[]>(GET_SCHEDULE, { period: [toUtcText(from), toUtcText(to)] });

  return items.map((item) => ({ id: item.id, start: new Date(item.startDate), end: new Date(item.endDate) }));
};

/** Without an id a new Notification Window is added. */
export const saveNotificationWindow = (id: string | null, start: Date, end: Date): Promise<{ id: string }> =>
  client.post(UPDATE_SCHEDULE, {
    ...(id === null ? {} : { id }),
    startDate: toUtcText(start),
    endDate: toUtcText(end),
  });

export const deleteNotificationWindow = (id: string): Promise<void> => client.remove(DELETE_SCHEDULE, { id });
