// The routes of the app and the query name of a notification click.

export const ROUTES = {
  root: '/',
  words: '/words',
  flashcard: '/flashcard',
  active: '/active',
  schedule: '/schedule',
  config: '/config',
  settings: '/settings',
  unknown: '*',
} as const;

export const WORD_IDS_QUERY = 'wordIds';
