using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section L: UpdateConfig.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateConfigTests : IDisposable
{
    private const string NEW_VALUE = "25";
    private const string TEXT_VALUE = "abc";
    private const string ZERO_VALUE = "0";
    private const string NEGATIVE_VALUE = "-5";
    private const string DECIMAL_VALUE = "1.5";
    private const string MAXIMUM_VALUE = "525600";
    private const string ABOVE_MAXIMUM_VALUE = "525601";

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task ValueIsStoredAndNothingElseChanges()
    {
        // L1, L2, L3
        var configsBefore = ReadConfigs();
        var rotationCount = configsBefore.Single(config => config.Code == TestData.ROTATION_COUNT_CODE);

        await UpdateAsync(rotationCount.Id, NEW_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var stored = ReadConfigs();
        stored.Single(config => config.Id == rotationCount.Id).Should()
            .BeEquivalentTo(rotationCount, options => options.Excluding(config => config.Value))
            .And.Match<Config>(config => config.Value == NEW_VALUE);
        stored.Where(config => config.Id != rotationCount.Id).Should()
            .BeEquivalentTo(configsBefore.Where(config => config.Id != rotationCount.Id));
    }

    [Theory]
    [InlineData(TEXT_VALUE)] // L4
    [InlineData(ZERO_VALUE)] // L5
    [InlineData(NEGATIVE_VALUE)] // L6
    [InlineData(DECIMAL_VALUE)] // L7
    [InlineData(ABOVE_MAXIMUM_VALUE)] // Review R5
    public async Task NumberRowRejectsValueThatIsNotWholeNumberAboveZero(string value)
    {
        // L4, L5, L6, L7, review R5
        var configsBefore = ReadConfigs();
        var rotationCount = configsBefore.Single(config => config.Code == TestData.ROTATION_COUNT_CODE);

        await UpdateAsync(rotationCount.Id, value).ShouldBeProblemAsync(HttpStatusCode.BadRequest);

        ReadConfigs().Should().BeEquivalentTo(configsBefore);
    }

    [Fact]
    public async Task NumberRowAcceptsMaximum()
    {
        // Review R5: one year in minutes is the largest number.
        var rotationPeriod = ReadConfigs().Single(config => config.Code == TestData.ROTATION_PERIOD_CODE);

        await UpdateAsync(rotationPeriod.Id, MAXIMUM_VALUE).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadConfigs().Single(config => config.Id == rotationPeriod.Id).Value.Should().Be(MAXIMUM_VALUE);
    }

    [Fact]
    public async Task NotificationPeriodRowIsBadRequestAndNotChanged()
    {
        // Review R6: that row changes only through UpdateNotificationPeriod, which also restarts the timer.
        var configsBefore = ReadConfigs();
        var notificationPeriod = configsBefore.Single(config => config.Code == TestData.NOTIFICATION_PERIOD_CODE);

        await UpdateAsync(notificationPeriod.Id, NEW_VALUE).ShouldBeProblemAsync(HttpStatusCode.BadRequest);

        ReadConfigs().Should().BeEquivalentTo(configsBefore);
        databaseApi.Timer.Intervals.Should().BeEmpty();
    }

    [Fact]
    public async Task UnknownConfigIsNotFound()
    {
        // L8
        var configsBefore = ReadConfigs();

        await UpdateAsync(Guid.NewGuid(), NEW_VALUE).ShouldBeProblemAsync(HttpStatusCode.NotFound);

        ReadConfigs().Should().BeEquivalentTo(configsBefore);
    }

    [Fact]
    public async Task IdThatIsNotGuidIsBadRequest()
    {
        // L9
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_CONFIG, new { id = ApiRequests.NOT_A_GUID, value = NEW_VALUE })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task EmptyValueIsBadRequest()
    {
        // L10
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_CONFIG, new { id = Guid.NewGuid(), value = string.Empty })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingValueIsBadRequest()
    {
        // L10
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_CONFIG, new { id = Guid.NewGuid() })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Task<HttpResponseMessage> UpdateAsync(Guid id, string value) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_CONFIG, new { id, value });

    private List<Config> ReadConfigs() => databaseApi.Read(context => context.Configs.AsNoTracking().ToList());
}
