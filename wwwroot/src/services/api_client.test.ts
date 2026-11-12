import { expect, test, vi } from 'vitest';
import { API_URL, RAG_URL, mockApi, networkFailure, problem } from '../test/api_mock';
import { ApiError, API_URL_KEY, UNREACHABLE_MESSAGE, createApiClient, errorMessageOf } from './api_client';
import { getConfigs } from './config_service';
import { getWordContent } from './rag_service';
import { getWordsByFilter, updateWordContent } from './words_service';

const WORD_ID = '7b0e4a0c-5a51-4c0b-9a55-0f2f6d2a1c11';

test('A6 a missing API URL raises an error that names the key', async () => {
  mockApi();
  vi.stubEnv(API_URL_KEY, '');

  await expect(getConfigs()).rejects.toThrow(API_URL_KEY);
});

test('C1 a .NET API call starts with the API URL and uses /api/<Name>', async () => {
  const api = mockApi({ 'GET /api/GetConfigs': { body: [] } });

  await getConfigs();

  expect(api.calls[0].url.href).toBe(`${API_URL}/api/GetConfigs`);
});

test('C2 a RAG API call starts with the RAG URL', async () => {
  const api = mockApi({ 'GET /GetWordContent': { body: [] } });

  await getWordContent(['run']);

  expect(api.calls[0].url.origin).toBe(RAG_URL);
});

test('C3 a POST call sends camelCase JSON with the JSON content type', async () => {
  const api = mockApi({ 'POST /api/UpdateWordContent': { status: 204 } });

  await updateWordContent(WORD_ID, 'a story');

  expect(api.calls[0].body).toEqual({ id: WORD_ID, content: 'a story' });
  expect(api.calls[0].headers['Content-Type']).toBe('application/json');
});

test('C4 a 204 answer returns without parsing a body', async () => {
  mockApi({ 'POST /api/UpdateWordContent': { status: 204 } });

  await expect(updateWordContent(WORD_ID, 'a story')).resolves.toBeUndefined();
});

test('C5 a ProblemDetails answer raises an error with the status and the detail', async () => {
  mockApi({ 'GET /api/GetConfigs': problem(400, 'The value is not a number.') });

  const error = await getConfigs().catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).status).toBe(400);
  expect((error as ApiError).message).toBe('The value is not a number.');
});

test('C6 a network failure raises an error that says the API cannot be reached', async () => {
  mockApi({ 'GET /api/GetConfigs': networkFailure });

  const error = await getConfigs().catch((caught: unknown) => caught);

  expect((error as ApiError).status).toBeNull();
  expect((error as ApiError).message).toBe(UNREACHABLE_MESSAGE);
});

test('C7 a query value with special characters is URL-encoded', async () => {
  const api = mockApi({ 'GET /api/GetWordsByFilter': { body: [] } });

  await getWordsByFilter({ name: '100% & more' });

  expect(api.calls[0].url.search).toBe('?name=100%25+%26+more');
  expect(api.calls[0].url.searchParams.get('name')).toBe('100% & more');
});

test('a trailing slash of the base URL is not doubled', async () => {
  const api = mockApi({ 'GET /api/GetConfigs': { body: [] } });
  vi.stubEnv(API_URL_KEY, `${API_URL}/`);

  await createApiClient(API_URL_KEY).get('/api/GetConfigs');

  expect(api.calls[0].url.href).toBe(`${API_URL}/api/GetConfigs`);
});

test('review: a missing API URL is shown with its key, not as a generic failure', async () => {
  mockApi();
  vi.stubEnv(API_URL_KEY, '');

  const error = await getConfigs().catch((caught: unknown) => caught);

  expect(errorMessageOf(error)).toBe(`Configuration value ${API_URL_KEY} is missing.`);
});

test('review: a success answer that is not JSON is a failed request', async () => {
  mockApi({ 'GET /api/GetConfigs': () => ({ status: 200, body: undefined }) });
  vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>', { status: 200 })));

  await expect(getConfigs()).rejects.toBeInstanceOf(ApiError);
});
