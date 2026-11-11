namespace FuXi.Api.Push;

/// <summary>The timed task that sends push notifications. Phase 4 implements it with Quartz.NET.</summary>
public interface INotificationTimer
{
    /// <summary>Stops the timed task and starts it again with the new interval.</summary>
    Task RestartAsync(TimeSpan interval, CancellationToken cancellationToken);
}
