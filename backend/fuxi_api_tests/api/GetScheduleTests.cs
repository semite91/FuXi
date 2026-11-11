using System.Net;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section N: GetSchedule. The period runs from 10:00 to 14:00.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetScheduleTests : IDisposable
{
    private const int FAR_BEFORE = 8;
    private const int BEFORE = 9;
    private const int PERIOD_START = 10;
    private const int EARLY_INSIDE = 11;
    private const int LATE_INSIDE = 13;
    private const int PERIOD_END = 14;
    private const int AFTER = 15;
    private const int FAR_AFTER = 16;
    private const int LOCAL_OFFSET_HOURS = 3;
    private const string NOT_A_DATE = "not-a-date";
    private static readonly string[] ITEM_FIELDS = [ApiFields.ID, ApiFields.START_DATE, ApiFields.END_DATE];

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Theory]
    [InlineData(EARLY_INSIDE, LATE_INSIDE, true)] // N1
    [InlineData(BEFORE, EARLY_INSIDE, true)] // N2
    [InlineData(LATE_INSIDE, AFTER, true)] // N3
    [InlineData(BEFORE, AFTER, true)] // N4
    [InlineData(FAR_BEFORE, BEFORE, false)] // N5
    [InlineData(AFTER, FAR_AFTER, false)] // N6
    [InlineData(BEFORE, PERIOD_START, false)] // N7
    [InlineData(PERIOD_END, AFTER, false)] // N8
    public async Task WindowIsReturnedWhenItOverlapsPeriod(int startHour, int endHour, bool isReturned)
    {
        // N1, N2, N3, N4, N5, N6, N7, N8
        var window = databaseApi.Arrange(context =>
            TestData.AddSchedule(context, TestData.TimeOfDay(startHour), TestData.TimeOfDay(endHour)));

        var items = await GetScheduleAsync();

        items.Ids().Contains(window.Id).Should().Be(isReturned);
    }

    [Fact]
    public async Task ItemHoldsIdAndUtcDates()
    {
        // N9, N10: the window is stored from a date-time with a non-zero offset.
        var offset = TimeSpan.FromHours(LOCAL_OFFSET_HOURS);
        var window = databaseApi.Arrange(context => TestData.AddSchedule(
            context, TestData.TimeOfDay(EARLY_INSIDE).ToOffset(offset), TestData.TimeOfDay(LATE_INSIDE).ToOffset(offset)));

        var item = (await GetScheduleAsync()).Should().ContainSingle().Subject;

        item.FieldNames().Should().BeEquivalentTo(ITEM_FIELDS);
        item.GuidOf(ApiFields.ID).Should().Be(window.Id);
        item.Date(ApiFields.START_DATE).Should().Be(TestData.TimeOfDay(EARLY_INSIDE));
        item.Date(ApiFields.END_DATE).Should().Be(TestData.TimeOfDay(LATE_INSIDE));
        item.Date(ApiFields.START_DATE)!.Value.Offset.Should().Be(TimeSpan.Zero);
        item.Date(ApiFields.END_DATE)!.Value.Offset.Should().Be(TimeSpan.Zero);
    }

    [Fact]
    public async Task ItemsAreOrderedByStartDate()
    {
        // N11: stored latest first.
        var (late, early) = databaseApi.Arrange(context => (
            TestData.AddSchedule(context, TestData.TimeOfDay(LATE_INSIDE), TestData.TimeOfDay(PERIOD_END)),
            TestData.AddSchedule(context, TestData.TimeOfDay(PERIOD_START), TestData.TimeOfDay(EARLY_INSIDE))));

        var items = await GetScheduleAsync();

        items.Ids().Should().Equal(early.Id, late.Id);
    }

    [Fact]
    public async Task PeriodWithOneValueIsBadRequest()
    {
        // N12
        await GetWithPeriodAsync(Hour(PERIOD_START)).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task PeriodWithThreeValuesIsBadRequest()
    {
        // N13
        await GetWithPeriodAsync(Hour(PERIOD_START), Hour(EARLY_INSIDE), Hour(PERIOD_END))
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Theory]
    [InlineData(PERIOD_START, PERIOD_START)]
    [InlineData(PERIOD_END, PERIOD_START)]
    public async Task PeriodThatDoesNotStartBeforeItsEndIsBadRequest(int firstHour, int secondHour)
    {
        // N14
        await GetWithPeriodAsync(Hour(firstHour), Hour(secondHour)).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task PeriodValueThatIsNotDateTimeIsBadRequest()
    {
        // N15
        await GetWithPeriodAsync(Hour(PERIOD_START), NOT_A_DATE).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private static string Hour(int hour) => TestData.Iso(TestData.TimeOfDay(hour));

    private Task<IReadOnlyList<JsonElement>> GetScheduleAsync() =>
        databaseApi.Client.GetItemsAsync(
            ApiRoutes.GET_SCHEDULE, (ApiFields.PERIOD, Hour(PERIOD_START)), (ApiFields.PERIOD, Hour(PERIOD_END)));

    // The period is the same query name given once per value.
    private Task<HttpResponseMessage> GetWithPeriodAsync(params string[] values) =>
        nowApi.Client.GetApiAsync(ApiRoutes.GET_SCHEDULE, [.. values.Select(value => (ApiFields.PERIOD, (string?)value))]);
}
