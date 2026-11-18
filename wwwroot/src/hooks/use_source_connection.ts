// One source of the Requests toggle (Notion, Google Drive): its connection state, read once when the page opens,
// and the result of a sign-in the API sent the browser back from, as /settings?<parameter>=connected|failed.
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';

const FAILED_RESULT = 'failed';

interface SourceConnectionOptions<T> {
  /** The address parameter the API sets after this source's sign-in, for example "notion". */
  resultParameter: string;
  load: () => Promise<T>;
  /** Shown when the state cannot be read; the button still starts the sign-in. */
  notConnected: T;
}

export const useSourceConnection = <T>({ resultParameter, load, notConnected }: SourceConnectionOptions<T>) => {
  const [searchParams, setSearchParams] = useSearchParams();
  // Read once, so the page keeps the result after the address is cleaned.
  const [signInResult] = useState(() => searchParams.get(resultParameter));
  // Null until the state is known, so a connected source never reads "Not connected" first.
  const [connection, setConnection] = useState<T | null>(null);

  // The result is removed from the address without a reload, so a refresh or a bookmark does not show it again.
  useEffect(() => {
    if (searchParams.has(resultParameter)) {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete(resultParameter);
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams, resultParameter]);

  // The options come from module constants; the state is read once when the page opens.
  useEffect(() => {
    let isCurrent = true;

    load()
      .catch((): T => notConnected)
      .then((loaded) => {
        if (isCurrent) {
          setConnection(loaded);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  return {
    connection,
    setConnection,
    isReturningFromSignIn: signInResult !== null,
    hasSignInFailed: signInResult === FAILED_RESULT,
  };
};
