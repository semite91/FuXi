using System.Diagnostics;
using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Push;
using FuXi.Api.Words;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Quartz;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 section C (test_scenarios_2026_11_12_22_06): the Quartz.NET timed task, without a database.</summary>
[Collection(nameof(SmokeTests))]
public sealed class NotificationTimerTests : IDisposable
{
    // Nothing listens on this port, so every run of the job fails fast.
    private const string UNREACHABLE_CONNECTION = "Host=127.0.0.1;Port=1;Database=fuxi_timer_test;Username=fuxi;Password=not-a-secret";
    private const string IDLE_TIMER_TYPE = "FuXi.Api.Push.IdleNotificationTimer";
    private const string RAM_JOB_STORE_TYPE = "Quartz.Impl.RAMJobStore";
    private const string TEST_KEY = "configured-key-of-a-test";
    private const int REQUIRED_FAILED_RUNS = 2;
    private static readonly TimeSpan ShortInterval = TimeSpan.FromMilliseconds(200);
    private static readonly TimeSpan LongInterval = TimeSpan.FromHours(1);
    private static readonly TimeSpan WaitLimit = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan PollDelay = TimeSpan.FromMilliseconds(50);

    private readonly RecordingLoggerProvider logs = new();
    private readonly ServiceProvider services;

    public NotificationTimerTests() => services = CreateServices(logs);

    private QuartzNotificationTimer Timer => services.GetRequiredService<QuartzNotificationTimer>();

    private static CancellationToken Token => TestContext.Current.CancellationToken;

    [Fact]
    public void ApiRegistersQuartzTimerAsNotificationTimerAndHostedService()
    {
        // C1
        var collection = new ServiceCollection().AddLogging();
        collection.AddFuXiApi();
        using var provider = collection.BuildServiceProvider();

        var timer = provider.GetRequiredService<INotificationTimer>();

        timer.Should().BeOfType<QuartzNotificationTimer>();
        provider.GetRequiredService<INotificationTimer>().Should().BeSameAs(timer);
        provider.GetServices<IHostedService>().Should().Contain(service => ReferenceEquals(service, timer));
        typeof(Program).Assembly.GetType(IDLE_TIMER_TYPE).Should().BeNull();
    }

    [Fact]
    public async Task SchedulerUsesRamJobStore()
    {
        // C2
        await Timer.RestartAsync(LongInterval, Token);

        var metadata = await Timer.ReadMetadataAsync(Token);

        metadata!.JobStoreTypeName.Should().StartWith(RAM_JOB_STORE_TYPE);
        metadata.JobStorePersistent.Should().BeFalse();
    }

    [Fact]
    public async Task JobDoesNotRunConcurrently()
    {
        // C7
        await Timer.RestartAsync(LongInterval, Token);

        var job = await Timer.ReadJobAsync(Token);

        job!.ConcurrentExecutionDisallowed.Should().BeTrue();
        typeof(NotificationJob).IsDefined(typeof(DisallowConcurrentExecutionAttribute), inherit: false).Should().BeTrue();
    }

    [Fact]
    public async Task FailedRunIsLoggedAndNextRunStillFires()
    {
        // C8: every run fails on the unreachable database; the job keeps firing and logs each failure.
        await Timer.RestartAsync(ShortInterval, Token);

        var failedRuns = await WaitForFailedRunsAsync(REQUIRED_FAILED_RUNS);

        failedRuns.Should().BeGreaterThanOrEqualTo(REQUIRED_FAILED_RUNS);
        (await Timer.ReadTriggersAsync(Token)).Should().ContainSingle();
    }

    [Fact]
    public async Task StopShutsSchedulerDown()
    {
        // C9
        await Timer.RestartAsync(LongInterval, Token);

        await Timer.StopAsync(Token);

        Timer.IsShutDown.Should().BeTrue();
    }

    [Fact]
    public async Task UnreachableDatabaseAtStartLogsErrorAndLaterRestartCreatesTrigger()
    {
        // C10: the Notification Period cannot be read because the database is down.
        var start = () => Timer.StartAsync(Token);

        await start.Should().NotThrowAsync();

        logs.Of(typeof(QuartzNotificationTimer).FullName!).Should().ContainSingle(entry => entry.Level == LogLevel.Error);
        (await Timer.ReadTriggersAsync(Token)).Should().BeEmpty();

        await Timer.RestartAsync(LongInterval, Token);

        (await Timer.ReadTriggersAsync(Token)).Should().ContainSingle();
    }

    [Fact]
    public async Task CancelledStartIsNotSwallowed()
    {
        // C10: a start that the host cancels still ends with the cancellation.
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();

        var start = () => Timer.StartAsync(cancellation.Token);

        await start.Should().ThrowAsync<OperationCanceledException>();
    }

    [Fact]
    public async Task RestartOfStoppedTimerCreatesNoTrigger()
    {
        // C11: the host stopped the timer before it was ever started; a late restart must not start a new scheduler.
        await Timer.StopAsync(Token);

        var restart = () => Timer.RestartAsync(LongInterval, Token);

        await restart.Should().NotThrowAsync();
        (await Timer.ReadTriggersAsync(Token)).Should().BeEmpty();
        logs.Of(typeof(QuartzNotificationTimer).FullName!).Should().ContainSingle(entry => entry.Level == LogLevel.Warning);
    }

    [Fact]
    public async Task RestartOfShutDownSchedulerDoesNotThrow()
    {
        // C11: the scheduler was shut down; a late restart leaves it alone.
        await Timer.RestartAsync(LongInterval, Token);
        await Timer.StopAsync(Token);

        var restart = () => Timer.RestartAsync(LongInterval, Token);

        await restart.Should().NotThrowAsync();
        Timer.IsShutDown.Should().BeTrue();
        logs.Of(typeof(QuartzNotificationTimer).FullName!).Should().ContainSingle(entry => entry.Level == LogLevel.Warning);
    }

    [Fact]
    public async Task RestartAfterDisposeDoesNotThrow()
    {
        // C11: a request that arrives while the host disposes the timer.
        await Timer.RestartAsync(LongInterval, Token);
        await Timer.DisposeAsync();

        var restart = () => Timer.RestartAsync(LongInterval, Token);

        await restart.Should().NotThrowAsync();
    }

    public void Dispose()
    {
        services.Dispose();
        logs.Dispose();
    }

    private async Task<int> WaitForFailedRunsAsync(int count)
    {
        var watch = Stopwatch.StartNew();
        while (FailedRuns() < count && watch.Elapsed < WaitLimit)
        {
            await Task.Delay(PollDelay, Token);
        }

        return FailedRuns();
    }

    private int FailedRuns() =>
        logs.Of(typeof(NotificationJob).FullName!).Count(entry => entry.Level == LogLevel.Error && entry.Exception is not null);

    // The parts the job needs, with VAPID keys so a run goes on to the database.
    private static ServiceProvider CreateServices(RecordingLoggerProvider logs)
    {
        var collection = new ServiceCollection();
        collection.AddLogging(logging => logging.AddProvider(logs));
        collection.AddSingleton<IConfiguration>(new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                [VapidSettings.PUBLIC_KEY_KEY] = TEST_KEY,
                [VapidSettings.PRIVATE_KEY_KEY] = TEST_KEY,
            })
            .Build());
        collection.AddSingleton(TimeProvider.System);
        collection.AddFuXiDatabase(UNREACHABLE_CONNECTION);
        collection.AddScoped<WordService>();
        collection.AddScoped<NotificationService>();
        collection.AddScoped<NotificationJob>();
        collection.AddSingleton<IPushMessageSender>(new FakePushMessageSender());
        collection.AddSingleton<QuartzNotificationTimer>();

        return collection.BuildServiceProvider();
    }
}
