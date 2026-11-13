namespace FuXi.Api.Push;

/// <summary>The VAPID configuration keys and the placeholder public key used while no real keys are configured.</summary>
public static class VapidSettings
{
    public const string PUBLIC_KEY_KEY = "VAPID_PUBLIC_KEY";
    public const string PRIVATE_KEY_KEY = "VAPID_PRIVATE_KEY";

    /// <summary>The mailto: or https: contact the push services may use to reach the sender.</summary>
    public const string SUBJECT_KEY = "VAPID_SUBJECT";

    // A valid P-256 public key whose private half was never stored. It cannot send notifications.
    public const string PLACEHOLDER_PUBLIC_KEY =
        "BMVrLSxLCIdXiEP5S1Srz0F_EiM3W92FK4yLK7YGpFcvXkd3pM5MCGBzpAVUFgqoLpAx10dMkukD-l1gEOtbD0Y";

    /// <summary>The configured VAPID details, or null when the public or the private key is empty, so nothing can be signed.</summary>
    public static VapidDetails? ReadDetails(IConfiguration configuration)
    {
        var publicKey = configuration[PUBLIC_KEY_KEY];
        var privateKey = configuration[PRIVATE_KEY_KEY];
        if (string.IsNullOrWhiteSpace(publicKey) || string.IsNullOrWhiteSpace(privateKey))
        {
            return null;
        }

        var subject = configuration[SUBJECT_KEY];

        return new VapidDetails(publicKey, privateKey, string.IsNullOrWhiteSpace(subject) ? null : subject);
    }
}
