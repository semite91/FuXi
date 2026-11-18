import { useState } from 'react';
import Credits from '../components/credits/credits';
import DisclosureToggle from '../components/disclosure_toggle/disclosure_toggle';
import EmbeddingsUpdate from '../components/embeddings_update/embeddings_update';
import LinkDialog from '../components/link_dialog/link_dialog';
import NotificationPermission from '../components/notification_permission/notification_permission';
import PageCard from '../components/page_card/page_card';
import RequestRow from '../components/request_row/request_row';
import StatusMessage from '../components/status_message/status_message';
import UploadGuideDialog, { type UploadGuideStep } from '../components/upload_guide_dialog/upload_guide_dialog';
import {
  APP_TEXTS,
  CONNECTION_TEXTS,
  CREDITS_TEXTS,
  GOOGLE_DRIVE_TEXTS,
  LETTERBOXD_TEXTS,
  NOTION_TEXTS,
  PERMISSION_TEXTS,
  REQUESTS_TEXTS,
  SETTINGS_TEXTS,
  SPOTIFY_TEXTS,
} from '../constants/texts';
import { useEmbeddingsUpdate, type EmbeddingsStep } from '../hooks/use_embeddings_update';
import { useGoogleDriveConnection } from '../hooks/use_google_drive_connection';
import { useLetterboxdLikes, type UploadError } from '../hooks/use_letterboxd_likes';
import type { LinkSaveError } from '../hooks/use_link_choice';
import { useNotificationPermission } from '../hooks/use_notification_permission';
import { useNotionConnection } from '../hooks/use_notion_connection';
import { useSpotifyConnection } from '../hooks/use_spotify_connection';
import { folderAddress } from '../services/google_drive_service';
import type { LetterboxdLikes } from '../services/letterboxd_service';
import { playlistAddress } from '../services/spotify_service';
import { GoogleDriveLogo, LetterboxdLogo, NotionLogo, SpotifyLogo } from '../image/icons';
import exportStepOne from '../image/letterboxd_export_step_1.svg';
import exportStepTwo from '../image/letterboxd_export_step_2.svg';
import exportStepThree from '../image/letterboxd_export_step_3.svg';
import tmdbLogo from '../image/tmdb_logo.svg';

const RESULT_TITLES: Partial<Record<EmbeddingsStep, string>> = {
  updated: SETTINGS_TEXTS.updated,
  failed: SETTINGS_TEXTS.failed,
};

const CONFIRM_STEP: EmbeddingsStep = 'confirm';
const NEW_TAB = '_blank';
const NEW_TAB_REL = 'noopener noreferrer';

const FOLDER_SAVE_ERRORS: Record<LinkSaveError, string> = {
  notALink: GOOGLE_DRIVE_TEXTS.notAFolderLink,
  notReadable: GOOGLE_DRIVE_TEXTS.saveFailed,
  failed: GOOGLE_DRIVE_TEXTS.saveFailed,
};

const PLAYLIST_SAVE_ERRORS: Record<LinkSaveError, string> = {
  notALink: SPOTIFY_TEXTS.notAPlaylistLink,
  notReadable: SPOTIFY_TEXTS.playlistNotReadable,
  failed: SPOTIFY_TEXTS.saveFailed,
};

const UPLOAD_ERRORS: Record<UploadError, string> = {
  notALikesFile: LETTERBOXD_TEXTS.notALikesFile,
  failed: LETTERBOXD_TEXTS.uploadFailed,
};

// The export guide: the three places of Letterboxd's data export, each with its screenshot.
const EXPORT_STEPS: readonly UploadGuideStep[] = [
  { image: exportStepOne, imageAlt: LETTERBOXD_TEXTS.settingsStepAlt, caption: LETTERBOXD_TEXTS.settingsStepCaption },
  { image: exportStepTwo, imageAlt: LETTERBOXD_TEXTS.dataStepAlt, caption: LETTERBOXD_TEXTS.dataStepCaption },
  { image: exportStepThree, imageAlt: LETTERBOXD_TEXTS.exportStepAlt, caption: LETTERBOXD_TEXTS.exportStepCaption },
];

/** No text until the state is known; "Uploaded: <N> movies" once a file is saved. */
const likesStateText = (likes: LetterboxdLikes | null) => {
  if (likes === null) {
    return undefined;
  }

  if (!likes.hasUpload) {
    return LETTERBOXD_TEXTS.noFile;
  }

  const movies = likes.movieCount === 1 ? LETTERBOXD_TEXTS.movieOne : LETTERBOXD_TEXTS.movieMany;

  return `${LETTERBOXD_TEXTS.uploaded}${CONNECTION_TEXTS.nameSeparator}${likes.movieCount} ${movies}`;
};

/** No text until the state is known; "Connected: <name>" when the source gave a name. */
const connectionStateText = (connection: { isConnected: boolean } | null, name: string | null | undefined) => {
  if (connection === null) {
    return undefined;
  }

  if (!connection.isConnected) {
    return CONNECTION_TEXTS.notConnected;
  }

  return name ? `${CONNECTION_TEXTS.connected}${CONNECTION_TEXTS.nameSeparator}${name}` : CONNECTION_TEXTS.connected;
};

const SettingsPage = () => {
  const embeddings = useEmbeddingsUpdate();
  const notification = useNotificationPermission();
  const notion = useNotionConnection();
  const drive = useGoogleDriveConnection();
  const letterboxd = useLetterboxdLikes();
  const spotify = useSpotifyConnection();
  // Not stored, so the toggle is closed every time the page opens, unless it opens back from a sign-in.
  const [isRequestsOpen, setIsRequestsOpen] = useState(
    notion.isReturningFromSignIn || drive.isReturningFromSignIn || spotify.isReturningFromSignIn,
  );
  const folderId = drive.connection?.folderId ?? null;
  const playlistId = spotify.connection?.playlistId ?? null;

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
        <RequestRow
          logo={<NotionLogo />}
          connectLabel={NOTION_TEXTS.connect}
          text={NOTION_TEXTS.label}
          aboutLabel={NOTION_TEXTS.about}
          tipText={NOTION_TEXTS.tip}
          stateText={connectionStateText(notion.connection, notion.connection?.workspaceName)}
          errorText={notion.hasSignInFailed ? NOTION_TEXTS.failed : undefined}
          onConnect={notion.connect}
        />
        <RequestRow
          logo={<GoogleDriveLogo />}
          connectLabel={GOOGLE_DRIVE_TEXTS.connect}
          text={GOOGLE_DRIVE_TEXTS.label}
          aboutLabel={GOOGLE_DRIVE_TEXTS.about}
          tipText={GOOGLE_DRIVE_TEXTS.tip}
          stateText={connectionStateText(drive.connection, drive.connection?.email)}
          errorText={drive.hasSignInFailed ? GOOGLE_DRIVE_TEXTS.failed : undefined}
          onConnect={drive.connect}
        >
          {drive.connection?.isConnected && (
            <>
              <p className="request-row__detail">
                {folderId === null ? (
                  GOOGLE_DRIVE_TEXTS.noFolder
                ) : (
                  <>
                    <span>{GOOGLE_DRIVE_TEXTS.folderChosen}</span>
                    <a href={folderAddress(folderId)} target={NEW_TAB} rel={NEW_TAB_REL}>
                      {GOOGLE_DRIVE_TEXTS.openFolder}
                    </a>
                  </>
                )}
              </p>
              <button type="button" className="request-row__action" onClick={drive.chooseFolder}>
                {GOOGLE_DRIVE_TEXTS.chooseFolder}
              </button>
            </>
          )}
        </RequestRow>
        <RequestRow
          logo={<LetterboxdLogo />}
          connectLabel={LETTERBOXD_TEXTS.connect}
          text={LETTERBOXD_TEXTS.label}
          aboutLabel={LETTERBOXD_TEXTS.about}
          tipText={LETTERBOXD_TEXTS.tip}
          stateText={likesStateText(letterboxd.likes)}
          onConnect={letterboxd.openGuide}
        />
        <RequestRow
          logo={<SpotifyLogo />}
          connectLabel={SPOTIFY_TEXTS.connect}
          text={SPOTIFY_TEXTS.label}
          aboutLabel={SPOTIFY_TEXTS.about}
          tipText={SPOTIFY_TEXTS.tip}
          stateText={connectionStateText(spotify.connection, spotify.connection?.name)}
          errorText={spotify.hasSignInFailed ? SPOTIFY_TEXTS.failed : undefined}
          onConnect={spotify.press}
        >
          {spotify.connection?.isConnected && (
            <>
              <p className="request-row__detail">
                {playlistId === null ? (
                  SPOTIFY_TEXTS.noPlaylist
                ) : (
                  <>
                    <span>{SPOTIFY_TEXTS.playlistChosen}</span>
                    <a href={playlistAddress(playlistId)} target={NEW_TAB} rel={NEW_TAB_REL}>
                      {SPOTIFY_TEXTS.openPlaylist}
                    </a>
                  </>
                )}
              </p>
              <button type="button" className="request-row__action" onClick={spotify.connectAgain}>
                {SPOTIFY_TEXTS.connectAgain}
              </button>
            </>
          )}
        </RequestRow>
      </DisclosureToggle>
      {letterboxd.isGuideOpen && (
        <UploadGuideDialog
          title={LETTERBOXD_TEXTS.guideTitle}
          steps={EXPORT_STEPS}
          hint={LETTERBOXD_TEXTS.hint}
          uploadLabel={LETTERBOXD_TEXTS.uploadCsv}
          closeLabel={APP_TEXTS.closeDialog}
          accept={LETTERBOXD_TEXTS.accept}
          isUploading={letterboxd.isUploading}
          errorText={letterboxd.uploadError === null ? undefined : UPLOAD_ERRORS[letterboxd.uploadError]}
          onFile={(file) => void letterboxd.upload(file)}
          onClose={letterboxd.closeGuide}
        />
      )}
      {spotify.isChoosingPlaylist && (
        <LinkDialog
          title={SPOTIFY_TEXTS.choosePlaylist}
          linkLabel={SPOTIFY_TEXTS.playlistLink}
          initialLink={playlistId === null ? '' : playlistAddress(playlistId)}
          saveLabel={SPOTIFY_TEXTS.save}
          closeLabel={APP_TEXTS.closeDialog}
          isSaving={spotify.isSaving}
          errorText={spotify.saveError === null ? undefined : PLAYLIST_SAVE_ERRORS[spotify.saveError]}
          onSave={(link) => void spotify.savePlaylist(link)}
          onClose={spotify.closePlaylist}
        />
      )}
      {drive.isChoosingFolder && (
        <LinkDialog
          title={GOOGLE_DRIVE_TEXTS.chooseFolder}
          linkLabel={GOOGLE_DRIVE_TEXTS.folderLink}
          initialLink={folderId === null ? '' : folderAddress(folderId)}
          saveLabel={GOOGLE_DRIVE_TEXTS.save}
          closeLabel={APP_TEXTS.closeDialog}
          isSaving={drive.isSaving}
          errorText={drive.saveError === null ? undefined : FOLDER_SAVE_ERRORS[drive.saveError]}
          onSave={(link) => void drive.saveFolder(link)}
          onClose={drive.closeFolder}
        />
      )}
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
