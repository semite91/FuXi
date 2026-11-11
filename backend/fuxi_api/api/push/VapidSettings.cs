namespace FuXi.Api.Push;

/// <summary>The VAPID configuration keys and the placeholder used until Phase 4 generates real keys.</summary>
public static class VapidSettings
{
    public const string PUBLIC_KEY_KEY = "VAPID_PUBLIC_KEY";
    public const string PRIVATE_KEY_KEY = "VAPID_PRIVATE_KEY";

    // A valid P-256 public key whose private half was never stored. It cannot send notifications.
    public const string PLACEHOLDER_PUBLIC_KEY =
        "BMVrLSxLCIdXiEP5S1Srz0F_EiM3W92FK4yLK7YGpFcvXkd3pM5MCGBzpAVUFgqoLpAx10dMkukD-l1gEOtbD0Y";
}
