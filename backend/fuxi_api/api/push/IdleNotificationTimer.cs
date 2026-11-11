namespace FuXi.Api.Push;

/// <summary>A timer that does nothing. It stands in until Phase 4 adds the Quartz.NET timed task.</summary>
public sealed class IdleNotificationTimer : INotificationTimer
{
    public Task RestartAsync(TimeSpan interval, CancellationToken cancellationToken) => Task.CompletedTask;
}
