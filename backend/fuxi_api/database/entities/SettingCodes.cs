namespace FuXi.Api.Database.Entities;

/// <summary>The Code of every <see cref="Setting"/> row the app writes.</summary>
public static class SettingCodes
{
    public const string NOTION_ACCESS_TOKEN = "NotionAccessToken";
    public const string NOTION_REFRESH_TOKEN = "NotionRefreshToken";
    public const string NOTION_WORKSPACE_NAME = "NotionWorkspaceName";
    public const string GOOGLE_DRIVE_REFRESH_TOKEN = "GoogleDriveRefreshToken";
    public const string GOOGLE_DRIVE_EMAIL = "GoogleDriveEmail";
    public const string GOOGLE_DRIVE_FOLDER_ID = "GoogleDriveFolderId";
    public const string LETTERBOXD_LIKED_FILMS_CSV = "LetterboxdLikedFilmsCsv";
}
