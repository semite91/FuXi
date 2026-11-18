using Microsoft.AspNetCore.WebUtilities;

namespace FuXi.Api.OAuth;

/// <summary>The Settings page addresses a sign-in sends the Learner back to, for example /settings?notion=connected.</summary>
public sealed class SignInResultAddress(IConfiguration configuration, string resultParameter, string sourceName)
{
    private const string SETTINGS_PATH = "/settings";
    private const string CONNECTED = "connected";
    private const string FAILED = "failed";

    public string Connected() => Address(CONNECTED);

    public string Failed() => Address(FAILED);

    public string For(bool isConnected) => isConnected ? Connected() : Failed();

    // Without the app address there is no page to send the Learner back to, so the API answers 500 itself.
    private string Address(string result)
    {
        var appUrl = OAuthSettings.ReadAppUrl(configuration) ?? throw new ApiException(
            StatusCodes.Status500InternalServerError,
            $"{OAuthSettings.APP_URL_KEY} is not set, so the {sourceName} sign-in cannot return to FuXi.");

        return QueryHelpers.AddQueryString(appUrl + SETTINGS_PATH, resultParameter, result);
    }
}
