// One source of the Requests toggle (Notion, Google Drive): its connection state, read once when the page opens,
// and the result of a sign-in the API sent the browser back from, as /settings?<parameter>=connected|failed.
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { announceConnection, listenForConnection } from '../services/connection_channel';
import { closeThisTab } from '../services/page_location';

const FAILED_RESULT = 'failed';
const CONNECTED_RESULT = 'connected';

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
  const [returnedResult] = useState(() => searchParams.get(resultParameter));
  // The tab that opened the sign-in learns its result from the tab the sign-in ended in.
  const [announcedResult, setAnnouncedResult] = useState<string | null>(null);
  const signInResult = returnedResult ?? announcedResult;
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

  // The options come from module constants; the state is read when the page opens and again when a sign-in ends.
  useEffect(() => {
    let isCurrent = true;

    const read = () =>
      load()
        .catch((): T => notConnected)
        .then((loaded) => {
          if (isCurrent) {
            setConnection(loaded);
          }
        });

    void read();

    const stopListening = listenForConnection((message) => {
      if (message.parameter === resultParameter) {
        setAnnouncedResult(message.result);
        void read();
      }
    });

    return () => {
      isCurrent = false;
      stopListening();
    };
  }, []);

  // The sign-in tab hands its result to the tab that opened it; after a success it closes itself, when the browser allows it.
  useEffect(() => {
    if (returnedResult !== null) {
      announceConnection({ parameter: resultParameter, result: returnedResult });

      if (returnedResult === CONNECTED_RESULT) {
        closeThisTab();
      }
    }
  }, []);

  return {
    connection,
    setConnection,
    isReturningFromSignIn: returnedResult !== null,
    hasSignInFailed: signInResult === FAILED_RESULT,
  };
};
