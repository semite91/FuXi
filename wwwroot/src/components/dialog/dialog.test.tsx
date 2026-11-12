// Section Q: dialogs and accessible names.
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, test, vi } from 'vitest';
import { mockApi } from '../../test/api_mock';
import { CONFIGS } from '../../test/data';
import { renderApp } from '../../test/render_app';
import Dialog from './dialog';

const Opener = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)}>
        Open
      </button>
      {isOpen && (
        <Dialog label="Sample" closeLabel="Close dialog" onClose={() => setIsOpen(false)}>
          <p>Body</p>
        </Dialog>
      )}
    </>
  );
};

test('Q1 a dialog has role dialog, aria-modal and a name', () => {
  render(<Opener />);
  fireEvent.click(screen.getByRole('button', { name: 'Open' }));

  const dialog = screen.getByRole('dialog', { name: 'Sample' });
  expect(dialog).toHaveAttribute('aria-modal', 'true');
});

test('Q2 the focus moves into the dialog and returns to its opener', () => {
  render(<Opener />);
  const opener = screen.getByRole('button', { name: 'Open' });
  opener.focus();

  fireEvent.click(opener);
  expect(screen.getByRole('dialog')).toHaveFocus();

  fireEvent.keyDown(document, { key: 'Escape' });
  expect(opener).toHaveFocus();
});

test.each(['/words', '/config', '/settings', '/schedule'])('Q3 every button on %s has a name', async (path) => {
  mockApi({ 'GET /api/GetConfigs': { body: CONFIGS }, 'GET /api/GetSchedule': { body: [] } });
  renderApp(path);
  await screen.findByRole('heading', { level: 1 });

  screen.getAllByRole('button').forEach((button) => {
    expect(button).toHaveAccessibleName();
  });
});

test('a dialog takes the focus without scrolling, so a sliding panel does not shake the page', () => {
  const focus = vi.spyOn(HTMLElement.prototype, 'focus');
  render(<Opener />);

  fireEvent.click(screen.getByRole('button', { name: 'Open' }));

  expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  focus.mockRestore();
});
