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

    public async Task SendAsync(Database.Entities.PushSubscription subscription, string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        using var authentication = CreateAuthentication(vapid);
        var pushServiceClient = new PushServiceClient(httpClient);

        await pushServiceClient.RequestPushMessageDeliveryAsync(ToTarget(subscription), new PushMessage(payload), authentication, cancellationToken);
    }

    private static VapidAuthentication CreateAuthentication(VapidDetails vapid)
    {
        var authentication = new VapidAuthentication(vapid.PublicKey, vapid.PrivateKey);
        if (vapid.Subject is not null)
        {
            authentication.Subject = vapid.Subject;
        }

        return authentication;
    }

    private static PushSubscription ToTarget(Database.Entities.PushSubscription subscription)
    {
        var target = new PushSubscription { Endpoint = subscription.Endpoint };
        target.SetKey(PushEncryptionKeyName.P256DH, subscription.P256dh);
        target.SetKey(PushEncryptionKeyName.Auth, subscription.Auth);

        return target;
    }
}
