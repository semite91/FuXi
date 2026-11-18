using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.OAuth;
using Microsoft.AspNetCore.WebUtilities;

namespace FuXi.Api.Notion;

/// <summary>The Notion sign-in logic behind the Notion endpoints.</summary>
public sealed class NotionService(
    FuXiDbContext database,
    IConfiguration configuration,
    OAuthStateStore stateStore,
    NotionOAuthClient oauthClient,
    ILogger<NotionService> logger)
{
    private const string AUTHORIZE_ADDRESS = "https://api.notion.com/v1/oauth/authorize";
    private const string RESULT_PARAMETER = "notion";

    private readonly SignInResultAddress resultAddress = new(configuration, RESULT_PARAMETER, NotionSettings.SOURCE_NAME);

    /// <summary>
    /// The Notion address that asks the Learner to allow FuXi to read the chosen pages,
    /// or the Settings page address with the failure when the Notion keys are not set.
    /// </summary>
    public string StartSignIn()
    {
        var failedAddress = resultAddress.Failed();
        var options = NotionSettings.ReadClient(configuration);
        if (options is null)
        {
            return failedAddress;
        }

        return QueryHelpers.AddQueryString(AUTHORIZE_ADDRESS, new Dictionary<string, string?>
        {
            ["client_id"] = options.ClientId,
            ["response_type"] = "code",
            ["owner"] = "user",
            ["redirect_uri"] = options.RedirectUri,
            ["state"] = stateStore.Create(NotionSettings.SOURCE_NAME),
        });
    }

    /// <summary>Finishes a sign-in Notion sent back. Returns the Settings page address that shows the result.</summary>
    public async Task<string> HandleCallbackAsync(string? code, string? state, string? error, CancellationToken cancellationToken)
    {
        var failedAddress = resultAddress.Failed();
        var options = NotionSettings.ReadClient(configuration);

        // The state is checked first, so it is used up even when the Learner cancelled on Notion.
        if (!stateStore.TryUse(NotionSettings.SOURCE_NAME, state) || options is null || !string.IsNullOrEmpty(error) || string.IsNullOrEmpty(code))
        {
            return failedAddress;
        }

        return resultAddress.For(await TryConnectAsync(options, code, cancellationToken));
    }

    /// <summary>Notion is connected when an access token is saved. An empty workspace name is given as null.</summary>
    public async Task<NotionConnection> GetConnectionAsync(CancellationToken cancellationToken)
    {
        var values = await SettingRows.ReadAsync(
            database, [SettingCodes.NOTION_ACCESS_TOKEN, SettingCodes.NOTION_WORKSPACE_NAME], cancellationToken);
        if (string.IsNullOrEmpty(values.GetValueOrDefault(SettingCodes.NOTION_ACCESS_TOKEN)))
        {
            return new NotionConnection(false, null);
        }

        var workspaceName = values.GetValueOrDefault(SettingCodes.NOTION_WORKSPACE_NAME);

        return new NotionConnection(true, string.IsNullOrEmpty(workspaceName) ? null : workspaceName);
    }

    // The code, the client secret and the tokens are never logged.
    private async Task<bool> TryConnectAsync(OAuthClientOptions options, string code, CancellationToken cancellationToken)
    {
        try
        {
            var tokens = await oauthClient.ExchangeAsync(options, code, cancellationToken);
            if (tokens is null)
            {
                logger.LogError("Notion answered the token request without an access token.");
                return false;
            }

            await SettingRows.SaveAsync(database, new Dictionary<string, string>
            {
                [SettingCodes.NOTION_ACCESS_TOKEN] = tokens.AccessToken,
                [SettingCodes.NOTION_REFRESH_TOKEN] = tokens.RefreshToken,
                [SettingCodes.NOTION_WORKSPACE_NAME] = tokens.WorkspaceName,
            }, cancellationToken);
            return true;
        }
        catch (NotionExchangeException exception)
        {
            logger.LogError("Notion refused the token request with status {StatusCode}.", exception.StatusCode);
        }
        catch (Exception exception) when (OAuthFailures.IsConnectFailure(exception, cancellationToken))
        {
            logger.LogError(exception, "The Notion sign-in could not be finished.");
        }

        return false;
    }
}
