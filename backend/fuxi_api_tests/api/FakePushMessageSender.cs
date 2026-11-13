using System.Collections.Concurrent;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;

namespace FuXi.Api.Tests.Api;

/// <summary>Records every push instead of calling a push service. A failure can be set per endpoint.</summary>
public sealed class FakePushMessageSender : IPushMessageSender
{
    private readonly ConcurrentQueue<SentPush> sent = new();
    private readonly ConcurrentDictionary<string, Exception> failures = new();

    /// <summary>Every call, in call order, failed ones included.</summary>
    public IReadOnlyList<SentPush> Sent => sent.ToList();

    /// <summary>From now on a push to this endpoint throws the exception.</summary>
    public void FailFor(string endpoint, Exception exception) => failures[endpoint] = exception;

    public Task SendAsync(PushSubscription subscription, string payload, VapidDetails vapid, CancellationToken cancellationToken)
    {
        sent.Enqueue(new SentPush(subscription, payload, vapid));

        return failures.TryGetValue(subscription.Endpoint, out var failure) ? Task.FromException(failure) : Task.CompletedTask;
    }
}

/// <summary>One call of <see cref="FakePushMessageSender"/>.</summary>
public sealed record SentPush(PushSubscription Subscription, string Payload, VapidDetails Vapid);
