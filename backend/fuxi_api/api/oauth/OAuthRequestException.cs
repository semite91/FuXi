namespace FuXi.Api.OAuth;

/// <summary>A source answered a sign-in request with an error status. It carries no code and no token.</summary>
public sealed class OAuthRequestException(string source, string requestName, int statusCode)
    : Exception($"{source} answered the {requestName} request with status {statusCode}.")
{
    public string RequestName { get; } = requestName;

    public int StatusCode { get; } = statusCode;

    /// <summary>Throws <see cref="OAuthRequestException"/> when the answer has an error status.</summary>
    public static void ThrowIfFailed(HttpResponseMessage response, string source, string requestName)
    {
        if (!response.IsSuccessStatusCode)
        {
            throw new OAuthRequestException(source, requestName, (int)response.StatusCode);
        }
    }
}
