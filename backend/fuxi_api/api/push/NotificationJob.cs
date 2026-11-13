using Quartz;

namespace FuXi.Api.Push;

/// <summary>The Quartz.NET job of the timed task. A failed run is logged and never stops the next run.</summary>
[DisallowConcurrentExecution]
public sealed partial class NotificationJob(NotificationService notificationService, ILogger<NotificationJob> logger) : IJob
{
    public async ValueTask Execute(IJobExecutionContext context, CancellationToken cancellationToken = default)
    {
        try
        {
            await notificationService.SendDueWordsAsync(cancellationToken);
        }
        catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
        {
            // Swallowed on purpose: a job that throws is not retried and its trigger stays as it is either way, but the error is visible here.
            LogRunFailed(logger, exception);
        }
    }

    [LoggerMessage(Level = LogLevel.Error, Message = "The push notification run failed.")]
    private static partial void LogRunFailed(ILogger logger, Exception exception);
}
