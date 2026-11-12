// Every text the Learner sees. Components get their texts from here or through props.

export const APP_TEXTS = {
  name: 'FuXi',
  openMenu: 'Open menu',
  loading: 'Loading',
  close: 'Close',
  closeDialog: 'Close dialog',
  yes: 'Yes',
  no: 'No',
  empty: '-',
  failed: 'The request failed.',
} as const;

export const MENU_TEXTS = {
  active: 'Active Words',
  words: 'Words',
  schedule: 'Schedule',
  config: 'Configs',
  settings: 'Settings',
} as const;

export const FLASHCARD_TEXTS = {
  question: 'Do you know this word?',
  noWords: 'Keep working like this; there are no words to review at the moment.',
  done: 'Done',
  reinforcement: 'Is reinforcement',
  previous: 'Previous word',
  next: 'Next word',
  contentUnavailable: 'Content is not available.',
  loadingContent: 'Loading content',
} as const;

export const HISTORY_TEXTS = {
  title: 'History',
  isKnown: 'Is It known',
  date: 'Date',
  loading: 'Loading history',
} as const;

export const WORDS_TEXTS = {
  title: 'Words',
  openFilters: 'Open filters',
  closeFilters: 'Close filters',
  filters: 'Filters',
  name: 'Name',
  isKnown: 'Is known',
  isReinforcement: 'Is reinforcement',
  knownCount: 'Known count',
  shownCount: 'Shown count',
  recursiveKnownCount: 'Recursive known count',
  lastShownDate: 'Last shown date',
  isActiveWord: 'Is active word',
  all: 'All',
  clear: 'Clear',
  apply: 'Apply',
  loading: 'Loading words',
  noMatch: 'No words match these filters.',
  sortBy: 'Sort by',
} as const;

export const CONFIG_TEXTS = {
  title: 'Configs',
  name: 'Name',
  value: 'Value',
  edit: 'Edit',
  save: 'Save',
} as const;

export const PERMISSION_TEXTS = {
  enable: 'Enable notifications',
  default: 'Notifications: not asked',
  granted: 'Notifications: allowed',
  denied: 'Notifications: blocked',
  unsupported: 'Notifications: not supported',
} as const;

export const SCHEDULE_TEXTS = {
  title: 'Schedule',
  newEntry: 'New entry',
  editEntry: 'Edit entry',
  view: 'View',
  month: 'Month',
  week: 'Week',
  day: 'Day',
  previous: 'Previous',
  next: 'Next',
  today: 'Today',
  weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  continued: 'cont.',
  until: 'Until',
  allDay: 'All day',
  showAllEntriesOf: 'Show all entries of',
  editEntryAt: 'Edit entry at',
  entryTitle: 'Title',
  entryTitleValue: 'Selected',
  start: 'Start',
  end: 'End',
  cancel: 'Cancel',
  save: 'Save',
  delete: 'Delete',
  invalidRange: 'The end must be later than the start.',
  overlap: 'This Notification Window overlaps another one.',
} as const;

export const SETTINGS_TEXTS = {
  title: 'Settings',
  updateEmbeddings: 'Update embeddings',
  about: 'About updating embeddings',
  tip: 'It will update to your current data.',
  confirm: 'Are you sure?',
  updated: 'Embeddings updated',
  failed: 'Embeddings could not be updated.',
} as const;
