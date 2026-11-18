using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using FuXi.Api.OAuth;

namespace FuXi.Api.Spotify;

/// <summary>Calls Spotify's token endpoint and the /v1/me call for the sign-in.</summary>
public sealed class SpotifyOAuthClient(HttpClient httpClient)
{
    /// <summary>The name of the HttpClient this client gets from IHttpClientFactory.</summary>
    public const string HTTP_CLIENT_NAME = "Spotify";

    /// <summary>How long each Spotify request may take.</summary>
    public static readonly TimeSpan REQUEST_TIMEOUT = TimeSpan.FromSeconds(30);

    private const string TOKEN_ADDRESS = "https://accounts.spotify.com/api/token";
    private const string ME_ADDRESS = "https://api.spotify.com/v1/me";
    private const string BEARER_SCHEME = "Bearer";
    private const string BASIC_SCHEME = "Basic";
    private const string SOURCE = "Spotify";
    private const string PLAYLIST_ITEMS_FORMAT = "https://api.spotify.com/v1/playlists/{0}/items?limit=1";
    private const string REFRESH_TOKEN_GRANT = "refresh_token";
    private const string AUTHORIZATION_CODE_GRANT = "authorization_code";

    /// <summary>Sends the code to Spotify. Throws <see cref="OAuthRequestException"/> on an error status.</summary>
    public async Task<SpotifyTokens> ExchangeAsync(OAuthClientOptions options, string code, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, TOKEN_ADDRESS)
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["grant_type"] = AUTHORIZATION_CODE_GRANT,
                ["code"] = code,
                ["redirect_uri"] = options.RedirectUri,
            }),
        };
        return await SendTokenRequestAsync(request, options, cancellationToken);
    }

    /// <summary>A new access token for the saved refresh token. Throws <see cref="OAuthRequestException"/> on an error status.</summary>
    public async Task<string> RefreshAsync(OAuthClientOptions options, string refreshToken, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, TOKEN_ADDRESS)
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["grant_type"] = REFRESH_TOKEN_GRANT,
                ["refresh_token"] = refreshToken,
            }),
        };

        return (await SendTokenRequestAsync(request, options, cancellationToken)).AccessToken;
    }

    /// <summary>
    /// Whether the signed-in account may read the playlist's items. Spotify answers 401, 403 or 404 for a playlist the
    /// account neither owns nor collaborates on; any other error status throws <see cref="OAuthRequestException"/>.
    /// </summary>
    public async Task<bool> CanReadPlaylistAsync(string accessToken, string playlistId, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, string.Format(PLAYLIST_ITEMS_FORMAT, playlistId));
        request.Headers.Authorization = new AuthenticationHeaderValue(BEARER_SCHEME, accessToken);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden or HttpStatusCode.NotFound)
        {
            return false;
        }

        OAuthRequestException.ThrowIfFailed(response, SOURCE, "playlist");

        return true;
    }

    private async Task<SpotifyTokens> SendTokenRequestAsync(HttpRequestMessage request, OAuthClientOptions options, CancellationToken cancellationToken)
    {
        request.Headers.Authorization = new AuthenticationHeaderValue(BASIC_SCHEME, OAuthCredentials.Basic(options));
        using var response = await httpClient.SendAsync(request, cancellationToken);
        OAuthRequestException.ThrowIfFailed(response, SOURCE, "token");

        var answer = await response.Content.ReadFromJsonAsync<TokenAnswer>(cancellationToken);

        return new SpotifyTokens(answer?.AccessToken ?? string.Empty, answer?.RefreshToken ?? string.Empty, answer?.Scope ?? string.Empty);
    }

    /// <summary>The signed-in account, or null when Spotify gives no user id.</summary>
    public async Task<SpotifyUser?> GetUserAsync(string accessToken, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, ME_ADDRESS);
        request.Headers.Authorization = new AuthenticationHeaderValue(BEARER_SCHEME, accessToken);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        OAuthRequestException.ThrowIfFailed(response, SOURCE, "me");

        var answer = await response.Content.ReadFromJsonAsync<MeAnswer>(cancellationToken);

        return string.IsNullOrEmpty(answer?.Id) ? null : new SpotifyUser(answer.Id, answer.DisplayName);
    }

    private sealed record TokenAnswer(
        [property: JsonPropertyName("access_token")] string? AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("scope")] string? Scope);

    private sealed record MeAnswer(
        [property: JsonPropertyName("id")] string? Id,
        [property: JsonPropertyName("display_name")] string? DisplayName);
}

/// <summary>What Spotify gives after a code exchange. A missing value is empty.</summary>
public sealed record SpotifyTokens(string AccessToken, string RefreshToken, string Scope);

/// <summary>The signed-in Spotify account. The display name is null when the account has none.</summary>
public sealed record SpotifyUser(string Id, string? DisplayName);
