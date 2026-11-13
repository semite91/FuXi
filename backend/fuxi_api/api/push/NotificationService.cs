using System.Net;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.Words;
using PushServiceClientException = Lib.Net.Http.WebPush.PushServiceClientException;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Push;

/// <summary>One run of the timed task: sends the Due Words to every Push Subscription while a Notification Window is open.</summary>
public sealed partial class NotificationService(
    FuXiDbContext database,
    WordService wordService,
    IPushMessageSender pushMessageSender,
    IConfiguration configuration,
    TimeProvider timeProvider,
    ILogger<NotificationService> logger)
{
    /// <summary>Sends nothing when VAPID keys are missing, no Notification Window holds now, or no Word is Due.</summary>
    public async Task SendDueWordsAsync(CancellationToken cancellationToken)
    {
        // Checked first: without keys nothing can be signed, so the Rotation is left alone.
        var vapid = VapidSettings.ReadDetails(configuration);
        if (vapid is null)
        {
            LogVapidKeysMissing(logger);
            return;
        }

        var now = timeProvider.GetUtcNow();
        if (!await IsInsideNotificationWindowAsync(now, cancellationToken))
        {
            return;
        }

        var words = await wordService.GetNotificationWordsAsync(now, cancellationToken);
        if (words.Count == 0)
        {
            return;
        }

        await SendToSubscriptionsAsync(NotificationPayload.From(words).ToJson(), vapid, cancellationToken);
    }

    // A window holds now from its StartDate on, up to but not including its EndDate.
    private Task<bool> IsInsideNotificationWindowAsync(DateTimeOffset now, CancellationToken cancellationToken) =>
        database.Schedules.AsNoTracking().AnyAsync(schedule => schedule.StartDate <= now && schedule.EndDate > now, cancellationToken);

    private async Task SendToSubscriptionsAsync(string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        var subscriptions = await database.PushSubscriptions.AsNoTracking().ToListAsync(cancellationToken);
        foreach (var subscription in subscriptions)
        {
            await SendAsync(subscription, payload, vapid, cancellationToken);
        }
    }

    // One failing subscription never stops the others. 410 Gone means the browser dropped it, so it is deleted.
    private async Task SendAsync(PushSubscription subscription, string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        if (!PushHosts.IsAllowedEndpoint(subscription.Endpoint))
        {
            LogEndpointNotAllowed(logger, subscription.Id);
            return;
        }

        try
        {
            await pushMessageSender.SendAsync(subscription, payload, vapid, cancellationToken);
        }
        catch (PushServiceClientException exception) when (exception.StatusCode == HttpStatusCode.Gone)
        {
            await DeleteSubscriptionAsync(subscription.Id, cancellationToken);
        }
        catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
        {
            LogSendFailed(logger, exception, subscription.Id);
        }
    }

    private Task<int> DeleteSubscriptionAsync(Guid id, CancellationToken cancellationToken) =>
        database.PushSubscriptions.Where(subscription => subscription.Id == id).ExecuteDeleteAsync(cancellationToken);

    [LoggerMessage(Level = LogLevel.Warning, Message = "VAPID_PUBLIC_KEY or VAPID_PRIVATE_KEY is empty, so no push notification is sent.")]
    private static partial void LogVapidKeysMissing(ILogger logger);

    [LoggerMessage(Level = LogLevel.Warning, Message = "Push Subscription {SubscriptionId} points to a host that is not a known push service; it is skipped.")]
    private static partial void LogEndpointNotAllowed(ILogger logger, Guid subscriptionId);

    [LoggerMessage(Level = LogLevel.Error, Message = "Push notification to Push Subscription {SubscriptionId} failed; the subscription is kept.")]
    private static partial void LogSendFailed(ILogger logger, Exception exception, Guid subscriptionId);
}
