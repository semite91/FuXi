// Sample API data for the frontend tests.
import type { ConfigItem } from '../services/config_service';
import type { CardWord, FilteredWord } from '../services/words_service';

export const WORD_ONE_ID = '11111111-1111-4111-8111-111111111111';
export const WORD_TWO_ID = '22222222-2222-4222-8222-222222222222';
export const WORD_THREE_ID = '33333333-3333-4333-8333-333333333333';

export const cardWord = (id: string, name: string, overrides: Partial<CardWord> = {}): CardWord => ({
  id,
  name,
  translation: `${name} translation`,
  counter: 1,
  isReinforcement: false,
  lastShownDate: null,
  content: `${name} content`,
  ...overrides,
});

export const TWO_CARDS = [cardWord(WORD_ONE_ID, 'Ephemeral'), cardWord(WORD_TWO_ID, 'Serendipity')];
export const THREE_CARDS = [...TWO_CARDS, cardWord(WORD_THREE_ID, 'Ubiquitous')];

export const filteredWord = (id: string, name: string, overrides: Partial<FilteredWord> = {}): FilteredWord => ({
  id,
  name,
  isReinforcement: false,
  isKnown: false,
  lastShownDate: null,
  shownCount: 0,
  knownCount: 0,
  isRotated: false,
  counter: null,
  ...overrides,
});

export const CONFIGS: ConfigItem[] = [
  { configId: 'c1', code: 'RotationCount', name: 'Rotation Count', value: '20', inputType: 'Number' },
  { configId: 'c2', code: 'NotificationPeriod', name: 'Notification period', value: '15', inputType: 'Number' },
  { configId: 'c3', code: 'StartDate', name: 'Start date', value: '2026-10-01', inputType: 'Date' },
  { configId: 'c4', code: 'Title', name: 'Notebook title', value: 'My words', inputType: 'String' },
];
