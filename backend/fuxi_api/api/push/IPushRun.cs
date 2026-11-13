using FuXi.Api.Database.Entities;

namespace FuXi.Api.Push;

/// <summary>The pushes of one run, all signed with the same VAPID authentication. Pushes may be sent in parallel.</summary>
public interface IPushRun : IDisposable
{
    /// <summary>Sends the payload. A refusal of the push service throws Lib.Net.Http.WebPush.PushServiceClientException with its status code.</summary>
    Task SendAsync(PushSubscription subscription, string payload, CancellationToken cancellationToken);
}
