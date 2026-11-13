using Lib.Net.Http.WebPush;
using Lib.Net.Http.WebPush.Authentication;

namespace FuXi.Api.Push;

/// <summary>Sends push messages with Lib.Net.Http.WebPush over an HttpClient from IHttpClientFactory.</summary>
public sealed class WebPushMessageSender(HttpClient httpClient) : IPushMessageSender
{
    /// <summary>The name of the HttpClient this sender gets from IHttpClientFactory.</summary>
    public const string HTTP_CLIENT_NAME = "PushService";

    /// <summary>How long one request to a push service may take.</summary>
    public static readonly TimeSpan REQUEST_TIMEOUT = TimeSpan.FromSeconds(30);

    public IPushRun StartRun(VapidDetails vapid)
    {
        var authentication = CreateAuthentication(vapid);

        return new WebPushRun(new PushServiceClient(httpClient) { DefaultAuthentication = authentication }, authentication);
    }

    private static VapidAuthentication CreateAuthentication(VapidDetails vapid)
    {
        var authentication = new VapidAuthentication(vapid.PublicKey, vapid.PrivateKey);
        try
        {
            if (vapid.Subject is not null)
            {
                authentication.Subject = vapid.Subject;
            }

            return authentication;
        }
        catch
        {
            authentication.Dispose();
            throw;
        }
    }

    // One client and one authentication for every push of the run; the authentication is disposed with the run.
    private sealed class WebPushRun(PushServiceClient pushServiceClient, VapidAuthentication authentication) : IPushRun
    {
        public Task SendAsync(Database.Entities.PushSubscription subscription, string payload, CancellationToken cancellationToken) =>
            pushServiceClient.RequestPushMessageDeliveryAsync(ToTarget(subscription), new PushMessage(payload), cancellationToken);

        public void Dispose() => authentication.Dispose();

        private static PushSubscription ToTarget(Database.Entities.PushSubscription subscription)
        {
            var target = new PushSubscription { Endpoint = subscription.Endpoint };
            target.SetKey(PushEncryptionKeyName.P256DH, subscription.P256dh);
            target.SetKey(PushEncryptionKeyName.Auth, subscription.Auth);

            return target;
        }
    }
}
