using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.OAuth;
using Microsoft.AspNetCore.WebUtilities;

namespace FuXi.Api.GoogleDrive;

/// <summary>The Google Drive sign-in and folder logic behind the Google Drive endpoints.</summary>
public sealed class GoogleDriveService(
    FuXiDbContext database,
    IConfiguration configuration,
    OAuthStateStore stateStore,
    GoogleOAuthClient oauthClient,
    ILogger<GoogleDriveService> logger)
{
    /// <summary>The one scope FuXi asks for: read the Learner's Drive files, so the chosen folder can be read.</summary>
    public const string DRIVE_READ_ONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly";

    private const string AUTHORIZE_ADDRESS = "https://accounts.google.com/o/oauth2/v2/auth";
    private const string RESULT_PARAMETER = "drive";
    private const char SCOPE_SEPARATOR = ' ';
    private const string NOT_A_FOLDER_LINK = "This is not a Google Drive folder link.";
    private const string NOT_CONNECTED = "Connect Google Drive before choosing a folder.";

    private static readonly string[] CONNECTION_CODES =
        [SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN, SettingCodes.GOOGLE_DRIVE_EMAIL, SettingCodes.GOOGLE_DRIVE_FOLDER_ID];

    private readonly SignInResultAddress resultAddress = new(configuration, RESULT_PARAMETER, GoogleDriveSettings.SOURCE_NAME);

    /// <summary>
    /// The Google address that asks the Learner to let FuXi read their Drive, or the Settings page address with the
    /// failure when the Google keys are not set. offline and consent make Google give a refresh token every time.
    /// </summary>
    public string StartSignIn()
    {
        var failedAddress = resultAddress.Failed();
        var options = GoogleDriveSettings.ReadClient(configuration);
        if (options is null)
        {
            return failedAddress;
        }

        return QueryHelpers.AddQueryString(AUTHORIZE_ADDRESS, new Dictionary<string, string?>
        {
            ["client_id"] = options.ClientId,
            ["response_type"] = "code",
            ["redirect_uri"] = options.RedirectUri,
            ["scope"] = DRIVE_READ_ONLY_SCOPE,
            ["access_type"] = "offline",
            ["prompt"] = "consent",
            ["state"] = stateStore.Create(GoogleDriveSettings.SOURCE_NAME),
        });
    }

    /// <summary>Finishes a sign-in Google sent back. Returns the Settings page address that shows the result.</summary>
    public async Task<string> HandleCallbackAsync(string? code, string? state, string? error, CancellationToken cancellationToken)
    {
        var failedAddress = resultAddress.Failed();
        var options = GoogleDriveSettings.ReadClient(configuration);

        // The state is checked first, so it is used up even when the Learner cancelled on Google.
        if (!stateStore.TryUse(GoogleDriveSettings.SOURCE_NAME, state) || options is null || !string.IsNullOrEmpty(error) || string.IsNullOrEmpty(code))
        {
            return failedAddress;
        }

        return resultAddress.For(await TryConnectAsync(options, code, cancellationToken));
    }

    /// <summary>Google Drive is connected when a refresh token is saved. An empty email or folder is given as null.</summary>
    public async Task<GoogleDriveConnection> GetConnectionAsync(CancellationToken cancellationToken)
    {
        var values = await SettingRows.ReadAsync(database, CONNECTION_CODES, cancellationToken);
        if (string.IsNullOrEmpty(values.GetValueOrDefault(SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN)))
        {
            return new GoogleDriveConnection(false, null, null);
        }

        return new GoogleDriveConnection(
            true,
            SettingRows.NullWhenEmpty(values.GetValueOrDefault(SettingCodes.GOOGLE_DRIVE_EMAIL)),
            SettingRows.NullWhenEmpty(values.GetValueOrDefault(SettingCodes.GOOGLE_DRIVE_FOLDER_ID)));
    }

    /// <summary>Saves the folder the engine reads. Only the link's form is checked; Google is not called.</summary>
    public async Task<GoogleDriveFolderSaved> UpdateFolderAsync(string? folderLink, CancellationToken cancellationToken)
    {
        var folderId = GoogleDriveFolderLink.TryReadFolderId(folderLink) ?? throw ApiException.BadRequest(NOT_A_FOLDER_LINK);
        if (!(await GetConnectionAsync(cancellationToken)).IsConnected)
        {
            throw ApiException.Conflict(NOT_CONNECTED);
        }

        await SettingRows.SaveAsync(database, new Dictionary<string, string> { [SettingCodes.GOOGLE_DRIVE_FOLDER_ID] = folderId }, cancellationToken);

        return new GoogleDriveFolderSaved(folderId);
    }

    // The code, the client secret and the tokens are never logged.
    private async Task<bool> TryConnectAsync(OAuthClientOptions options, string code, CancellationToken cancellationToken)
    {
        try
        {
            var tokens = await oauthClient.ExchangeAsync(options, code, cancellationToken);
            var missing = MissingPart(tokens);
            if (missing is not null)
            {
                logger.LogError("Google answered the token request without {Missing}.", missing);
                return false;
            }

            var email = await oauthClient.GetEmailAsync(tokens.AccessToken, cancellationToken);
            if (string.IsNullOrEmpty(email))
            {
                logger.LogError("Google Drive answered the about request without an email.");
                return false;
            }

            await SaveAsync(tokens.RefreshToken, email, cancellationToken);
            return true;
        }
        catch (OAuthRequestException exception)
        {
            logger.LogError("{Message}", exception.Message);
        }
        catch (Exception exception) when (OAuthFailures.IsConnectFailure(exception, cancellationToken))
        {
            logger.LogError("The Google Drive sign-in could not be finished: {ErrorType}.", exception.GetType().Name);
        }

        return false;
    }

    private static string? MissingPart(GoogleTokens tokens)
    {
        if (string.IsNullOrEmpty(tokens.AccessToken))
        {
            return "an access token";
        }

        if (string.IsNullOrEmpty(tokens.RefreshToken))
        {
            return "a refresh token";
        }

        return tokens.Scope.Split(SCOPE_SEPARATOR).Contains(DRIVE_READ_ONLY_SCOPE, StringComparer.Ordinal)
            ? null
            : "the Drive read scope";
    }

    // Another account may not see the saved folder, so a new email clears it in the same transaction.
    private async Task SaveAsync(string refreshToken, string email, CancellationToken cancellationToken)
    {
        var saved = await SettingRows.ReadAsync(
            database, [SettingCodes.GOOGLE_DRIVE_EMAIL, SettingCodes.GOOGLE_DRIVE_FOLDER_ID], cancellationToken);
        var values = new Dictionary<string, string>
        {
            [SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN] = refreshToken,
            [SettingCodes.GOOGLE_DRIVE_EMAIL] = email,
        };
        var isOtherAccount = !string.Equals(saved.GetValueOrDefault(SettingCodes.GOOGLE_DRIVE_EMAIL), email, StringComparison.OrdinalIgnoreCase);
        if (isOtherAccount && !string.IsNullOrEmpty(saved.GetValueOrDefault(SettingCodes.GOOGLE_DRIVE_FOLDER_ID)))
        {
            values[SettingCodes.GOOGLE_DRIVE_FOLDER_ID] = string.Empty;
        }

        await SettingRows.SaveAsync(database, values, cancellationToken);
    }
}
