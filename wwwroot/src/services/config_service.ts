import { API_URL_KEY, createApiClient } from './api_client';

const GET_CONFIGS = '/api/GetConfigs';
const UPDATE_CONFIG = '/api/UpdateConfig';
const UPDATE_NOTIFICATION_PERIOD = '/api/UpdateNotificationPeriod';

export const NOTIFICATION_PERIOD_CODE = 'NotificationPeriod';

export type InputType = 'CheckboxList' | 'Radiobutton' | 'String' | 'Number' | 'Date';

export interface ConfigItem {
  configId: string;
  code: string;
  name: string;
  value: string;
  inputType: InputType;
}

const client = createApiClient(API_URL_KEY);

export const getConfigs = (): Promise<ConfigItem[]> => client.get(GET_CONFIGS);

/** The Notification Period has its own API, because it also restarts the notification timer. */
export const saveConfig = (config: ConfigItem, value: string): Promise<void> =>
  client.post(config.code === NOTIFICATION_PERIOD_CODE ? UPDATE_NOTIFICATION_PERIOD : UPDATE_CONFIG, {
    id: config.configId,
    value,
  });
