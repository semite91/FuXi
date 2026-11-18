using System.Text.Json;
using FuXi.Api.OAuth;
using FuXi.Api.Spotify;
using FuXi.Api.Tests.Api.Notion;

namespace FuXi.Api.Tests.Api.Spotify;

/// <summary>The Spotify values every Spotify test shares. None of them is a real secret.</summary>
public static class SpotifyTestData
{
    public const string CLIENT_ID = "spotify-client-id-of-a-test";
    public const string CLIENT_SECRET = "spotify-client-secret-of-a-test";
    public const string REDIRECT_URI = "http://127.0.0.1:5000/api/SpotifyCallback";
    public const string APP_URL = NotionTestData.APP_URL;
    public const string CODE = "spotify-code-of-a-test";
    public const string ACCESS_TOKEN = "BQD-access-token-of-a-test";
    public const string REFRESH_TOKEN = "AQD-refresh-token-of-a-test";
    public const string USER_ID = "learner-user-id";
    public const string DISPLAY_NAME = "The Learner";
    public const string PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M";
    public const string SCOPES = "playlist-read-private playlist-read-collaborative";
    public const string TOKEN_HOST = "accounts.spotify.com";
    public const string CONNECTED_ADDRESS = APP_URL + "/settings?spotify=connected";
    public const string FAILED_ADDRESS = APP_URL + "/settings?spotify=failed";

    /// <summary>The answer of a playlist items call that the account may read.</summary>
    public const string EmptyItemsAnswer = "{\"items\":[],\"next\":null}";

    /// <summary>A token answer with every field Spotify documents for a code exchange.</summary>
    public static readonly string FullTokenAnswer = TokenAnswer(ACCESS_TOKEN, REFRESH_TOKEN, SCOPES);

    /// <summary>A host without a database whose every Spotify .env key has a value.</summary>
    public static NowApiSettings ConfiguredSettings() => new()
    {
        SpotifyClientId = CLIENT_ID,
        SpotifyClientSecret = CLIENT_SECRET,
        SpotifyRedirectUri = REDIRECT_URI,
        AppUrl = APP_URL,
    };

    /// <summary>A host without a database where only this Spotify .env key is missing.</summary>
    public static NowApiSettings SettingsWithout(string key) => key switch
    {
        SpotifySettings.CLIENT_ID_KEY => ConfiguredSettings() with { SpotifyClientId = null },
        SpotifySettings.CLIENT_SECRET_KEY => ConfiguredSettings() with { SpotifyClientSecret = null },
        SpotifySettings.REDIRECT_URI_KEY => ConfiguredSettings() with { SpotifyRedirectUri = null },
        _ => throw new ArgumentOutOfRangeException(nameof(key), key, null),
    };

    /// <summary>Gives every Spotify .env key of a database host a value.</summary>
    public static void Configure(Dictionary<string, string?> settings)
    {
        settings[SpotifySettings.CLIENT_ID_KEY] = CLIENT_ID;
        settings[SpotifySettings.CLIENT_SECRET_KEY] = CLIENT_SECRET;
        settings[SpotifySettings.REDIRECT_URI_KEY] = REDIRECT_URI;
        settings[OAuthSettings.APP_URL_KEY] = APP_URL;
    }

    /// <summary>A token answer; a null value leaves its field out.</summary>
    public static string TokenAnswer(string? accessToken, string? refreshToken, string? scope)
    {
        var fields = new Dictionary<string, object?>
        {
            ["access_token"] = accessToken,
            ["token_type"] = "Bearer",
            ["expires_in"] = 3600,
            ["refresh_token"] = refreshToken,
            ["scope"] = scope,
        };

        return JsonSerializer.Serialize(fields.Where(pair => pair.Value is not null).ToDictionary());
    }

    /// <summary>The /v1/me answer; a null value leaves its field out.</summary>
    public static string MeAnswer(string? id, string? displayName)
    {
        var fields = new Dictionary<string, object?> { ["id"] = id, ["display_name"] = displayName };

        return JsonSerializer.Serialize(fields.Where(pair => pair.Value is not null).ToDictionary());
    }
}
