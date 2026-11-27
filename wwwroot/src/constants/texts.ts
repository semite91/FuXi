// Every text the Learner sees. Components get their texts from here or through props.

export const APP_TEXTS = {
  name: 'FuXi',
  openMenu: 'Open menu',
  loading: 'Loading',
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
  failed: 'Notifications could not be enabled.',
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
  syncNotice: 'Your info will be synced',
  updating: 'Updating embeddings. This can take a while.',
  updated: 'Embeddings updated',
  failed: 'Embeddings could not be updated.',
} as const;

export const REQUESTS_TEXTS = {
  title: 'Requests',
} as const;

/** The connection state every source of the Requests toggle shows: "Connected: <name>" when the name is known. */
export const CONNECTION_TEXTS = {
  notConnected: 'Not connected',
  connected: 'Connected',
  nameSeparator: ': ',
} as const;

export const NOTION_TEXTS = {
  connect: 'Connect Notion',
  label: 'Notion',
  failed: 'Notion could not be connected.',
  about: 'About Notion',
  tip: 'Connect Notion pages',
} as const;

export const GOOGLE_DRIVE_TEXTS = {
  connect: 'Connect Google Drive',
  label: 'Google Drive',
  failed: 'Google Drive could not be connected.',
  about: 'About Google Drive',
  tip: 'Connect Google Drive images',
  noFolder: 'No folder chosen',
  folderChosen: 'Folder chosen',
  openFolder: 'Open in Drive',
  chooseFolder: 'Choose folder',
  folderLink: 'Folder link',
  save: 'Save',
  notAFolderLink: 'This is not a Google Drive folder link.',
  saveFailed: 'The folder could not be saved.',
} as const;

export const LETTERBOXD_TEXTS = {
  connect: 'Upload Letterboxd liked movies',
  label: 'Letterboxd',
  about: 'About Letterboxd',
  tip: 'Upload your liked movies',
  noFile: 'No file uploaded',
  uploaded: 'Uploaded',
  movieOne: 'movie',
  movieMany: 'movies',
  guideTitle: 'Upload your liked movies',
  hint: 'Upload likes/films.csv from the export.',
  uploadCsv: 'Upload CSV',
  notALikesFile: 'The file must be a CSV with the Date, Name and Year columns.',
  uploadFailed: 'The file could not be uploaded.',
  accept: '.csv,text/csv',
  settingsStepAlt: 'Screenshot: the Settings button on your Letterboxd profile',
  settingsStepCaption: 'Open Settings from your profile menu.',
  dataStepAlt: 'Screenshot: the Data tab in Settings',
  dataStepCaption: 'Open the Data tab.',
  exportStepAlt: 'Screenshot: the export button on the Data tab',
  exportStepCaption: 'Press Export your data and unzip the file you get.',
} as const;

export const SPOTIFY_TEXTS = {
  connect: 'Connect Spotify',
  label: 'Spotify',
  failed: 'Spotify could not be connected.',
  about: 'About Spotify',
  tip: 'Connect your Spotify list',
  noPlaylist: 'No playlist chosen',
  playlistChosen: 'Playlist chosen',
  openPlaylist: 'Open in Spotify',
  connectAgain: 'Connect again',
  choosePlaylist: 'Choose playlist',
  playlistLink: 'Playlist link',
  save: 'Save',
  notAPlaylistLink: 'This is not a Spotify playlist link.',
  playlistNotReadable: 'Spotify does not let FuXi read this playlist. Choose one you own or collaborate on.',
  saveFailed: 'The playlist could not be saved.',
} as const;

export const CREDITS_TEXTS = {
  title: 'Credits',
  tmdbLogo: 'TMDB',
  tmdbNotice: 'This product uses the TMDB API but is not endorsed or certified by TMDB.',
} as const;
