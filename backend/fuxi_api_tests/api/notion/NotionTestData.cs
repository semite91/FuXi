using FuXi.Api.Notion;

namespace FuXi.Api.Tests.Api.Notion;

/// <summary>The Notion values every Notion test shares. None of them is a real secret.</summary>
public static class NotionTestData
{
    public const string CLIENT_ID = "notion-client-id-of-a-test";
    public const string CLIENT_SECRET = "notion-client-secret-of-a-test";
    public const string REDIRECT_URI = "http://localhost:5000/api/NotionCallback";
    public const string APP_URL = "https://fuxi.test";
    public const string CODE = "notion-code-of-a-test";
    public const string ACCESS_TOKEN = "secret_access-token-of-a-test";
    public const string REFRESH_TOKEN = "nrt_refresh-token-of-a-test";
    public const string WORKSPACE_NAME = "Learner's Workspace";
    public const string CONNECTED_ADDRESS = APP_URL + "/settings?notion=connected";
    public const string FAILED_ADDRESS = APP_URL + "/settings?notion=failed";

    /// <summary>A token answer with every field Notion documents.</summary>
    public static readonly string FullTokenAnswer = TokenAnswer(ACCESS_TOKEN, REFRESH_TOKEN, WORKSPACE_NAME);

    /// <summary>A host without a database whose every Notion .env key has a value.</summary>
    public static NowApiSettings ConfiguredSettings() => new()
    {
        NotionClientId = CLIENT_ID,
        NotionClientSecret = CLIENT_SECRET,
        NotionRedirectUri = REDIRECT_URI,
        AppUrl = APP_URL,
    };

    /// <summary>A host without a database where only this Notion .env key is missing.</summary>
    public static NowApiSettings SettingsWithout(string key) => key switch
    {
        NotionSettings.CLIENT_ID_KEY => ConfiguredSettings() with { NotionClientId = null },
        NotionSettings.CLIENT_SECRET_KEY => ConfiguredSettings() with { NotionClientSecret = null },
        NotionSettings.REDIRECT_URI_KEY => ConfiguredSettings() with { NotionRedirectUri = null },
        NotionSettings.APP_URL_KEY => ConfiguredSettings() with { AppUrl = null },
        _ => throw new ArgumentOutOfRangeException(nameof(key), key, null),
    };

    /// <summary>Gives every Notion .env key of a database host a value.</summary>
    public static void Configure(Dictionary<string, string?> settings)
    {
        settings[NotionSettings.CLIENT_ID_KEY] = CLIENT_ID;
        settings[NotionSettings.CLIENT_SECRET_KEY] = CLIENT_SECRET;
        settings[NotionSettings.REDIRECT_URI_KEY] = REDIRECT_URI;
        settings[NotionSettings.APP_URL_KEY] = APP_URL;
    }

    /// <summary>A token answer; a null value leaves its field out.</summary>
    public static string TokenAnswer(string? accessToken, string? refreshToken, string? workspaceName)
    {
        var fields = new Dictionary<string, string?>
        {
            ["access_token"] = accessToken,
            ["token_type"] = "bearer",
            ["refresh_token"] = refreshToken,
            ["bot_id"] = "bot-id-of-a-test",
            ["workspace_name"] = workspaceName,
            ["workspace_id"] = "workspace-id-of-a-test",
        };

        return System.Text.Json.JsonSerializer.Serialize(fields.Where(pair => pair.Value is not null).ToDictionary());
    }
}
