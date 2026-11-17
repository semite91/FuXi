// Phase 6a E10: a StatusMessage can be a plain note, without a status or live region role.
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import StatusMessage from './status_message';

test('6a E10 by default a note is announced as a status', () => {
  render(<StatusMessage text="Loading" />);

  expect(screen.getByRole('status')).toHaveTextContent('Loading');
});

test('6a E10 an error is still an alert', () => {
  render(<StatusMessage kind="error" text="Failed" />);

  expect(screen.getByRole('alert')).toHaveTextContent('Failed');
});

test('6a E10 an error stays an alert even when isAnnounced is false', () => {
  render(<StatusMessage kind="error" text="Failed" isAnnounced={false} />);

  expect(screen.getByRole('alert')).toHaveTextContent('Failed');
});

test('6a E10 a message that is not announced has no role and the same note style', () => {
  render(<StatusMessage text="No requests yet." isAnnounced={false} />);

  const note = screen.getByText('No requests yet.');
  expect(note).not.toHaveAttribute('role');
  expect(note).not.toHaveAttribute('aria-live');
  expect(note).toHaveClass('status-message', 'status-message--note');
});
