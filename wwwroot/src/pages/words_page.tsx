import { useState } from 'react';
import Dialog from '../components/dialog/dialog';
import IconButton from '../components/icon_button/icon_button';
import PageCard from '../components/page_card/page_card';
import StatusMessage from '../components/status_message/status_message';
import WordsFilterPanel, { type FilterField } from '../components/words_filter_panel/words_filter_panel';
import WordsTable, { type WordsTableColumn } from '../components/words_table/words_table';
import { APP_TEXTS, HISTORY_TEXTS, WORDS_TEXTS } from '../constants/texts';
import { EMPTY_FILTER, useWords, type Choice, type FilterDraft, type SortKey } from '../hooks/use_words';
import type { FilteredWord } from '../services/words_service';
import { formatDate } from '../utils/date_format';
import { renderWordHistory } from './word_history_content';

const CHOICES: readonly { value: Choice; label: string }[] = [
  { value: '', label: WORDS_TEXTS.all },
  { value: 'yes', label: APP_TEXTS.yes },
  { value: 'no', label: APP_TEXTS.no },
];

const FILTER_FIELDS: readonly FilterField<keyof FilterDraft>[] = [
  { name: 'name', label: WORDS_TEXTS.name },
  { name: 'isReinforcement', label: WORDS_TEXTS.isReinforcement, choices: CHOICES },
  { name: 'isKnown', label: WORDS_TEXTS.isKnown, choices: CHOICES },
  { name: 'isRotated', label: WORDS_TEXTS.isActiveWord, choices: CHOICES },
];

const COLUMN_LABELS: readonly [SortKey, string][] = [
  ['name', WORDS_TEXTS.name],
  ['isKnown', WORDS_TEXTS.isKnown],
  ['isReinforcement', WORDS_TEXTS.isReinforcement],
  ['knownCount', WORDS_TEXTS.knownCount],
  ['shownCount', WORDS_TEXTS.shownCount],
  ['counter', WORDS_TEXTS.recursiveKnownCount],
  ['lastShownDate', WORDS_TEXTS.lastShownDate],
];

const COLUMNS: readonly WordsTableColumn<SortKey>[] = COLUMN_LABELS.map(([key, label]) => ({
  key,
  label,
  sortLabel: `${WORDS_TEXTS.sortBy} ${label}`,
}));

const toRow = (word: FilteredWord) => ({
  id: word.id,
  name: word.name,
  isKnown: word.isKnown,
  isReinforcement: word.isReinforcement,
  knownCount: String(word.knownCount),
  shownCount: String(word.shownCount),
  recursiveKnownCount: word.counter === null ? APP_TEXTS.empty : String(word.counter),
  lastShownDate: word.lastShownDate === null ? APP_TEXTS.empty : formatDate(new Date(word.lastShownDate)),
});

/** The Words page starts empty. Words are loaded when a filter is applied. */
const WordsPage = () => {
  const words = useWords();
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const { history } = words;

  const apply = (draft: Record<keyof FilterDraft, string>) => {
    setIsPanelOpen(false);
    void words.apply(draft as FilterDraft);
  };

  const openWord = (id: string) => {
    const word = words.words.find((item) => item.id === id);

    if (word !== undefined) {
      void words.openHistory(word);
    }
  };

  return (
    <PageCard
      title={WORDS_TEXTS.title}
      action={
        <IconButton icon="filter" label={WORDS_TEXTS.openFilters} aria-haspopup="dialog" onClick={() => setIsPanelOpen(true)} />
      }
    >

      <WordsTable
        label={WORDS_TEXTS.title}
        columns={COLUMNS}
        rows={words.words.map(toRow)}
        isLoading={words.status === 'loading'}
        sortKey={words.sort?.key ?? null}
        sortDirection={words.sort?.direction ?? null}
        yesLabel={APP_TEXTS.yes}
        noLabel={APP_TEXTS.no}
        onSort={words.sortBy}
        onOpenWord={openWord}
      />
      {words.status === 'loading' && <StatusMessage kind="hidden" text={WORDS_TEXTS.loading} />}
      {words.status === 'loaded' && words.words.length === 0 && <StatusMessage text={WORDS_TEXTS.noMatch} />}
      {words.status === 'error' && <StatusMessage kind="error" text={words.error} />}

      {isPanelOpen && (
        <WordsFilterPanel
          title={WORDS_TEXTS.filters}
          closeLabel={WORDS_TEXTS.closeFilters}
          clearLabel={WORDS_TEXTS.clear}
          applyLabel={WORDS_TEXTS.apply}
          fields={FILTER_FIELDS}
          values={words.applied}
          emptyValues={EMPTY_FILTER}
          onApply={apply}
          onClose={() => setIsPanelOpen(false)}
        />
      )}

      {history && (
        <Dialog label={history.wordName} closeLabel={APP_TEXTS.closeDialog} onClose={words.closeHistory}>
          <div className="dialog__head">
            <div>
              <h2>{history.wordName}</h2>
              <p className="dialog__subtitle">{HISTORY_TEXTS.title}</p>
            </div>
            <IconButton icon="close" shape="small" label={APP_TEXTS.close} onClick={words.closeHistory} />
          </div>
          {renderWordHistory(history)}
        </Dialog>
      )}
    </PageCard>
  );
};

export default WordsPage;
