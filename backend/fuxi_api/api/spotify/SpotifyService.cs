using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.OAuth;
using Microsoft.AspNetCore.WebUtilities;

namespace FuXi.Api.Spotify;

/// <summary>The Spotify sign-in and playlist logic behind the Spotify endpoints.</summary>
public sealed class SpotifyService(
    FuXiDbContext database,
    IConfiguration configuration,
    OAuthStateStore stateStore,
    SpotifyOAuthClient oauthClient,
    ILogger<SpotifyService> logger)
{
    /// <summary>The scopes FuXi asks for: read the Learner's own public, private and shared playlists.</summary>
    public static readonly string[] SCOPES = ["playlist-read-private", "playlist-read-collaborative"];

    private const string AUTHORIZE_ADDRESS = "https://accounts.spotify.com/authorize";
    private const string RESULT_PARAMETER = "spotify";
    private const char SCOPE_SEPARATOR = ' ';
    private const string NOT_A_PLAYLIST_LINK = "This is not a Spotify playlist link.";
    private const string NOT_CONNECTED = "Connect Spotify before choosing a playlist.";
    private const string TOKEN_REQUEST = "token";
    private const string NOT_SET_UP = "Spotify is not set up on the server: its .env keys are empty.";
    private const string SIGN_IN_ENDED = "Spotify no longer accepts the saved sign-in. Connect Spotify again.";
    private const string PLAYLIST_NOT_READABLE = "Spotify does not let FuXi read this playlist. Choose one you own or collaborate on.";
    private const string SPOTIFY_UNREACHABLE = "Spotify could not be reached to check the playlist. Try again.";

    private static readonly string[] CONNECTION_CODES =
        [SettingCodes.SPOTIFY_REFRESH_TOKEN, SettingCodes.SPOTIFY_NAME, SettingCodes.SPOTIFY_PLAYLIST_ID];

    private readonly SignInResultAddress resultAddress = new(configuration, RESULT_PARAMETER, SpotifySettings.SOURCE_NAME);

    /// <summary>
    /// The Spotify address that asks the Learner to let FuXi read their playlists, or the Settings page address with
    /// the failure when the Spotify keys are not set.
    /// </summary>
    public string StartSignIn()
    {
        var failedAddress = resultAddress.Failed();
        var options = SpotifySettings.ReadClient(configuration);
        if (options is null)
        {
            return failedAddress;
        }

        return QueryHelpers.AddQueryString(AUTHORIZE_ADDRESS, new Dictionary<string, string?>
        {
            ["client_id"] = options.ClientId,
            ["response_type"] = "code",
            ["redirect_uri"] = options.RedirectUri,
            ["scope"] = string.Join(SCOPE_SEPARATOR, SCOPES),
            // Without it Spotify skips its consent page for a signed-in browser, so "Connect again" could not switch accounts.
            ["show_dialog"] = "true",
            ["state"] = stateStore.Create(SpotifySettings.SOURCE_NAME),
        });
    }

    /// <summary>Finishes a sign-in Spotify sent back. Returns the Settings page address that shows the result.</summary>
    public async Task<string> HandleCallbackAsync(string? code, string? state, string? error, CancellationToken cancellationToken)
    {
        var failedAddress = resultAddress.Failed();
        var options = SpotifySettings.ReadClient(configuration);

        // The state is checked first, so it is used up even when the Learner cancelled on Spotify.
        if (!stateStore.TryUse(SpotifySettings.SOURCE_NAME, state) || options is null || !string.IsNullOrEmpty(error) || string.IsNullOrEmpty(code))
        {
            return failedAddress;
        }

        return resultAddress.For(await TryConnectAsync(options, code, cancellationToken));
    }

    /// <summary>Spotify is connected when a refresh token is saved. An empty name or playlist is given as null.</summary>
    public async Task<SpotifyConnection> GetConnectionAsync(CancellationToken cancellationToken)
    {
        var values = await SettingRows.ReadAsync(database, CONNECTION_CODES, cancellationToken);
        if (string.IsNullOrEmpty(values.GetValueOrDefault(SettingCodes.SPOTIFY_REFRESH_TOKEN)))
        {
            return new SpotifyConnection(false, null, null);
        }

        return new SpotifyConnection(
            true,
            SettingRows.NullWhenEmpty(values.GetValueOrDefault(SettingCodes.SPOTIFY_NAME)),
            SettingRows.NullWhenEmpty(values.GetValueOrDefault(SettingCodes.SPOTIFY_PLAYLIST_ID)));
    }

    /// <summary>
    /// Saves the playlist the engine reads, after Spotify confirms the signed-in account can read its items (a playlist
    /// the account neither owns nor collaborates on is refused with 422).
    /// </summary>
    public async Task<SpotifyPlaylistSaved> UpdatePlaylistAsync(string? playlistLink, CancellationToken cancellationToken)
    {
        var playlistId = SpotifyPlaylistLink.TryReadPlaylistId(playlistLink) ?? throw ApiException.BadRequest(NOT_A_PLAYLIST_LINK);
        if (!(await GetConnectionAsync(cancellationToken)).IsConnected)
        {
            throw ApiException.Conflict(NOT_CONNECTED);
        }

        await EnsureReadableAsync(playlistId, cancellationToken);
        await SettingRows.SaveAsync(database, new Dictionary<string, string> { [SettingCodes.SPOTIFY_PLAYLIST_ID] = playlistId }, cancellationToken);

        return new SpotifyPlaylistSaved(playlistId);
    }

    // A new access token from the saved refresh token, then one items call. Nothing but the answer's status is kept.
    private async Task EnsureReadableAsync(string playlistId, CancellationToken cancellationToken)
    {
        var options = SpotifySettings.ReadClient(configuration) ?? throw ApiException.Conflict(NOT_SET_UP);
        var refreshToken = (await SettingRows.ReadAsync(database, [SettingCodes.SPOTIFY_REFRESH_TOKEN], cancellationToken))
            .GetValueOrDefault(SettingCodes.SPOTIFY_REFRESH_TOKEN, string.Empty);
        try
        {
            var accessToken = await oauthClient.RefreshAsync(options, refreshToken, cancellationToken);
            if (!await oauthClient.CanReadPlaylistAsync(accessToken, playlistId, cancellationToken))
            {
                throw ApiException.Unprocessable(PLAYLIST_NOT_READABLE);
            }
        }
        catch (OAuthRequestException exception) when (exception is { RequestName: TOKEN_REQUEST, StatusCode: StatusCodes.Status400BadRequest or StatusCodes.Status401Unauthorized })
        {
            logger.LogWarning("{Message}", exception.Message);
            throw ApiException.Conflict(SIGN_IN_ENDED);
        }
        catch (OAuthRequestException exception)
        {
            logger.LogError("{Message}", exception.Message);
            throw ApiException.BadGateway(SPOTIFY_UNREACHABLE);
        }
        catch (Exception exception) when (OAuthFailures.IsConnectFailure(exception, cancellationToken))
        {
            logger.LogError("The Spotify playlist check failed: {ErrorType}.", exception.GetType().Name);
            throw ApiException.BadGateway(SPOTIFY_UNREACHABLE);
        }
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
                logger.LogError("Spotify answered the token request without {Missing}.", missing);
                return false;
            }

            var user = await oauthClient.GetUserAsync(tokens.AccessToken, cancellationToken);
            if (user is null)
            {
                logger.LogError("Spotify answered the me request without a user id.");
                return false;
            }

            await SaveAsync(tokens.RefreshToken, user, cancellationToken);
            return true;
        }
        catch (OAuthRequestException exception)
        {
            logger.LogError("{Message}", exception.Message);
        }
        catch (Exception exception) when (OAuthFailures.IsConnectFailure(exception, cancellationToken))
        {
            logger.LogError("The Spotify sign-in could not be finished: {ErrorType}.", exception.GetType().Name);
        }

        return false;
    }

    private static string? MissingPart(SpotifyTokens tokens)
    {
        if (string.IsNullOrEmpty(tokens.AccessToken))
        {
            return "an access token";
        }

        if (string.IsNullOrEmpty(tokens.RefreshToken))
        {
            return "a refresh token";
        }

        var granted = tokens.Scope.Split(SCOPE_SEPARATOR);

        return SCOPES.All(scope => granted.Contains(scope, StringComparer.Ordinal)) ? null : "the playlist read scopes";
    }

    // Another account may not own the saved playlist, so a new user id clears it in the same transaction.
    private async Task SaveAsync(string refreshToken, SpotifyUser user, CancellationToken cancellationToken)
    {
        var saved = await SettingRows.ReadAsync(
            database, [SettingCodes.SPOTIFY_USER_ID, SettingCodes.SPOTIFY_PLAYLIST_ID], cancellationToken);
        var values = new Dictionary<string, string>
        {
            [SettingCodes.SPOTIFY_REFRESH_TOKEN] = refreshToken,
            [SettingCodes.SPOTIFY_USER_ID] = user.Id,
            [SettingCodes.SPOTIFY_NAME] = string.IsNullOrEmpty(user.DisplayName) ? user.Id : user.DisplayName,
        };
        var isOtherAccount = !string.Equals(saved.GetValueOrDefault(SettingCodes.SPOTIFY_USER_ID), user.Id, StringComparison.Ordinal);
        if (isOtherAccount && !string.IsNullOrEmpty(saved.GetValueOrDefault(SettingCodes.SPOTIFY_PLAYLIST_ID)))
        {
            values[SettingCodes.SPOTIFY_PLAYLIST_ID] = string.Empty;
        }

        await SettingRows.SaveAsync(database, values, cancellationToken);
    }
}
