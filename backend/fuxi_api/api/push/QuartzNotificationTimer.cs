using FuXi.Api.Configs;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Quartz;

namespace FuXi.Api.Push;

/// <summary>
/// The timed task on Quartz.NET with the in-memory (RAM) job store. At startup it schedules one repeating trigger from the
/// Notification Period; a restart replaces that trigger. The first run always comes one period after the start or restart.
/// </summary>
public sealed class QuartzNotificationTimer(IServiceScopeFactory scopeFactory, TimeProvider timeProvider)
    : INotificationTimer, IHostedService, IAsyncDisposable, IDisposable
{
    public const string JOB_NAME = "SendNotifications";
    public const string TRIGGER_NAME = "NotificationPeriod";

    public static readonly JobKey JOB_KEY = new(JOB_NAME);
    public static readonly TriggerKey TRIGGER_KEY = new(TRIGGER_NAME);

    private readonly SemaphoreSlim schedulerLock = new(1, 1);
    private StandaloneSchedulerFactory? schedulerFactory;
    private IScheduler? scheduler;

    /// <summary>True once the scheduler was shut down.</summary>
    public bool IsShutDown => scheduler?.Status == SchedulerStatus.Shutdown;

    /// <summary>Reads the Notification Period and schedules the trigger.</summary>
    public async Task StartAsync(CancellationToken cancellationToken) =>
        await RestartAsync(TimeSpan.FromMinutes(await ReadNotificationPeriodAsync(cancellationToken)), cancellationToken);

    public async Task RestartAsync(TimeSpan interval, CancellationToken cancellationToken)
    {
        await schedulerLock.WaitAsync(cancellationToken);
        try
        {
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

    /// <summary>Shuts the scheduler down and lets a running job finish.</summary>
    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (scheduler is not null && scheduler.Status != SchedulerStatus.Shutdown)
        {
            await scheduler.Shutdown(waitForJobsToComplete: true, cancellationToken);
        }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync(CancellationToken.None);
        if (schedulerFactory is not null)
        {
            await schedulerFactory.DisposeAsync();
        }

        schedulerLock.Dispose();
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
}
