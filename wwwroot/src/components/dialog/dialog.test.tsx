// Section Q: dialogs and accessible names.
import { fireEvent, render, screen, within } from '@testing-library/react';
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

// Phase 6a section C: the close (X) button of every dialog.
const renderDialog = () => {
  const onClose = vi.fn();
  const view = render(
    <Dialog label="Sample" closeLabel="Close" onClose={onClose}>
      <button type="button">Inside</button>
    </Dialog>,
  );

  return { onClose, view };
};

const FOCUSABLE = 'button:not([tabindex="-1"]), input, select, textarea, a[href]';

test('6a C11 the header row holds the title and the X, and the X is the first control in the focus order', () => {
  renderDialog();

  const dialog = screen.getByRole('dialog', { name: 'Sample' });
  const header = dialog.querySelector('.dialog__header');
  expect(header).not.toBeNull();
  const title = within(dialog).getByRole('heading', { level: 2, name: 'Sample' });
  const close = within(dialog).getByRole('button', { name: 'Close' });
  expect(header).toContainElement(title);
  expect(header).toContainElement(close);
  expect(dialog.querySelector(FOCUSABLE)).toBe(close);
});

test('6a C12 the content is in the body under the header, which is the part that scrolls', () => {
  renderDialog();

  const body = screen.getByRole('dialog').querySelector('.dialog__body');
  expect(body).toContainElement(screen.getByRole('button', { name: 'Inside' }));
  expect(body).not.toContainElement(screen.getByRole('heading', { name: 'Sample' }));
});

test('6a C11 a subtitle is shown under the title and an icon above it', () => {
  render(
    <Dialog label="banana" subtitle="History" icon={<span data-testid="icon" />} closeLabel="Close" onClose={vi.fn()}>
      <p>Body</p>
    </Dialog>,
  );

  const title = screen.getByRole('heading', { name: 'banana' });
  const subtitle = screen.getByText('History');
  expect(screen.getByTestId('icon').compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(title.compareDocumentPosition(subtitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole('dialog')).toHaveAccessibleName('banana');
});

test('6a C11 a title can be a status, and the dialog keeps it as its name', () => {
  render(
    <Dialog label="Embeddings updated" isTitleStatus isTitleCentered closeLabel="Close" onClose={vi.fn()}>
      <p>Body</p>
    </Dialog>,
  );

  expect(screen.getByRole('status')).toHaveTextContent('Embeddings updated');
  expect(screen.getByRole('dialog')).toHaveAccessibleName('Embeddings updated');
  expect(screen.getByRole('dialog').querySelector('.dialog__header')).toHaveClass('dialog__header--center');
});

test.each([
  ['none', undefined],
  ['null', null],
  ['false', false],
])('6a C14 a dialog with %s as its content draws no body under the header', (_, content) => {
  render(
    <Dialog label="Embeddings updated" closeLabel="Close" onClose={vi.fn()}>
      {content}
    </Dialog>,
  );

  expect(screen.getByRole('dialog').querySelector('.dialog__body')).toBeNull();
});

test('6a C14 a dialog whose children are only empty conditionals draws no body under the header', () => {
  const isShown = false;
  const missing: string | null = null;
  render(
    <Dialog label="Embeddings updated" closeLabel="Close" onClose={vi.fn()}>
      {isShown && <p>Hidden</p>}
      {missing}
      {[false, null, undefined]}
    </Dialog>,
  );

  expect(screen.getByRole('dialog').querySelector('.dialog__body')).toBeNull();
});

test('6a C14 a dialog with one shown child among empty ones draws its body', () => {
  render(
    <Dialog label="Sample" closeLabel="Close" onClose={vi.fn()}>
      {false}
      <p>Shown</p>
    </Dialog>,
  );

  expect(screen.getByRole('dialog').querySelector('.dialog__body')).toContainElement(screen.getByText('Shown'));
});

test('6a C3 the backdrop is a plain element, hidden from screen readers and not focusable', () => {
  const { view } = renderDialog();

  const backdrop = view.container.querySelector('.dialog__backdrop');
  expect(backdrop?.tagName).toBe('DIV');
  expect(backdrop).toHaveAttribute('aria-hidden', 'true');
  expect(backdrop).not.toHaveAttribute('tabindex');
});

test('6a C1 an open dialog has a close icon button named by closeLabel inside its box', () => {
  renderDialog();

  const dialog = screen.getByRole('dialog', { name: 'Sample' });
  const close = within(dialog).getByRole('button', { name: 'Close' });
  expect(close).toHaveClass('dialog__close');
  expect(close.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
});

test('6a C2 a click on the close button calls onClose once', () => {
  const { onClose } = renderDialog();

  fireEvent.click(screen.getByRole('button', { name: 'Close' }));

  expect(onClose).toHaveBeenCalledTimes(1);
});

test('6a C3 Escape and the backdrop still call onClose', () => {
  const { onClose, view } = renderDialog();

  fireEvent.keyDown(document, { key: 'Escape' });
  const backdrop = view.container.querySelector('.dialog__backdrop');
  expect(backdrop).not.toBeNull();
  fireEvent.click(backdrop as Element);

  expect(onClose).toHaveBeenCalledTimes(2);
});

test('6a C3 the backdrop is hidden from screen readers, so the dialog has one close button', () => {
  renderDialog();

  expect(screen.getAllByRole('button', { name: 'Close' })).toHaveLength(1);
});

test('6a C4 the close button is in the Tab order', () => {
  renderDialog();

  const close = screen.getByRole('button', { name: 'Close' });
  expect(close).not.toHaveAttribute('tabindex');
  expect(close.tabIndex).toBe(0);
  close.focus();
  expect(close).toHaveFocus();
});

test('a dialog takes the focus without scrolling, so a sliding panel does not shake the page', () => {
  const focus = vi.spyOn(HTMLElement.prototype, 'focus');
  render(<Opener />);

  fireEvent.click(screen.getByRole('button', { name: 'Open' }));

  expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  focus.mockRestore();
});
