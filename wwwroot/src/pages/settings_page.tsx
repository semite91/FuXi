import { useState } from 'react';
import Credits from '../components/credits/credits';
import DisclosureToggle from '../components/disclosure_toggle/disclosure_toggle';
import EmbeddingsUpdate from '../components/embeddings_update/embeddings_update';
import NotificationPermission from '../components/notification_permission/notification_permission';
import NotionConnect from '../components/notion_connect/notion_connect';
import PageCard from '../components/page_card/page_card';
import StatusMessage from '../components/status_message/status_message';
import {
  APP_TEXTS,
  CREDITS_TEXTS,
  NOTION_TEXTS,
  PERMISSION_TEXTS,
  REQUESTS_TEXTS,
  SETTINGS_TEXTS,
} from '../constants/texts';
import { useEmbeddingsUpdate, type EmbeddingsStep } from '../hooks/use_embeddings_update';
import { useNotificationPermission } from '../hooks/use_notification_permission';
import { useNotionConnection } from '../hooks/use_notion_connection';
import type { NotionConnection } from '../services/notion_service';
import tmdbLogo from '../image/tmdb_logo.svg';

const RESULT_TITLES: Partial<Record<EmbeddingsStep, string>> = {
  updated: SETTINGS_TEXTS.updated,
  failed: SETTINGS_TEXTS.failed,
};

const CONFIRM_STEP: EmbeddingsStep = 'confirm';

/** No text until the state is known. */
const notionStateText = (connection: NotionConnection | null): string | undefined => {
  if (connection === null) {
    return undefined;
  }

  if (!connection.isConnected) {
    return NOTION_TEXTS.notConnected;
  }

  return connection.workspaceName
    ? `${NOTION_TEXTS.connected}${NOTION_TEXTS.workspaceSeparator}${connection.workspaceName}`
    : NOTION_TEXTS.connected;
};

const SettingsPage = () => {
  const embeddings = useEmbeddingsUpdate();
  const notification = useNotificationPermission();
  const notion = useNotionConnection();
  // Not stored, so the toggle is closed every time the page opens, unless it opens back from the Notion sign-in.
  const [isRequestsOpen, setIsRequestsOpen] = useState(notion.isReturningFromSignIn);

  return (
    <PageCard title={SETTINGS_TEXTS.title}>
      <EmbeddingsUpdate
        linkLabel={SETTINGS_TEXTS.updateEmbeddings}
        aboutLabel={SETTINGS_TEXTS.about}
        tipText={SETTINGS_TEXTS.tip}
        confirmTitle={SETTINGS_TEXTS.confirm}
        confirmNotice={SETTINGS_TEXTS.syncNotice}
        confirmLabel={APP_TEXTS.yes}
        closeLabel={APP_TEXTS.closeDialog}
        resultTitle={RESULT_TITLES[embeddings.step]}
        isConfirmOpen={embeddings.step === CONFIRM_STEP}
        onAsk={embeddings.ask}
        onConfirm={() => void embeddings.update()}
        onClose={embeddings.close}
      />
      <NotificationPermission
        stateText={PERMISSION_TEXTS[notification.permission]}
        buttonLabel={PERMISSION_TEXTS.enable}
        isDisabled={!notification.canEnable}
        onEnable={() => void notification.enable()}
      />
      {notification.hasFailed && <StatusMessage kind="error" text={PERMISSION_TEXTS.failed} />}
      <DisclosureToggle
        label={REQUESTS_TEXTS.title}
        isOpen={isRequestsOpen}
        isFlush
        onToggle={() => setIsRequestsOpen((isOpen) => !isOpen)}
      >
        <NotionConnect
          connectLabel={NOTION_TEXTS.connect}
          text={NOTION_TEXTS.label}
          aboutLabel={NOTION_TEXTS.about}
          tipText={NOTION_TEXTS.tip}
          stateText={notionStateText(notion.connection)}
          errorText={notion.hasSignInFailed ? NOTION_TEXTS.failed : undefined}
          onConnect={notion.connect}
        />
      </DisclosureToggle>
      <Credits
        title={CREDITS_TEXTS.title}
        logoSource={tmdbLogo}
        logoText={CREDITS_TEXTS.tmdbLogo}
        noticeText={CREDITS_TEXTS.tmdbNotice}
      />
    </PageCard>
  );
};

export default SettingsPage;
