// Phase 6a section E: the shared toggle of the Requests and History blocks.
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import DisclosureToggle from './disclosure_toggle';

const renderToggle = (isOpen: boolean) => {
  const onToggle = vi.fn();
  render(
    <DisclosureToggle label="Requests" isOpen={isOpen} onToggle={onToggle}>
      <p>Content</p>
    </DisclosureToggle>,
  );

  return onToggle;
};

const toggle = () => screen.getByRole('button', { name: 'Requests' });

test('6a E2 a closed toggle has aria-expanded false and hides its content', () => {
  renderToggle(false);

  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('Content')).not.toBeInTheDocument();
});

test('6a E3 an open toggle has aria-expanded true and shows its content', () => {
  renderToggle(true);

  expect(toggle()).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('Content')).toBeInTheDocument();
});

test('6a E3 a click on the text or the arrow calls onToggle', () => {
  const onToggle = renderToggle(false);

  fireEvent.click(toggle());
  fireEvent.click(toggle().querySelector('svg') as Element);

  expect(onToggle).toHaveBeenCalledTimes(2);
});

test('6a E7 the down arrow turns when the toggle is open', () => {
  renderToggle(true);

  const arrow = toggle().querySelector('svg');
  expect(arrow).toHaveClass('disclosure-toggle__icon', 'disclosure-toggle__icon--open');
  expect(arrow).toHaveAttribute('aria-hidden', 'true');
});

test('6a B7 a flush toggle lines up with the rows above it; the default keeps its inset', () => {
  const { rerender } = render(
    <DisclosureToggle label="Requests" isOpen={false} onToggle={vi.fn()} isFlush>
      <p>Content</p>
    </DisclosureToggle>,
  );
  expect(toggle()).toHaveClass('disclosure-toggle__button--flush');

  rerender(
    <DisclosureToggle label="Requests" isOpen={false} onToggle={vi.fn()}>
      <p>Content</p>
    </DisclosureToggle>,
  );
  expect(toggle()).not.toHaveClass('disclosure-toggle__button--flush');
});

test('6a E11 an open toggle names its content with aria-controls, and the content has that id', () => {
  renderToggle(true);

  const id = toggle().getAttribute('aria-controls');
  expect(id).toBeTruthy();
  const content = document.getElementById(id as string);
  expect(content).toContainElement(screen.getByText('Content'));
});

test('6a E11 a closed toggle has no aria-controls, because its content is not drawn', () => {
  renderToggle(false);

  expect(toggle()).not.toHaveAttribute('aria-controls');
});

test('6a E9 the toggle keeps no state of its own; it shows what isOpen says', () => {
  const onToggle = renderToggle(false);

  fireEvent.click(toggle());

  expect(onToggle).toHaveBeenCalledTimes(1);
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
});
