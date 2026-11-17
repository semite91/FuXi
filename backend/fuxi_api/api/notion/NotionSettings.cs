namespace FuXi.Api.Notion;

/// <summary>The .env keys of the Notion sign-in. They are set once by the Learner, never changed by the app.</summary>
public static class NotionSettings
{
    public const string CLIENT_ID_KEY = "NOTION_CLIENT_ID";
    public const string CLIENT_SECRET_KEY = "NOTION_CLIENT_SECRET";
    public const string REDIRECT_URI_KEY = "NOTION_REDIRECT_URI";

    /// <summary>The address of the FuXi web app; the sign-in ends on its Settings page.</summary>
    public const string APP_URL_KEY = "FUXI_APP_URL";

    private static readonly string[] KEYS = [CLIENT_ID_KEY, CLIENT_SECRET_KEY, REDIRECT_URI_KEY, APP_URL_KEY];

    /// <summary>The configured Notion client, or null when one of its keys is empty.</summary>
    public static NotionClientOptions? ReadClient(IConfiguration configuration)
    {
        var clientId = configuration[CLIENT_ID_KEY];
        var clientSecret = configuration[CLIENT_SECRET_KEY];
        var redirectUri = configuration[REDIRECT_URI_KEY];
        if (string.IsNullOrWhiteSpace(clientId) || string.IsNullOrWhiteSpace(clientSecret) || string.IsNullOrWhiteSpace(redirectUri))
        {
            return null;
        }

        return new NotionClientOptions(clientId, clientSecret, redirectUri);
    }

    /// <summary>The FuXi web app address without a closing slash, or null when it is empty.</summary>
    public static string? ReadAppUrl(IConfiguration configuration)
    {
        var appUrl = configuration[APP_URL_KEY];

        return string.IsNullOrWhiteSpace(appUrl) ? null : appUrl.TrimEnd('/');
    }

    /// <summary>
    /// Logs every empty key once at startup. The API still starts: Notion is optional,
    /// and the Notion endpoints answer with a failure until the keys are set.
    /// </summary>
    public static void LogMissingKeys(IConfiguration configuration, ILoggerFactory loggerFactory)
    {
        var missingKeys = KEYS.Where(key => string.IsNullOrWhiteSpace(configuration[key])).ToList();
        if (missingKeys.Count == 0)
        {
            return;
        }

        loggerFactory.CreateLogger(typeof(NotionSettings).FullName!).LogError(
            "Notion cannot be connected until these .env keys have a value: {Keys}.", string.Join(", ", missingKeys));
    }
}

/// <summary>The Notion client values the sign-in needs from .env.</summary>
public sealed record NotionClientOptions(string ClientId, string ClientSecret, string RedirectUri);
