namespace FuXi.Api.Push;

/// <summary>The VAPID keys that sign a push message, and the optional contact of the sender.</summary>
public sealed record VapidDetails(string PublicKey, string PrivateKey, string? Subject);
