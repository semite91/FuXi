using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Serialization;

namespace FuXi.Api.Notion;

/// <summary>Trades a Notion sign-in code for tokens at Notion's token endpoint.</summary>
public sealed class NotionOAuthClient(HttpClient httpClient)
{
    /// <summary>The name of the HttpClient this client gets from IHttpClientFactory.</summary>
    public const string HTTP_CLIENT_NAME = "Notion";

    /// <summary>How long the token request may take.</summary>
    public static readonly TimeSpan REQUEST_TIMEOUT = TimeSpan.FromSeconds(30);

    private const string TOKEN_ADDRESS = "https://api.notion.com/v1/oauth/token";
    private const string BASIC_SCHEME = "Basic";
    private const string AUTHORIZATION_CODE_GRANT = "authorization_code";

    /// <summary>Sends the code to Notion. Returns the tokens, or null when Notion refused or answered without an access token.</summary>
    public async Task<NotionTokens?> ExchangeAsync(NotionClientOptions options, string code, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, TOKEN_ADDRESS)
        {
            Content = JsonContent.Create(new TokenRequest(AUTHORIZATION_CODE_GRANT, code, options.RedirectUri)),
        };
        request.Headers.Authorization = new AuthenticationHeaderValue(BASIC_SCHEME, BasicCredentials(options));

        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new NotionExchangeException((int)response.StatusCode);
        }

        var answer = await response.Content.ReadFromJsonAsync<TokenAnswer>(cancellationToken);
        if (string.IsNullOrEmpty(answer?.AccessToken))
        {
            return null;
        }

        return new NotionTokens(answer.AccessToken, answer.RefreshToken ?? string.Empty, answer.WorkspaceName ?? string.Empty);
    }

    private static string BasicCredentials(NotionClientOptions options) =>
        Convert.ToBase64String(Encoding.UTF8.GetBytes($"{options.ClientId}:{options.ClientSecret}"));

    private sealed record TokenRequest(
        [property: JsonPropertyName("grant_type")] string GrantType,
        [property: JsonPropertyName("code")] string Code,
        [property: JsonPropertyName("redirect_uri")] string RedirectUri);

    private sealed record TokenAnswer(
        [property: JsonPropertyName("access_token")] string? AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("workspace_name")] string? WorkspaceName);
}

/// <summary>The tokens and the workspace name Notion gives after a sign-in. Missing optional values are empty.</summary>
public sealed record NotionTokens(string AccessToken, string RefreshToken, string WorkspaceName);

/// <summary>Notion answered the token request with an error status. It carries no code and no token.</summary>
public sealed class NotionExchangeException(int statusCode) : Exception($"Notion answered the token request with status {statusCode}.")
{
    public int StatusCode { get; } = statusCode;
}
