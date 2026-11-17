using System.Text.Json;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Notion;

/// <summary>The Notion sign-in logic behind the Notion endpoints.</summary>
public sealed class NotionService(
    FuXiDbContext database,
    IConfiguration configuration,
    NotionStateStore stateStore,
    NotionOAuthClient oauthClient,
    ILogger<NotionService> logger)
{
    private const string AUTHORIZE_ADDRESS = "https://api.notion.com/v1/oauth/authorize";
    private const string SETTINGS_PATH = "/settings";
    private const string RESULT_PARAMETER = "notion";
    private const string CONNECTED = "connected";
    private const string FAILED = "failed";
    private const string APP_URL_MISSING = "FUXI_APP_URL is not set, so the Notion sign-in cannot return to FuXi.";

    /// <summary>
    /// The Notion address that asks the Learner to allow FuXi to read the chosen pages,
    /// or the Settings page address with the failure when the Notion keys are not set.
    /// </summary>
    public string StartSignIn()
    {
        var appUrl = RequireAppUrl();
        var options = NotionSettings.ReadClient(configuration);
        if (options is null)
        {
            return ResultAddress(appUrl, FAILED);
        }

        return QueryHelpers.AddQueryString(AUTHORIZE_ADDRESS, new Dictionary<string, string?>
        {
            ["client_id"] = options.ClientId,
            ["response_type"] = "code",
            ["owner"] = "user",
            ["redirect_uri"] = options.RedirectUri,
            ["state"] = stateStore.Create(),
        });
    }

    /// <summary>Finishes a sign-in Notion sent back. Returns the Settings page address that shows the result.</summary>
    public async Task<string> HandleCallbackAsync(string? code, string? state, string? error, CancellationToken cancellationToken)
    {
        var appUrl = RequireAppUrl();
        var options = NotionSettings.ReadClient(configuration);

        // The state is checked first, so it is used up even when the Learner cancelled on Notion.
        if (!stateStore.TryUse(state) || options is null || !string.IsNullOrEmpty(error) || string.IsNullOrEmpty(code))
        {
            return ResultAddress(appUrl, FAILED);
        }

        return ResultAddress(appUrl, await TryConnectAsync(options, code, cancellationToken) ? CONNECTED : FAILED);
    }

    /// <summary>Notion is connected when an access token is saved. An empty workspace name is given as null.</summary>
    public async Task<NotionConnection> GetConnectionAsync(CancellationToken cancellationToken)
    {
        var values = await database.Settings.AsNoTracking()
            .Where(setting => setting.Code == SettingCodes.NOTION_ACCESS_TOKEN || setting.Code == SettingCodes.NOTION_WORKSPACE_NAME)
            .ToDictionaryAsync(setting => setting.Code, setting => setting.Value, cancellationToken);
        if (string.IsNullOrEmpty(values.GetValueOrDefault(SettingCodes.NOTION_ACCESS_TOKEN)))
        {
            return new NotionConnection(false, null);
        }

        var workspaceName = values.GetValueOrDefault(SettingCodes.NOTION_WORKSPACE_NAME);

        return new NotionConnection(true, string.IsNullOrEmpty(workspaceName) ? null : workspaceName);
    }

    // Without the app address there is no page to send the Learner back to, so the API answers 500 itself.
    private string RequireAppUrl() =>
        NotionSettings.ReadAppUrl(configuration) ?? throw new ApiException(StatusCodes.Status500InternalServerError, APP_URL_MISSING);

    // The code, the client secret and the tokens are never logged.
    private async Task<bool> TryConnectAsync(NotionClientOptions options, string code, CancellationToken cancellationToken)
    {
        try
        {
            var tokens = await oauthClient.ExchangeAsync(options, code, cancellationToken);
            if (tokens is null)
            {
                logger.LogError("Notion answered the token request without an access token.");
                return false;
            }

            await SaveAsync(tokens, cancellationToken);
            return true;
        }
        catch (NotionExchangeException exception)
        {
            logger.LogError("Notion refused the token request with status {StatusCode}.", exception.StatusCode);
        }
        catch (Exception exception) when (IsConnectFailure(exception, cancellationToken))
        {
            logger.LogError(exception, "The Notion sign-in could not be finished.");
        }

        return false;
    }

    // A network error, a timeout, an unreadable answer or a failed save; never the Learner closing the page.
    private static bool IsConnectFailure(Exception exception, CancellationToken cancellationToken) =>
        exception is HttpRequestException or JsonException or DbUpdateException
        || (exception is TaskCanceledException && !cancellationToken.IsCancellationRequested);

    // One SaveChanges is one transaction: the three rows are written together or not at all.
    private async Task SaveAsync(NotionTokens tokens, CancellationToken cancellationToken)
    {
        var values = new Dictionary<string, string>
        {
            [SettingCodes.NOTION_ACCESS_TOKEN] = tokens.AccessToken,
            [SettingCodes.NOTION_REFRESH_TOKEN] = tokens.RefreshToken,
            [SettingCodes.NOTION_WORKSPACE_NAME] = tokens.WorkspaceName,
        };
        var existing = await database.Settings
            .Where(setting => values.Keys.Contains(setting.Code))
            .ToDictionaryAsync(setting => setting.Code, cancellationToken);

        foreach (var (code, value) in values)
        {
            if (existing.TryGetValue(code, out var setting))
            {
                setting.Value = value;
            }
            else
            {
                database.Settings.Add(new Setting { Code = code, Value = value });
            }
        }

        await database.SaveChangesAsync(cancellationToken);
    }

    private static string ResultAddress(string appUrl, string result) =>
        QueryHelpers.AddQueryString(appUrl + SETTINGS_PATH, RESULT_PARAMETER, result);
}
