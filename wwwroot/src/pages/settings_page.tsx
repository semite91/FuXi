import EmbeddingsUpdate from '../components/embeddings_update/embeddings_update';
import NotificationPermission from '../components/notification_permission/notification_permission';
import PageCard from '../components/page_card/page_card';
import StatusMessage from '../components/status_message/status_message';
import { APP_TEXTS, PERMISSION_TEXTS, SETTINGS_TEXTS } from '../constants/texts';
import { useEmbeddingsUpdate, type EmbeddingsStep } from '../hooks/use_embeddings_update';
import { useNotificationPermission } from '../hooks/use_notification_permission';

const RESULT_TITLES: Partial<Record<EmbeddingsStep, string>> = {
  updated: SETTINGS_TEXTS.updated,
  failed: SETTINGS_TEXTS.failed,
};

const CONFIRM_STEP: EmbeddingsStep = 'confirm';

const SettingsPage = () => {
  const embeddings = useEmbeddingsUpdate();
  const notification = useNotificationPermission();

  return (
    <PageCard title={SETTINGS_TEXTS.title}>
      <EmbeddingsUpdate
        linkLabel={SETTINGS_TEXTS.updateEmbeddings}
        aboutLabel={SETTINGS_TEXTS.about}
        tipText={SETTINGS_TEXTS.tip}
        confirmTitle={SETTINGS_TEXTS.confirm}
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
    </PageCard>
  );
};

export default SettingsPage;
