// The Word History list or its loading and error state, shared by the Flashcard and Words pages.
import StatusMessage from '../components/status_message/status_message';
import WordHistoryList from '../components/word_history_list/word_history_list';
import { APP_TEXTS, HISTORY_TEXTS } from '../constants/texts';
import type { WordHistoryItem } from '../services/words_service';
import { formatDate } from '../utils/date_format';

export interface LoadedHistory {
  status: 'loading' | 'loaded' | 'error';
  rows: readonly WordHistoryItem[];
}

export const renderWordHistory = (history: LoadedHistory | undefined) => {
  if (history === undefined || history.status === 'loading') {
    return <StatusMessage text={HISTORY_TEXTS.loading} />;
  }

  if (history.status === 'error') {
    return <StatusMessage kind="error" text={APP_TEXTS.failed} />;
  }

  return (
    <WordHistoryList
      rows={history.rows.map((row) => ({ isKnown: row.isKnown, dateText: formatDate(new Date(row.date)) }))}
      isKnownLabel={HISTORY_TEXTS.isKnown}
      dateLabel={HISTORY_TEXTS.date}
      yesLabel={APP_TEXTS.yes}
      noLabel={APP_TEXTS.no}
    />
  );
};
