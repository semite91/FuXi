// The Notion row of the Settings page: the connection state, read once when the page opens.
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { connectNotion, getNotionConnection, type NotionConnection } from '../services/notion_service';

const NOT_CONNECTED: NotionConnection = { isConnected: false, workspaceName: null };
// The API sends the browser back to /settings?notion=connected|failed after the sign-in.
const RESULT_PARAMETER = 'notion';
const FAILED_RESULT = 'failed';

export const useNotionConnection = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  // Read once, so the page keeps the result after the address is cleaned.
  const [signInResult] = useState(() => searchParams.get(RESULT_PARAMETER));
  const [connection, setConnection] = useState<NotionConnection | null>(null);

  // The result is removed from the address without a reload, so a refresh or a bookmark does not show it again.
  useEffect(() => {
    if (searchParams.has(RESULT_PARAMETER)) {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete(RESULT_PARAMETER);
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    let isCurrent = true;

    getNotionConnection()
      // A failed read shows "Not connected"; the button still starts the sign-in.
      .catch((): NotionConnection => NOT_CONNECTED)
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
    isReturningFromSignIn: signInResult !== null,
    hasSignInFailed: signInResult === FAILED_RESULT,
    connect: connectNotion,
  };
};
