namespace FuXi.Api.OAuth;

/// <summary>The three .env keys of one source's sign-in client. They are set once by the Learner, never changed by the app.</summary>
public sealed record OAuthClientKeys(string ClientIdKey, string ClientSecretKey, string RedirectUriKey);

/// <summary>The client values a sign-in needs from .env.</summary>
public sealed record OAuthClientOptions(string ClientId, string ClientSecret, string RedirectUri);

/// <summary>Reads and checks the .env keys every sign-in shares.</summary>
public static class OAuthSettings
{
    /// <summary>The address of the FuXi web app; every sign-in ends on its Settings page.</summary>
    public const string APP_URL_KEY = "FUXI_APP_URL";

    /// <summary>The configured client, or null when one of its keys is empty.</summary>
    public static OAuthClientOptions? ReadClient(IConfiguration configuration, OAuthClientKeys keys)
    {
        var clientId = configuration[keys.ClientIdKey];
        var clientSecret = configuration[keys.ClientSecretKey];
        var redirectUri = configuration[keys.RedirectUriKey];
        if (string.IsNullOrWhiteSpace(clientId) || string.IsNullOrWhiteSpace(clientSecret) || string.IsNullOrWhiteSpace(redirectUri))
        {
            return null;
        }

        return new OAuthClientOptions(clientId, clientSecret, redirectUri);
    }

    /// <summary>The FuXi web app address without a closing slash, or null when it is empty.</summary>
    public static string? ReadAppUrl(IConfiguration configuration)
    {
        var appUrl = configuration[APP_URL_KEY];

        return string.IsNullOrWhiteSpace(appUrl) ? null : appUrl.TrimEnd('/');
    }

    /// <summary>
    /// Logs every empty client key of a source once at startup. The API still starts: every source is optional,
    /// and its endpoints answer with a failure until the keys are set. The shared app address is logged once by
    /// <see cref="LogMissingAppUrl"/>.
    /// </summary>
    public static void LogMissingKeys(IConfiguration configuration, ILogger logger, string sourceName, OAuthClientKeys keys)
    {
        string[] allKeys = [keys.ClientIdKey, keys.ClientSecretKey, keys.RedirectUriKey];
        var missingKeys = allKeys.Where(key => string.IsNullOrWhiteSpace(configuration[key])).ToList();
        if (missingKeys.Count == 0)
        {
            return;
        }

        logger.LogError("{Source} cannot be connected until these .env keys have a value: {Keys}.", sourceName, string.Join(", ", missingKeys));
    }

    /// <summary>Logs the empty app address once at startup; every sign-in needs it to return to the Settings page.</summary>
    public static void LogMissingAppUrl(IConfiguration configuration, ILoggerFactory loggerFactory)
    {
        if (ReadAppUrl(configuration) is not null)
        {
            return;
        }

        loggerFactory.CreateLogger(typeof(OAuthSettings).FullName!)
            .LogError("The sign-ins cannot return to FuXi until this .env key has a value: {Key}.", APP_URL_KEY);
    }
}
