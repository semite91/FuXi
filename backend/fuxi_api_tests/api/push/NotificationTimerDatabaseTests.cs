using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Quartz;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 section C (test_scenarios_2026_11_12_22_06): the started Quartz.NET timer on the test database, with a fake clock.</summary>
[Collection(nameof(SmokeTests))]
public sealed class NotificationTimerDatabaseTests : IDisposable
{
    private const int SEEDED_PERIOD_MINUTES = 15;
    private const string NEW_VALUE = "30";
    private const int NEW_PERIOD_MINUTES = 30;

    // Less than the period, so the fake clock never reaches a fire time.
    private const int MINUTES_BEFORE_RESTART = 10;

    private readonly DatabaseApi api = new(startsNotificationTimer: true);

    private static CancellationToken Token => TestContext.Current.CancellationToken;

    [Fact]
    public async Task StartCreatesOneTriggerWithNotificationPeriod()
    {
        // C3
        var trigger = await SingleTriggerAsync();

        trigger.RepeatInterval.Should().Be(TimeSpan.FromMinutes(SEEDED_PERIOD_MINUTES));
    }

    [Fact]
    public async Task FirstFireIsOnePeriodAfterStart()
    {
        // C4
        var trigger = await SingleTriggerAsync();

        trigger.StartTimeUtc.Should().Be(TestData.Now.AddMinutes(SEEDED_PERIOD_MINUTES));
        trigger.NextFireTimeUtc.Should().Be(TestData.Now.AddMinutes(SEEDED_PERIOD_MINUTES));
    }

    [Fact]
    public async Task UpdateNotificationPeriodLeavesOneTriggerWithNewInterval()
    {
        // C5
        await UpdateNotificationPeriodAsync();

        var trigger = await SingleTriggerAsync();

        trigger.RepeatInterval.Should().Be(TimeSpan.FromMinutes(NEW_PERIOD_MINUTES));
    }

    [Fact]
    public async Task FirstFireAfterRestartIsOneNewPeriodAfterRestart()
    {
        // C6
        _ = await SingleTriggerAsync();
        api.Clock.Advance(TimeSpan.FromMinutes(MINUTES_BEFORE_RESTART));
        var restartTime = api.Clock.GetUtcNow();

        await UpdateNotificationPeriodAsync();

        var trigger = await SingleTriggerAsync();
        trigger.NextFireTimeUtc.Should().Be(restartTime.AddMinutes(NEW_PERIOD_MINUTES));
    }

    [Fact]
    public async Task HostStopShutsSchedulerDown()
    {
        // C9
        _ = await SingleTriggerAsync();
        var timer = api.NotificationTimer;

        api.Dispose();

        timer.IsShutDown.Should().BeTrue();
    }

    public void Dispose() => api.Dispose();

    private async Task<ISimpleTrigger> SingleTriggerAsync()
    {
        var triggers = await api.NotificationTimer.ReadTriggersAsync(Token);

        return triggers.Should().ContainSingle().Which.Should().BeAssignableTo<ISimpleTrigger>().Subject;
    }

    private async Task UpdateNotificationPeriodAsync()
    {
        var notificationPeriod = api.Read(context => TestData.ConfigOf(context, ConfigCodes.NOTIFICATION_PERIOD));

        await api.Client.PostApiAsync(ApiRoutes.UPDATE_NOTIFICATION_PERIOD, new { id = notificationPeriod.Id, value = NEW_VALUE })
            .ShouldHaveStatusAsync(HttpStatusCode.NoContent);
    }
}
