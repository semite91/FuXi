namespace FuXi.Api.Push;

/// <summary>
/// The body of SavePushSubscription. The browser's subscription object nests p256dh and auth under "keys",
/// so the frontend maps it to these three flat fields.
/// </summary>
public sealed record SavePushSubscriptionRequest(string? Endpoint, string? P256dh, string? Auth);
