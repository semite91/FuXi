import { Icon } from '../../image/icons';
import IconButton from '../icon_button/icon_button';
import './schedule_toolbar.less';

const NEW_ICON_SIZE = 16;
const NEW_ICON_STROKE = 2.5;

export interface ViewOption<View extends string> {
  view: View;
  label: string;
}

interface ScheduleToolbarProps<View extends string> {
  newEntryLabel: string;
  viewGroupLabel: string;
  views: readonly ViewOption<View>[];
  activeView: View;
  previousLabel: string;
  nextLabel: string;
  todayLabel: string;
  rangeLabel: string;
  onNewEntry: () => void;
  onView: (view: View) => void;
  onPrevious: () => void;
  onNext: () => void;
  onToday: () => void;
}

const ScheduleToolbar = <View extends string>({
  newEntryLabel,
  viewGroupLabel,
  views,
  activeView,
  previousLabel,
  nextLabel,
  todayLabel,
  rangeLabel,
  onNewEntry,
  onView,
  onPrevious,
  onNext,
  onToday,
}: ScheduleToolbarProps<View>) => (
  <div className="schedule-toolbar">
    <div className="schedule-toolbar__row">
      <button type="button" className="schedule-toolbar__new" onClick={onNewEntry}>
        <Icon name="plus" size={NEW_ICON_SIZE} strokeWidth={NEW_ICON_STROKE} />
        {newEntryLabel}
      </button>
      <div className="schedule-toolbar__views" role="group" aria-label={viewGroupLabel}>
        {views.map((option) => (
          <button
            key={option.view}
            type="button"
            className="schedule-toolbar__view"
            aria-pressed={option.view === activeView}
            onClick={() => onView(option.view)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
    <div className="schedule-toolbar__row">
      <IconButton icon="previous" shape="small" label={previousLabel} onClick={onPrevious} />
      <IconButton icon="next" shape="small" label={nextLabel} onClick={onNext} />
      <p className="schedule-toolbar__label" aria-live="polite">
        {rangeLabel}
      </p>
      <button type="button" className="schedule-toolbar__today" onClick={onToday}>
        {todayLabel}
      </button>
    </div>
  </div>
);

export default ScheduleToolbar;
