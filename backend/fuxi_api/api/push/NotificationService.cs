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

        // Words that do not fit in one push message stay Due and are sent by a later run.
        var payload = NotificationPayload.FittingJson(words);
        if (payload is null)
        {
            LogFirstWordTooLong(logger, words[0].Id, NotificationPayload.MAX_PAYLOAD_BYTES);
            return;
        }

        await SendToSubscriptionsAsync(payload, vapid, cancellationToken);
    }

    // A window holds now from its StartDate on, up to but not including its EndDate.
    private Task<bool> IsInsideNotificationWindowAsync(DateTimeOffset now, CancellationToken cancellationToken) =>
        database.Schedules.AsNoTracking().AnyAsync(schedule => schedule.StartDate <= now && schedule.EndDate > now, cancellationToken);

    // The pushes run in parallel (a single user has a handful of subscriptions, so they are not bounded) and never touch the
    // DbContext; the subscriptions the push services no longer know are deleted afterwards, in one statement.
    private async Task SendToSubscriptionsAsync(string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        var subscriptions = await ReadAllowedSubscriptionsAsync(cancellationToken);
        if (subscriptions.Count == 0)
        {
            return;
        }

        var unknownIds = await SendInParallelAsync(subscriptions, payload, vapid, cancellationToken);
        if (unknownIds.Count > 0)
        {
            await DeleteSubscriptionsAsync(unknownIds, cancellationToken);
        }
    }

    // One run, so the VAPID authentication is built once; it is disposed once every push answered.
    private async Task<IReadOnlyList<Guid>> SendInParallelAsync(
        IReadOnlyList<PushSubscription> subscriptions, string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        using var run = pushMessageSender.StartRun(vapid);
        var unknown = await Task.WhenAll(subscriptions.Select(subscription => SendAsync(run, subscription, payload, cancellationToken)));

        return subscriptions.Where((_, index) => unknown[index]).Select(subscription => subscription.Id).ToList();
    }

    // An endpoint of an unknown host is skipped, so the backend never calls it.
    private async Task<IReadOnlyList<PushSubscription>> ReadAllowedSubscriptionsAsync(CancellationToken cancellationToken)
    {
        var subscriptions = await database.PushSubscriptions.AsNoTracking().ToListAsync(cancellationToken);
        var allowed = new List<PushSubscription>(subscriptions.Count);
        foreach (var subscription in subscriptions)
        {
            if (PushHosts.IsAllowedEndpoint(subscription.Endpoint))
            {
                allowed.Add(subscription);
            }
            else
            {
                LogEndpointNotAllowed(logger, subscription.Id);
            }
        }

        return allowed;
    }

    // One failing subscription never stops the others. Returns true when the push service no longer knows the subscription.
    private async Task<bool> SendAsync(IPushRun run, PushSubscription subscription, string payload, CancellationToken cancellationToken)
    {
        try
        {
            await run.SendAsync(subscription, payload, cancellationToken);

            return false;
        }
        catch (PushServiceClientException exception) when (IsUnknownToPushService(exception.StatusCode))
        {
            return true;
        }
        catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
        {
            LogSendFailed(logger, exception, subscription.Id);

            return false;
        }
    }

    // 410 Gone and 404 Not Found: the push service no longer knows the subscription, so it can never be delivered to again.
    private static bool IsUnknownToPushService(HttpStatusCode statusCode) =>
        statusCode is HttpStatusCode.Gone or HttpStatusCode.NotFound;

    private Task<int> DeleteSubscriptionsAsync(IReadOnlyList<Guid> ids, CancellationToken cancellationToken) =>
        database.PushSubscriptions.Where(subscription => ids.Contains(subscription.Id)).ExecuteDeleteAsync(cancellationToken);

    [LoggerMessage(Level = LogLevel.Warning, Message = "VAPID_PUBLIC_KEY or VAPID_PRIVATE_KEY is empty, so no push notification is sent.")]
    private static partial void LogVapidKeysMissing(ILogger logger);

    [LoggerMessage(Level = LogLevel.Warning, Message = "The name of Word {WordId} alone makes the push message longer than {MaxBytes} bytes, so nothing is sent this run.")]
    private static partial void LogFirstWordTooLong(ILogger logger, Guid wordId, int maxBytes);

    [LoggerMessage(Level = LogLevel.Warning, Message = "Push Subscription {SubscriptionId} points to a host that is not a known push service; it is skipped.")]
    private static partial void LogEndpointNotAllowed(ILogger logger, Guid subscriptionId);

    [LoggerMessage(Level = LogLevel.Error, Message = "Push notification to Push Subscription {SubscriptionId} failed; the subscription is kept.")]
    private static partial void LogSendFailed(ILogger logger, Exception exception, Guid subscriptionId);
}
