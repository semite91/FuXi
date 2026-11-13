namespace FuXi.Api.Push;

/// <summary>The push services a Push Subscription may point to. Any other host is refused, so the backend never calls an unknown server.</summary>
public static class PushHosts
{
    /// <summary>An entry that starts with this text allows every sub-domain of the host after it, and not the host itself.</summary>
    public const string SUBDOMAIN_WILDCARD = "*";

    public static readonly IReadOnlyList<string> ALLOWED =
    [
        "fcm.googleapis.com",
        "jmt17.google.com",
        "updates.push.services.mozilla.com",
        SUBDOMAIN_WILDCARD + ".notify.windows.com",
        SUBDOMAIN_WILDCARD + ".push.apple.com",
    ];

    public static bool IsAllowed(string host) => ALLOWED.Any(allowed => Matches(host, allowed));

    /// <summary>Only https on the default port of an allowed push host, without surrounding whitespace (SSRF protection).</summary>
    public static bool IsAllowedEndpoint(string endpoint) =>
        endpoint.Length == endpoint.Trim().Length
        && Uri.TryCreate(endpoint, UriKind.Absolute, out var uri)
        && uri.Scheme == Uri.UriSchemeHttps
        && uri.IsDefaultPort
        && IsAllowed(uri.IdnHost);

    private static bool Matches(string host, string allowed)
    {
        if (!allowed.StartsWith(SUBDOMAIN_WILDCARD, StringComparison.Ordinal))
        {
            return host.Equals(allowed, StringComparison.OrdinalIgnoreCase);
        }

        // The suffix starts with a dot, so a look-alike such as evilpush.apple.com does not match.
        var suffix = allowed[SUBDOMAIN_WILDCARD.Length..];

        return host.Length > suffix.Length && host.EndsWith(suffix, StringComparison.OrdinalIgnoreCase);
    }
}
