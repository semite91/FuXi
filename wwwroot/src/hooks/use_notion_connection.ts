// The Notion row of the Settings page.
import { connectNotion, getNotionConnection, type NotionConnection } from '../services/notion_service';
import { useSourceConnection } from './use_source_connection';

const NOT_CONNECTED: NotionConnection = { isConnected: false, workspaceName: null };
// The API sends the browser back to /settings?notion=connected|failed after the sign-in.
const RESULT_PARAMETER = 'notion';

export const useNotionConnection = () => {
  const { connection, isReturningFromSignIn, hasSignInFailed } = useSourceConnection({
    resultParameter: RESULT_PARAMETER,
    load: getNotionConnection,
    notConnected: NOT_CONNECTED,
  });

  return { connection, isReturningFromSignIn, hasSignInFailed, connect: connectNotion };
};
