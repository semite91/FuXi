using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using FuXi.Api.OAuth;

namespace FuXi.Api.GoogleDrive;

/// <summary>Calls Google's token endpoint and Drive's about call for the sign-in.</summary>
public sealed class GoogleOAuthClient(HttpClient httpClient)
{
    /// <summary>The name of the HttpClient this client gets from IHttpClientFactory.</summary>
    public const string HTTP_CLIENT_NAME = "Google";

    /// <summary>How long each Google request may take.</summary>
    public static readonly TimeSpan REQUEST_TIMEOUT = TimeSpan.FromSeconds(30);

    private const string SOURCE = "Google";
    private const string TOKEN_ADDRESS = "https://oauth2.googleapis.com/token";
    private const string ABOUT_ADDRESS = "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)";
    private const string BEARER_SCHEME = "Bearer";
    private const string AUTHORIZATION_CODE_GRANT = "authorization_code";

    /// <summary>Sends the code to Google. Throws <see cref="OAuthRequestException"/> on an error status.</summary>
    public async Task<GoogleTokens> ExchangeAsync(OAuthClientOptions options, string code, CancellationToken cancellationToken)
    {
        using var form = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["grant_type"] = AUTHORIZATION_CODE_GRANT,
            ["code"] = code,
            ["redirect_uri"] = options.RedirectUri,
            ["client_id"] = options.ClientId,
            ["client_secret"] = options.ClientSecret,
        });
        using var response = await httpClient.PostAsync(TOKEN_ADDRESS, form, cancellationToken);
        OAuthRequestException.ThrowIfFailed(response, SOURCE, "token");

        var answer = await response.Content.ReadFromJsonAsync<TokenAnswer>(cancellationToken);

        return new GoogleTokens(answer?.AccessToken ?? string.Empty, answer?.RefreshToken ?? string.Empty, answer?.Scope ?? string.Empty);
    }

    /// <summary>The email of the signed-in account, or null when Drive gives none.</summary>
    public async Task<string?> GetEmailAsync(string accessToken, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, ABOUT_ADDRESS);
        request.Headers.Authorization = new AuthenticationHeaderValue(BEARER_SCHEME, accessToken);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        OAuthRequestException.ThrowIfFailed(response, SOURCE, "about");

        var answer = await response.Content.ReadFromJsonAsync<AboutAnswer>(cancellationToken);

        return answer?.User?.EmailAddress;
    }

    private sealed record TokenAnswer(
        [property: JsonPropertyName("access_token")] string? AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("scope")] string? Scope);

    private sealed record AboutAnswer([property: JsonPropertyName("user")] AboutUser? User);

    private sealed record AboutUser([property: JsonPropertyName("emailAddress")] string? EmailAddress);
}

/// <summary>What Google gives after a code exchange. A missing value is empty.</summary>
public sealed record GoogleTokens(string AccessToken, string RefreshToken, string Scope);
