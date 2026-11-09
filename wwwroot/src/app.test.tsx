import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import App from './app';

afterEach(cleanup);

test('root shell renders', () => {
  render(<App />);

  expect(screen.getByRole('main')).toBeInTheDocument();
});
