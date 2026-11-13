using FuXi.Api.Configs;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Quartz;

namespace FuXi.Api.Push;

/// <summary>
/// The timed task on Quartz.NET with the in-memory (RAM) job store. At startup it schedules one repeating trigger from the
/// Notification Period; a restart replaces that trigger. The first run always comes one period after the start or restart.
/// Start, restart and stop share one lock, and once stopped the timer never schedules again.
/// </summary>
public sealed partial class QuartzNotificationTimer(IServiceScopeFactory scopeFactory, TimeProvider timeProvider, ILogger<QuartzNotificationTimer> logger)
    : INotificationTimer, IHostedService, IAsyncDisposable, IDisposable
{
    public const string JOB_NAME = "SendNotifications";
    public const string TRIGGER_NAME = "NotificationPeriod";

    public static readonly JobKey JOB_KEY = new(JOB_NAME);
    public static readonly TriggerKey TRIGGER_KEY = new(TRIGGER_NAME);

    // Never disposed: it holds no wait handle, and a disposed lock would make a late RestartAsync throw.
    private readonly SemaphoreSlim schedulerLock = new(1, 1);
    private StandaloneSchedulerFactory? schedulerFactory;
    private IScheduler? scheduler;

    // The scheduler StopAsync took out, kept only to report its status.
    private IScheduler? stoppedScheduler;
    private bool isStopped;

    /// <summary>True once the scheduler was shut down.</summary>
    public bool IsShutDown => stoppedScheduler?.Status == SchedulerStatus.Shutdown;

    /// <summary>
    /// Reads the Notification Period and schedules the trigger. When the period cannot be read (database down, value missing
    /// or not a number) the error is logged and the API starts without a trigger; UpdateNotificationPeriod creates it later.
    /// </summary>
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        int minutes;
        try
        {
            minutes = await ReadNotificationPeriodAsync(cancellationToken);
        }
        catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
        {
            LogNotificationPeriodUnreadable(logger, exception);
            return;
        }

        await RestartAsync(TimeSpan.FromMinutes(minutes), cancellationToken);
    }

    /// <summary>Replaces the trigger. After the timer was stopped it only logs a warning, because the scheduler is gone.</summary>
    public async Task RestartAsync(TimeSpan interval, CancellationToken cancellationToken)
    {
        await schedulerLock.WaitAsync(cancellationToken);
        try
        {
            if (isStopped)
            {
                LogRestartAfterStop(logger);
                return;
            }

            var running = scheduler ??= await StartSchedulerAsync(cancellationToken);

            // Replacing the job with the same trigger key leaves exactly one trigger.
            await running.ScheduleJob(BuildJob(), [BuildTrigger(interval)], new ScheduleJobOptions { Replace = true }, cancellationToken);
        }
        finally
        {
            schedulerLock.Release();
        }
    }

    /// <summary>The triggers of the notification job; empty before the first start.</summary>
    public async Task<IReadOnlyList<ITrigger>> ReadTriggersAsync(CancellationToken cancellationToken) =>
        scheduler is null ? [] : await scheduler.GetTriggersOfJob(JOB_KEY, cancellationToken);

    /// <summary>The detail of the notification job, or null before the first start.</summary>
    public async Task<IJobDetail?> ReadJobAsync(CancellationToken cancellationToken) =>
        scheduler is null ? null : await scheduler.GetJobDetail(JOB_KEY, cancellationToken);

    /// <summary>What the scheduler reports about itself, such as its job store, or null before the first start.</summary>
    public async Task<SchedulerMetadata?> ReadMetadataAsync(CancellationToken cancellationToken) =>
        scheduler is null ? null : await scheduler.GetMetadata(cancellationToken);

    /// <summary>
    /// Marks the timer stopped, shuts the scheduler down and lets a running job finish. The lock is held only to take the
    /// scheduler out, so a RestartAsync during the wait returns at once instead of waiting for the job.
    /// </summary>
    public async Task StopAsync(CancellationToken cancellationToken)
    {
        IScheduler? stopping;
        await schedulerLock.WaitAsync(cancellationToken);
        try
        {
            isStopped = true;
            stopping = scheduler;
            scheduler = null;
            stoppedScheduler ??= stopping;
        }
        finally
        {
            schedulerLock.Release();
        }

        if (stopping is not null)
        {
            await stopping.Shutdown(waitForJobsToComplete: true, cancellationToken);
        }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync(CancellationToken.None);
        await schedulerLock.WaitAsync();
        try
        {
            if (schedulerFactory is not null)
            {
                await schedulerFactory.DisposeAsync();
                schedulerFactory = null;
            }
        }
        finally
        {
            schedulerLock.Release();
        }
    }

    public void Dispose() => DisposeAsync().AsTask().GetAwaiter().GetResult();

    private async Task<IScheduler> StartSchedulerAsync(CancellationToken cancellationToken)
    {
        schedulerFactory = QuartzSchedulerBuilder.Create(quartz =>
        {
            quartz.UseInMemoryStore();
            quartz.UseTimeProvider(timeProvider);
            quartz.UseJobFactory(new NotificationJobFactory(scopeFactory));
        }).Build();
        var created = await schedulerFactory.GetScheduler(cancellationToken);
        await created.Start(cancellationToken);

        return created;
    }

    private static IJobDetail BuildJob() =>
        JobBuilder.Create<NotificationJob>().WithIdentity(JOB_KEY).Build();

    private ITrigger BuildTrigger(TimeSpan interval) =>
        TriggerBuilder.Create(timeProvider)
            .WithIdentity(TRIGGER_KEY)
            .ForJob(JOB_KEY)
            .StartAt(timeProvider.GetUtcNow().Add(interval))
            .WithSchedule(SimpleScheduleBuilder.Create().WithInterval(interval).RepeatForever())
            .Build();

    private async Task<int> ReadNotificationPeriodAsync(CancellationToken cancellationToken)
    {
        await using var scope = scopeFactory.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<FuXiDbContext>();
        var value = await database.Configs.AsNoTracking()
            .Where(config => config.Code == ConfigCodes.NOTIFICATION_PERIOD)
            .Select(config => config.Value)
            .SingleOrDefaultAsync(cancellationToken);

        return value is not null && ConfigValue.TryParseNumber(value, out var minutes)
            ? minutes
            : throw new InvalidOperationException($"Config value {ConfigCodes.NOTIFICATION_PERIOD} is missing or is not a whole number.");
    }

    [LoggerMessage(Level = LogLevel.Error, Message = "The Notification Period could not be read at startup, so no push notification is scheduled until it is updated.")]
    private static partial void LogNotificationPeriodUnreadable(ILogger logger, Exception exception);

    [LoggerMessage(Level = LogLevel.Warning, Message = "The notification timer is stopped, so the new Notification Period is saved but not scheduled.")]
    private static partial void LogRestartAfterStop(ILogger logger);
}
