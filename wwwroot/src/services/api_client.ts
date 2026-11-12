// The only place that calls fetch. Each service builds its client from one base URL key.

export const API_URL_KEY = 'VITE_FUXI_API_URL';
export const RAG_URL_KEY = 'VITE_FUXI_RAG_URL';
export const UNREACHABLE_MESSAGE = 'The API cannot be reached.';
export const FAILED_MESSAGE = 'The request failed.';

const JSON_CONTENT_TYPE = 'application/json';
const METHOD_GET = 'GET';
const METHOD_POST = 'POST';
const METHOD_DELETE = 'DELETE';
const NO_CONTENT_STATUS = 204;
const TRAILING_SLASHES = /\/+$/;

export type QueryValue = string | readonly string[] | undefined;
export type Query = Readonly<Record<string, QueryValue>>;

/** An API answer that is not a success. Status is null when the API was not reached. */
export class ApiError extends Error {
  readonly status: number | null;

  constructor(status: number | null, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export interface ApiClient {
  get<T>(path: string, query?: Query): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  remove(path: string, query?: Query): Promise<void>;
}

const requireBaseUrl = (key: string): string => {
  const value: unknown = import.meta.env[key];

  if (typeof value !== 'string' || value.trim() === '') {
    // Status null: the API was not reached.
    throw new ApiError(null, `Configuration value ${key} is missing.`);
  }

  return value.trim().replace(TRAILING_SLASHES, '');
};

const buildUrl = (baseUrl: string, path: string, query?: Query): string => {
  const parameters = new URLSearchParams();

  Object.entries(query ?? {}).forEach(([name, value]) => {
    if (value === undefined) {
      return;
    }

    const values = typeof value === 'string' ? [value] : value;
    values.forEach((item) => parameters.append(name, item));
  });

  const queryText = parameters.toString();

  return queryText === '' ? `${baseUrl}${path}` : `${baseUrl}${path}?${queryText}`;
};

const readErrorMessage = async (response: Response): Promise<string> => {
  try {
    const problem: unknown = await response.json();

    if (typeof problem === 'object' && problem !== null) {
      const { detail, title } = problem as { detail?: unknown; title?: unknown };

      if (typeof detail === 'string' && detail !== '') {
        return detail;
      }

      if (typeof title === 'string' && title !== '') {
        return title;
      }
    }
  } catch {
    // The answer has no JSON body.
  }

  return FAILED_MESSAGE;
};

const send = async <T>(url: string, init: RequestInit): Promise<T> => {
  let response: Response;

  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError(null, UNREACHABLE_MESSAGE);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  if (response.status === NO_CONTENT_STATUS) {
    return undefined as T;
  }

  const text = await response.text();

  try {
    return (text === '' ? undefined : JSON.parse(text)) as T;
  } catch {
    throw new ApiError(response.status, FAILED_MESSAGE);
  }
};

/** The base URL is read on each call, so a missing key rejects the call that needs it. */
export const createApiClient = (baseUrlKey: string): ApiClient => ({
  get: async (path, query) => send(buildUrl(requireBaseUrl(baseUrlKey), path, query), { method: METHOD_GET }),
  post: async (path, body) =>
    send(buildUrl(requireBaseUrl(baseUrlKey), path), {
      method: METHOD_POST,
      headers: { 'Content-Type': JSON_CONTENT_TYPE },
      body: JSON.stringify(body ?? {}),
    }),
  remove: async (path, query) => send(buildUrl(requireBaseUrl(baseUrlKey), path, query), { method: METHOD_DELETE }),
});

/** The text to show for a failed call. */
export const errorMessageOf = (error: unknown): string =>
  error instanceof ApiError ? error.message : FAILED_MESSAGE;
