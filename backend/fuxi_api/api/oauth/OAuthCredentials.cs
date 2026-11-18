using System.Text;

namespace FuXi.Api.OAuth;

/// <summary>The client credentials as the Basic authorization header carries them.</summary>
public static class OAuthCredentials
{
    public static string Basic(OAuthClientOptions options) =>
        Convert.ToBase64String(Encoding.UTF8.GetBytes($"{options.ClientId}:{options.ClientSecret}"));
}
