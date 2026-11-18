using System.Text.Json;
using FuXi.Api.GoogleDrive;
using FuXi.Api.OAuth;
using FuXi.Api.Tests.Api.Notion;

namespace FuXi.Api.Tests.Api.GoogleDrive;

/// <summary>The Google values every Google Drive test shares. None of them is a real secret.</summary>
public static class GoogleDriveTestData
{
    public const string CLIENT_ID = "google-client-id-of-a-test.apps.googleusercontent.com";
    public const string CLIENT_SECRET = "google-client-secret-of-a-test";
    public const string REDIRECT_URI = "http://localhost:5000/api/GoogleDriveCallback";
    public const string APP_URL = NotionTestData.APP_URL;
    public const string CODE = "google-code-of-a-test";
    public const string ACCESS_TOKEN = "ya29.access-token-of-a-test";
    public const string REFRESH_TOKEN = "1//refresh-token-of-a-test";
    public const string EMAIL = "learner@example.com";
    public const string FOLDER_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz-_0123";
    public const string DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly";
    public const string TOKEN_HOST = "oauth2.googleapis.com";
    public const string CONNECTED_ADDRESS = APP_URL + "/settings?drive=connected";
    public const string FAILED_ADDRESS = APP_URL + "/settings?drive=failed";

    /// <summary>A token answer with every field Google documents for a code exchange.</summary>
    public static readonly string FullTokenAnswer = TokenAnswer(ACCESS_TOKEN, REFRESH_TOKEN, DRIVE_SCOPE);

    /// <summary>A host without a database whose every Google .env key has a value.</summary>
    public static NowApiSettings ConfiguredSettings() => new()
    {
        GoogleClientId = CLIENT_ID,
        GoogleClientSecret = CLIENT_SECRET,
        GoogleRedirectUri = REDIRECT_URI,
        AppUrl = APP_URL,
    };

    /// <summary>A host without a database where only this Google .env key is missing.</summary>
    public static NowApiSettings SettingsWithout(string key) => key switch
    {
        GoogleDriveSettings.CLIENT_ID_KEY => ConfiguredSettings() with { GoogleClientId = null },
        GoogleDriveSettings.CLIENT_SECRET_KEY => ConfiguredSettings() with { GoogleClientSecret = null },
        GoogleDriveSettings.REDIRECT_URI_KEY => ConfiguredSettings() with { GoogleRedirectUri = null },
        _ => throw new ArgumentOutOfRangeException(nameof(key), key, null),
    };

    /// <summary>Gives every Google .env key of a database host a value.</summary>
    public static void Configure(Dictionary<string, string?> settings)
    {
        settings[GoogleDriveSettings.CLIENT_ID_KEY] = CLIENT_ID;
        settings[GoogleDriveSettings.CLIENT_SECRET_KEY] = CLIENT_SECRET;
        settings[GoogleDriveSettings.REDIRECT_URI_KEY] = REDIRECT_URI;
        settings[OAuthSettings.APP_URL_KEY] = APP_URL;
    }

    /// <summary>A token answer; a null value leaves its field out.</summary>
    public static string TokenAnswer(string? accessToken, string? refreshToken, string? scope)
    {
        var fields = new Dictionary<string, object?>
        {
            ["access_token"] = accessToken,
            ["expires_in"] = 3599,
            ["refresh_token"] = refreshToken,
            ["scope"] = scope,
            ["token_type"] = "Bearer",
        };

        return JsonSerializer.Serialize(fields.Where(pair => pair.Value is not null).ToDictionary());
    }

    /// <summary>Drive's about answer for fields=user(emailAddress).</summary>
    public static string AboutAnswer(string? email) =>
        JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["user"] = email is null ? new Dictionary<string, string>() : new Dictionary<string, string> { ["emailAddress"] = email },
        });
}
