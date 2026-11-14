// Phase 5a section I: the RAG engine contract.
import { expect, test } from 'vitest';
import { mockApi, networkFailure } from '../test/api_mock';
import { getWordContent, initRag, startRag } from './rag_service';

const WORDS = [
  { name: 'Ephemeral', translation: 'geçici' },
  { name: 'Serendipity', translation: 'mutlu tesadüf' },
];

test('5a I1 GetWordContent is a POST with every Word and its translation', async () => {
  const content = [{ name: 'Ephemeral', translation: 'geçici', content: '{"method":"photo","image_url":"https://i.test/a.jpg"}' }];
  const api = mockApi({ 'POST /GetWordContent': { body: content } });

  await expect(getWordContent(WORDS)).resolves.toEqual(content);

  expect(api.calls).toHaveLength(1);
  expect(api.calls[0].body).toEqual({ words: WORDS });
});

test.each([
  [200, 'ready'],
  [202, 'building'],
  [200, 'empty'],
])('5a I2 Init_RAG is a POST that reads %s as "%s"', async (status, state) => {
  const api = mockApi({ 'POST /Init_RAG': { status, body: { status: state } } });

  await expect(initRag()).resolves.toEqual({ status: state });

  expect(api.calls[0].method).toBe('POST');
  expect(api.calls[0].path).toBe('/Init_RAG');
});

test.each([
  ['a network failure', networkFailure],
  ['a 503', { status: 503 }],
])('5a I2 startRag calls Init_RAG once and swallows %s', async (_, route) => {
  const api = mockApi({ 'POST /Init_RAG': route });

  expect(() => startRag()).not.toThrow();

  await expect.poll(() => api.callsTo('Init_RAG')).toHaveLength(1);
});

test('5b I4 GetWordContent passes a Drive photo content string through unchanged', async () => {
  const DRIVE_PHOTO = '{"method":"photo","image_url":"data:image/jpeg;base64,/9j/4AAQSkZJRg=="}';
  const content = [{ name: 'Ephemeral', translation: 'geçici', content: DRIVE_PHOTO }];
  mockApi({ 'POST /GetWordContent': { body: content } });

  await expect(getWordContent(WORDS)).resolves.toEqual(content);
});
