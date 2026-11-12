// A fake fetch for tests. No test reaches a real API.
import { vi } from 'vitest';

export const API_URL = 'http://api.test';
export const RAG_URL = 'http://rag.test';

export interface RecordedCall {
  method: string;
  url: URL;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

export interface Answer {
  status?: number;
  body?: unknown;
}

type Handler = (call: RecordedCall) => Answer | Promise<Answer>;
type Route = Answer | Handler;

const OK_STATUS = 200;
const NOT_MOCKED_STATUS = 599;

export interface ApiMock {
  calls: RecordedCall[];
  callsTo(name: string): RecordedCall[];
  set(key: string, route: Route): void;
}

/** A promise that the test resolves by hand, for pending calls. */
export const deferred = <T = Answer>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });

  return { promise, resolve };
};

export const problem = (status: number, detail: string): Answer => ({ status, body: { status, detail } });

export const networkFailure: Handler = () => {
  throw new TypeError('Failed to fetch');
};

/** Routes are keyed by "METHOD /path", for example "GET /api/GetConfigs". */
export const mockApi = (routes: Record<string, Route> = {}): ApiMock => {
  vi.stubEnv('VITE_FUXI_API_URL', API_URL);
  vi.stubEnv('VITE_FUXI_RAG_URL', RAG_URL);

  const table = new Map(Object.entries(routes));
  const calls: RecordedCall[] = [];

  const fetchMock = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const method = init?.method ?? 'GET';
    const call: RecordedCall = {
      method,
      url,
      path: url.pathname,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
      headers: (init?.headers ?? {}) as Record<string, string>,
    };
    calls.push(call);

    const route = table.get(`${method} ${url.pathname}`);

    if (route === undefined) {
      return new Response(JSON.stringify({ detail: `No mock for ${method} ${url.pathname}` }), {
        status: NOT_MOCKED_STATUS,
      });
    }

    const answer = typeof route === 'function' ? await route(call) : route;
    const status = answer.status ?? OK_STATUS;
    const hasBody = answer.body !== undefined && status !== 204;

    return new Response(hasBody ? JSON.stringify(answer.body) : null, { status });
  };

  vi.stubGlobal('fetch', vi.fn(fetchMock));

  return {
    calls,
    callsTo: (name) => calls.filter((call) => call.path.endsWith(`/${name}`)),
    set: (key, route) => {
      table.set(key, route);
    },
  };
};
