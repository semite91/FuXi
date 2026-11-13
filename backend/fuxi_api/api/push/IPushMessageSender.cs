using FuXi.Api.Database.Entities;

namespace FuXi.Api.Push;

/// <summary>Delivers one signed push message to the push service of one Push Subscription.</summary>
public interface IPushMessageSender
{
    /// <summary>Sends the payload. A refusal of the push service throws Lib.Net.Http.WebPush.PushServiceClientException with its status code.</summary>
    Task SendAsync(PushSubscription subscription, string payload, VapidDetails vapid, CancellationToken cancellationToken);
}
