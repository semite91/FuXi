using FuXi.Api.Database.Entities;

namespace FuXi.Api.Push;

/// <summary>Delivers signed push messages to the push services of Push Subscriptions. Pushes may be sent in parallel.</summary>
public interface IPushMessageSender
{
    /// <summary>
    /// Signs the push with its own VAPID authentication and sends the payload. A refusal of the push service throws
    /// Lib.Net.Http.WebPush.PushServiceClientException with its status code.
    /// </summary>
    Task SendAsync(PushSubscription subscription, string payload, VapidDetails vapid, CancellationToken cancellationToken);
}
