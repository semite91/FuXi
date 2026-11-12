// Section B: routes and navigation.
import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, expect, test } from 'vitest';
import { MENU_TEXTS } from './constants/texts';
import { mockApi } from './test/api_mock';
import { CONFIGS, TWO_CARDS } from './test/data';
import { LOCATION_TEST_ID, renderApp } from './test/render_app';

beforeEach(() => {
  mockApi({
    'GET /api/GetWordsByActive': { body: TWO_CARDS },
    'GET /api/GetCardWords': { body: TWO_CARDS },
    'GET /api/GetConfigs': { body: CONFIGS },
    'GET /api/GetSchedule': { body: [] },
  });
});

const location = () => screen.getByTestId(LOCATION_TEST_ID).textContent;
const heading = (name: string) => screen.findByRole('heading', { level: 1, name });
const openMenu = () => fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));

test('B1 "/" opens the Words page at /words', async () => {
  renderApp('/');

  expect(await heading('Words')).toBeInTheDocument();
  expect(location()).toBe('/words');
});

test('B2 /flashcard shows the carousel', async () => {
  renderApp('/flashcard?wordIds=a');

  expect(await screen.findByText('Do you know this word?')).toBeInTheDocument();
});

test('B3 /active shows the carousel with the Due Words', async () => {
  renderApp('/active');

  expect(await heading('Ephemeral')).toBeInTheDocument();
});

test.each([
  ['B4', '/schedule', 'Schedule'],
  ['B5', '/config', 'Configs'],
  ['B6', '/settings', 'Settings'],
])('%s %s shows the %s page', async (_, path, title) => {
  renderApp(path);

  expect(await heading(title)).toBeInTheDocument();
});

test('B7 an unknown path opens the Words page at /words', async () => {
  renderApp('/nothing-here');

  expect(await heading('Words')).toBeInTheDocument();
  expect(location()).toBe('/words');
});

test('B8 every page shows the logo and the menu button', () => {
  renderApp('/words');

  expect(screen.getByRole('img', { name: 'FuXi' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open menu' })).toBeInTheDocument();
});

test('B9 the menu lists its five items in order', () => {
  renderApp('/words');
  openMenu();

  const items = within(screen.getByRole('menu')).getAllByRole('menuitem').map((item) => item.textContent);
  expect(items).toEqual(['Active Words', 'Words', 'Schedule', 'Configs', 'Settings']);
});

test('B10 aria-expanded follows the menu', () => {
  renderApp('/words');
  const button = screen.getByRole('button', { name: 'Open menu' });

  expect(button).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(button);
  expect(button).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(button);
  expect(button).toHaveAttribute('aria-expanded', 'false');
});

test.each([
  ['B11', MENU_TEXTS.active, '/active'],
  ['B12', MENU_TEXTS.words, '/words'],
  ['B13', MENU_TEXTS.schedule, '/schedule'],
  ['B14', MENU_TEXTS.config, '/config'],
  ['B15', MENU_TEXTS.settings, '/settings'],
])('%s "%s" opens %s and B16 closes the menu', (_, item, path) => {
  renderApp('/settings');
  openMenu();

  fireEvent.click(screen.getByRole('menuitem', { name: item }));

  expect(location()).toBe(path);
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});

test('B17 Escape closes the menu', () => {
  renderApp('/settings');
  openMenu();

  fireEvent.keyDown(document, { key: 'Escape' });

  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});

test('B17 a click outside the menu closes it', () => {
  renderApp('/settings');
  openMenu();

  fireEvent.mouseDown(screen.getByRole('heading', { name: 'Settings' }));

  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});
