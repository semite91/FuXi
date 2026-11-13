using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Push;

/// <summary>The Push Subscription logic behind the push endpoints.</summary>
public sealed class PushService(FuXiDbContext database, IConfiguration configuration, TimeProvider timeProvider)
{
    private const string FIELD_MISSING = "endpoint, p256dh and auth are required.";
    private const string ENDPOINT_NOT_ALLOWED = "endpoint must be an https URL of a known push service.";

    /// <summary>Returns the configured VAPID public key, or the placeholder when none is configured.</summary>
    public VapidPublicKey GetVapidPublicKey()
    {
        var publicKey = configuration[VapidSettings.PUBLIC_KEY_KEY];

        return new VapidPublicKey(string.IsNullOrWhiteSpace(publicKey) ? VapidSettings.PLACEHOLDER_PUBLIC_KEY : publicKey);
    }

    /// <summary>Saves a Push Subscription. An endpoint that is already saved is left as it is.</summary>
    public async Task SavePushSubscriptionAsync(SavePushSubscriptionRequest request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.Endpoint) || string.IsNullOrWhiteSpace(request.P256dh) || string.IsNullOrWhiteSpace(request.Auth))
        {
            throw ApiException.BadRequest(FIELD_MISSING);
        }

        if (!PushHosts.IsAllowedEndpoint(request.Endpoint))
        {
            throw ApiException.BadRequest(ENDPOINT_NOT_ALLOWED);
        }

        if (await database.PushSubscriptions.AnyAsync(subscription => subscription.Endpoint == request.Endpoint, cancellationToken))
        {
            return;
        }

        database.PushSubscriptions.Add(new PushSubscription
        {
            Endpoint = request.Endpoint,
            P256dh = request.P256dh,
            Auth = request.Auth,
            CreatedDate = timeProvider.GetUtcNow(),
        });
        await database.SaveChangesAsync(cancellationToken);
    }
}
