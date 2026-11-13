using System.Collections.Concurrent;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;

namespace FuXi.Api.Tests.Api;

/// <summary>Records every push instead of calling a push service. A failure or a hold can be set per endpoint.</summary>
public sealed class FakePushMessageSender : IPushMessageSender
{
    private readonly ConcurrentQueue<SentPush> sent = new();
    private readonly ConcurrentDictionary<string, Exception> failures = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource> holds = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource> calls = new();
    private int runsStarted;
    private int runsDisposed;

    /// <summary>Every call, in call order, failed and held ones included.</summary>
    public IReadOnlyList<SentPush> Sent => sent.ToList();

    /// <summary>How many runs were started, which is how often the VAPID authentication was built.</summary>
    public int RunsStarted => Volatile.Read(ref runsStarted);

    public int RunsDisposed => Volatile.Read(ref runsDisposed);

    /// <summary>From now on a push to this endpoint throws the exception.</summary>
    public void FailFor(string endpoint, Exception exception) => failures[endpoint] = exception;

    /// <summary>From now on a push to this endpoint does not answer until the returned source is completed.</summary>
    public TaskCompletionSource HoldFor(string endpoint) =>
        holds.GetOrAdd(endpoint, _ => new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously));

    /// <summary>Completes once a push to this endpoint was called, whether it answered yet or not.</summary>
    public Task CalledAsync(string endpoint) => CallOf(endpoint).Task;

    public IPushRun StartRun(VapidDetails vapid)
    {
        Interlocked.Increment(ref runsStarted);

        return new FakePushRun(this, vapid);
    }

    private TaskCompletionSource CallOf(string endpoint) =>
        calls.GetOrAdd(endpoint, _ => new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously));

    private async Task SendAsync(PushSubscription subscription, string payload, VapidDetails vapid)
    {
        sent.Enqueue(new SentPush(subscription, payload, vapid));
        CallOf(subscription.Endpoint).TrySetResult();
        if (holds.TryGetValue(subscription.Endpoint, out var hold))
        {
            await hold.Task;
        }

        if (failures.TryGetValue(subscription.Endpoint, out var failure))
        {
            throw failure;
        }
    }

    private sealed class FakePushRun(FakePushMessageSender sender, VapidDetails vapid) : IPushRun
    {
        public Task SendAsync(PushSubscription subscription, string payload, CancellationToken cancellationToken) =>
            sender.SendAsync(subscription, payload, vapid);

        public void Dispose() => Interlocked.Increment(ref sender.runsDisposed);
    }
}

/// <summary>One call of <see cref="FakePushMessageSender"/>.</summary>
public sealed record SentPush(PushSubscription Subscription, string Payload, VapidDetails Vapid);
