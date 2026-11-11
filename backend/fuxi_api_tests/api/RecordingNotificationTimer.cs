using FuXi.Api.Push;

namespace FuXi.Api.Tests.Api;

/// <summary>Remembers every restart instead of running a timed task.</summary>
public sealed class RecordingNotificationTimer : INotificationTimer
{
    private readonly List<TimeSpan> intervals = [];
    private readonly List<CancellationToken> cancellationTokens = [];

    public IReadOnlyList<TimeSpan> Intervals => intervals;

    /// <summary>The token of every restart, in the order of <see cref="Intervals"/>.</summary>
    public IReadOnlyList<CancellationToken> CancellationTokens => cancellationTokens;

    /// <summary>Runs at the moment of a restart, so a test can look at the state the API left behind.</summary>
    public Action? OnRestart { get; set; }

    public Task RestartAsync(TimeSpan interval, CancellationToken cancellationToken)
    {
        OnRestart?.Invoke();
        intervals.Add(interval);
        cancellationTokens.Add(cancellationToken);

        return Task.CompletedTask;
    }
}
