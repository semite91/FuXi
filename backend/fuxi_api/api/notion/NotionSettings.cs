using FuXi.Api.OAuth;

namespace FuXi.Api.Notion;

/// <summary>The .env keys of the Notion sign-in. They are set once by the Learner, never changed by the app.</summary>
public static class NotionSettings
{
    public const string CLIENT_ID_KEY = "NOTION_CLIENT_ID";
    public const string CLIENT_SECRET_KEY = "NOTION_CLIENT_SECRET";
    public const string REDIRECT_URI_KEY = "NOTION_REDIRECT_URI";

    /// <summary>The address of the FuXi web app; the sign-in ends on its Settings page.</summary>
    public const string APP_URL_KEY = OAuthSettings.APP_URL_KEY;

    public const string SOURCE_NAME = "Notion";

    public static readonly OAuthClientKeys KEYS = new(CLIENT_ID_KEY, CLIENT_SECRET_KEY, REDIRECT_URI_KEY);

    /// <summary>The configured Notion client, or null when one of its keys is empty.</summary>
    public static OAuthClientOptions? ReadClient(IConfiguration configuration) => OAuthSettings.ReadClient(configuration, KEYS);

    /// <summary>Logs every empty Notion key once at startup; the API still starts.</summary>
    public static void LogMissingKeys(IConfiguration configuration, ILoggerFactory loggerFactory) =>
        OAuthSettings.LogMissingKeys(configuration, loggerFactory.CreateLogger(typeof(NotionSettings).FullName!), SOURCE_NAME, KEYS);
}
