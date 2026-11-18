using FuXi.Api.OAuth;

namespace FuXi.Api.Spotify;

/// <summary>The .env keys of the Spotify sign-in. They are set once by the Learner, never changed by the app.</summary>
public static class SpotifySettings
{
    public const string CLIENT_ID_KEY = "SPOTIFY_CLIENT_ID";
    public const string CLIENT_SECRET_KEY = "SPOTIFY_CLIENT_SECRET";
    public const string REDIRECT_URI_KEY = "SPOTIFY_REDIRECT_URI";

    public const string SOURCE_NAME = "Spotify";

    public static readonly OAuthClientKeys KEYS = new(CLIENT_ID_KEY, CLIENT_SECRET_KEY, REDIRECT_URI_KEY);

    /// <summary>The configured Spotify client, or null when one of its keys is empty.</summary>
    public static OAuthClientOptions? ReadClient(IConfiguration configuration) => OAuthSettings.ReadClient(configuration, KEYS);

    /// <summary>Logs every empty Spotify key once at startup; the API still starts.</summary>
    public static void LogMissingKeys(IConfiguration configuration, ILoggerFactory loggerFactory) =>
        OAuthSettings.LogMissingKeys(configuration, loggerFactory.CreateLogger(typeof(SpotifySettings).FullName!), SOURCE_NAME, KEYS);
}
