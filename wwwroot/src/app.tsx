import { Navigate, Route, Routes, useNavigate } from 'react-router';
import AppHeader from './components/app_header/app_header';
import { ROUTES } from './constants/routes';
import { APP_TEXTS, MENU_TEXTS } from './constants/texts';
import logo from './image/fuxi_logo.png';
import ConfigPage from './pages/config_page';
import FlashcardPage from './pages/flashcard_page';
import SchedulePage from './pages/schedule_page';
import SettingsPage from './pages/settings_page';
import WordsPage from './pages/words_page';

const MENU_ITEMS = [
  { label: MENU_TEXTS.active, path: ROUTES.active },
  { label: MENU_TEXTS.words, path: ROUTES.words },
  { label: MENU_TEXTS.schedule, path: ROUTES.schedule },
  { label: MENU_TEXTS.config, path: ROUTES.config },
  { label: MENU_TEXTS.settings, path: ROUTES.settings },
] as const;

const ACTIVE_KEY = 'active';
const FLASHCARD_KEY = 'flashcard';

/** The header and the routes. The router itself is added by main.tsx, or by a test. */
const App = () => {
  const navigate = useNavigate();

  return (
    <div className="app">
      <AppHeader
        logoSource={logo}
        logoText={APP_TEXTS.name}
        menuLabel={APP_TEXTS.openMenu}
        items={MENU_ITEMS}
        onNavigate={(path) => void navigate(path)}
      />
      <main className="app__content">
        <Routes>
          <Route path={ROUTES.words} element={<WordsPage />} />
          <Route path={ROUTES.flashcard} element={<FlashcardPage key={FLASHCARD_KEY} usesWordIds />} />
          <Route path={ROUTES.active} element={<FlashcardPage key={ACTIVE_KEY} usesWordIds={false} />} />
          <Route path={ROUTES.schedule} element={<SchedulePage />} />
          <Route path={ROUTES.config} element={<ConfigPage />} />
          <Route path={ROUTES.settings} element={<SettingsPage />} />
          <Route path={ROUTES.unknown} element={<Navigate to={ROUTES.words} replace />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;
