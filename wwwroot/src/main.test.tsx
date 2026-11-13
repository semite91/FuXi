// Phase 5a section I: the RAG engine is started when the app opens.
import { act, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { mockApi, problem } from './test/api_mock';

test('5a I2 opening the app calls POST /Init_RAG once and its failure shows no error', async () => {
  const api = mockApi({
    'POST /Init_RAG': problem(500, 'The engine failed.'),
    'GET /api/GetWordsByFilter': { body: [] },
  });
  const root = document.createElement('div');
  root.id = 'root';
  document.body.append(root);

  // main.tsx renders in StrictMode, which mounts every component twice.
  await act(async () => {
    await import('./main');
  });

  expect(await screen.findByRole('heading', { level: 1, name: 'Words' })).toBeInTheDocument();
  await expect.poll(() => api.callsTo('Init_RAG')).toHaveLength(1);
  expect(api.callsTo('Init_RAG')[0].method).toBe('POST');
  expect(screen.queryByText('The engine failed.')).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
