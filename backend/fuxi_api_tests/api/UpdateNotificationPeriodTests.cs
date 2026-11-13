using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section M: UpdateNotificationPeriod and the notification timer behind it.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateNotificationPeriodTests : IDisposable
{
    private const string NEW_VALUE = "30";
    private const int NEW_PERIOD_MINUTES = 30;
    private const string TEXT_VALUE = "abc";
    private const string ZERO_VALUE = "0";
    private const string MAXIMUM_VALUE = "525600";
    private const int MAXIMUM_PERIOD_MINUTES = 525600;
    private const string ABOVE_MAXIMUM_VALUE = "525601";

    private static readonly TimeSpan NewInterval = TimeSpan.FromMinutes(NEW_PERIOD_MINUTES);

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task ValueIsStoredAndTimerRestartsOnceWithNewInterval()
    {
        // M1, M2
        var notificationPeriod = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE);

        await UpdateAsync(notificationPeriod.Id, NEW_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadConfig(TestData.NOTIFICATION_PERIOD_CODE).Value.Should().Be(NEW_VALUE);
        databaseApi.Timer.Intervals.Should().Equal(NewInterval);
    }

    [Fact]
    public async Task ValueIsSavedBeforeTimerRestarts()
    {
        // M3: the value is read through another connection at the moment of the restart.
        var notificationPeriod = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE);
        string? valueAtRestart = null;
        databaseApi.Timer.OnRestart = () => valueAtRestart = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE).Value;

        await UpdateAsync(notificationPeriod.Id, NEW_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        valueAtRestart.Should().Be(NEW_VALUE);
    }

    [Theory]
    [InlineData(TEXT_VALUE)] // M4
    [InlineData(ZERO_VALUE)] // M5
    [InlineData(ABOVE_MAXIMUM_VALUE)] // Review R5
    public async Task RejectedValueChangesNothingAndLeavesTimerAlone(string value)
    {
        // M4, M5, review R5
        var notificationPeriod = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE);

        await UpdateAsync(notificationPeriod.Id, value).ShouldBeProblemAsync(HttpStatusCode.BadRequest);

        ReadConfig(TestData.NOTIFICATION_PERIOD_CODE).Should().BeEquivalentTo(notificationPeriod);
        databaseApi.Timer.Intervals.Should().BeEmpty();
    }

    [Fact]
    public async Task MaximumValueIsStoredAndRestartsTimer()
    {
        // Review R5: one year in minutes is the largest period.
        var notificationPeriod = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE);

        await UpdateAsync(notificationPeriod.Id, MAXIMUM_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadConfig(TestData.NOTIFICATION_PERIOD_CODE).Value.Should().Be(MAXIMUM_VALUE);
        databaseApi.Timer.Intervals.Should().Equal(TimeSpan.FromMinutes(MAXIMUM_PERIOD_MINUTES));
    }

    [Fact]
    public async Task TimerRestartCannotBeCancelledByRequest()
    {
        // Review R6: once the value is stored, a client that disconnects must not stop the restart.
        var notificationPeriod = ReadConfig(TestData.NOTIFICATION_PERIOD_CODE);

        await UpdateAsync(notificationPeriod.Id, NEW_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        databaseApi.Timer.CancellationTokens.Should().ContainSingle().Which.CanBeCanceled.Should().BeFalse();
    }

    [Fact]
    public async Task IdOfOtherConfigRowIsBadRequest()
    {
        // M6
        var rotationPeriod = ReadConfig(TestData.ROTATION_PERIOD_CODE);

        await UpdateAsync(rotationPeriod.Id, NEW_VALUE).ShouldBeProblemAsync(HttpStatusCode.BadRequest);

        ReadConfig(TestData.ROTATION_PERIOD_CODE).Should().BeEquivalentTo(rotationPeriod);
        databaseApi.Timer.Intervals.Should().BeEmpty();
    }

    [Fact]
    public async Task UnknownConfigIsNotFound()
    {
        // M7
        await UpdateAsync(Guid.NewGuid(), NEW_VALUE).ShouldBeProblemAsync(HttpStatusCode.NotFound);

        databaseApi.Timer.Intervals.Should().BeEmpty();
    }

    [Fact]
    public async Task IdThatIsNotGuidIsBadRequest()
    {
        // M8
        await nowApi.Client
            .PostApiAsync(ApiRoutes.UPDATE_NOTIFICATION_PERIOD, new { id = ApiRequests.NOT_A_GUID, value = NEW_VALUE })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);

        nowApi.Host.Timer.Intervals.Should().BeEmpty();
    }

    [Fact]
    public void QuartzTimerIsRegisteredAsSingleton()
    {
        // M9, updated by Phase 4 C1: the Quartz.NET timer replaced the idle timer.
        using var api = new NowApi(new NowApiSettings { ReplacesServices = false });

        var timer = api.Services.GetRequiredService<INotificationTimer>();

        timer.Should().BeOfType<QuartzNotificationTimer>();
        api.Services.GetRequiredService<INotificationTimer>().Should().BeSameAs(timer);
    }

    [Fact]
    public async Task QuartzTimerRestartsWithoutError()
    {
        // M10, updated by Phase 4: the restart needs no database.
        using var api = new NowApi(new NowApiSettings { ReplacesServices = false });
        var timer = api.Services.GetRequiredService<INotificationTimer>();

        var restart = () => timer.RestartAsync(NewInterval, TestContext.Current.CancellationToken);

        await restart.Should().NotThrowAsync();
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Task<HttpResponseMessage> UpdateAsync(Guid id, string value) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_NOTIFICATION_PERIOD, new { id, value });

    private Config ReadConfig(string code) => databaseApi.Read(context => TestData.ConfigOf(context, code));
}
