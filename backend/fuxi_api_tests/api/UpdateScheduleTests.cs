using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section O: UpdateSchedule. The stored Notification Window runs from 10:00 to 12:00.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateScheduleTests : IDisposable
{
    private const int EIGHT = 8;
    private const int NINE = 9;
    private const int TEN = 10;
    private const int ELEVEN = 11;
    private const int TWELVE = 12;
    private const int THIRTEEN = 13;
    private const int FOURTEEN = 14;
    private const int FIFTEEN = 15;
    private const int SIXTEEN = 16;
    private const int HALF_HOUR = 30;
    private const int WHOLE_HOUR = 0;
    private const int LOCAL_OFFSET_HOURS = 3;
    private const int TWO_WINDOWS = 2;
    private const string START_WITHOUT_OFFSET = "2026-11-10T10:00:00";
    private const string END_WITHOUT_OFFSET = "2026-11-10T12:00:00";
    private const string DATE_WITHOUT_TIME = "2026-11-10";

    private static readonly DateTimeOffset WindowStart = TestData.TimeOfDay(TEN);
    private static readonly DateTimeOffset WindowEnd = TestData.TimeOfDay(TWELVE);

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task RequestWithoutIdAddsEntryAndReturnsItsId()
    {
        // O1, O2
        using var response = await databaseApi.Client.PostApiAsync(
            ApiRoutes.UPDATE_SCHEDULE, new { startDate = WindowStart, endDate = WindowEnd });

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        var stored = ReadSchedules().Should().ContainSingle().Subject;
        stored.StartDate.Should().Be(WindowStart);
        stored.EndDate.Should().Be(WindowEnd);
        (await response.ReadJsonAsync()).GuidOf(ApiFields.ID).Should().Be(stored.Id);
    }

    [Fact]
    public async Task RequestWithNullIdAddsEntry()
    {
        // O1
        await SendAsync(id: null, WindowStart, WindowEnd).ShouldHaveStatusAsync(HttpStatusCode.OK);

        ReadSchedules().Should().ContainSingle();
    }

    [Fact]
    public async Task DatesWithOffsetAreStoredAsSameUtcInstants()
    {
        // O3
        var offset = TimeSpan.FromHours(LOCAL_OFFSET_HOURS);

        await SendAsync(id: null, WindowStart.ToOffset(offset), WindowEnd.ToOffset(offset))
            .ShouldHaveStatusAsync(HttpStatusCode.OK);

        var stored = ReadSchedules().Should().ContainSingle().Subject;
        stored.StartDate.Should().Be(WindowStart);
        stored.EndDate.Should().Be(WindowEnd);
        stored.StartDate.Offset.Should().Be(TimeSpan.Zero);
        stored.EndDate.Offset.Should().Be(TimeSpan.Zero);
    }

    [Fact]
    public async Task DatesWithoutOffsetAreStoredAsUtc()
    {
        // Review R3: a date-time without offset is UTC, never the server's local time.
        await databaseApi.Client
            .PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { startDate = START_WITHOUT_OFFSET, endDate = END_WITHOUT_OFFSET })
            .ShouldHaveStatusAsync(HttpStatusCode.OK);

        var stored = ReadSchedules().Should().ContainSingle().Subject;
        stored.StartDate.Should().Be(WindowStart);
        stored.EndDate.Should().Be(WindowEnd);
    }

    [Fact]
    public async Task RequestWithIdUpdatesThatEntryAndKeepsItsId()
    {
        // O4, O5
        var window = ArrangeWindow();

        using var response = await SendAsync(window.Id, TestData.TimeOfDay(FOURTEEN), TestData.TimeOfDay(SIXTEEN));

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadJsonAsync()).GuidOf(ApiFields.ID).Should().Be(window.Id);
        var stored = ReadSchedules().Should().ContainSingle().Subject;
        stored.Id.Should().Be(window.Id);
        stored.StartDate.Should().Be(TestData.TimeOfDay(FOURTEEN));
        stored.EndDate.Should().Be(TestData.TimeOfDay(SIXTEEN));
    }

    [Fact]
    public async Task UnknownIdIsNotFoundAndAddsNothing()
    {
        // O6
        await SendAsync(Guid.NewGuid(), WindowStart, WindowEnd).ShouldBeProblemAsync(HttpStatusCode.NotFound);

        ReadSchedules().Should().BeEmpty();
    }

    [Theory]
    [InlineData(ELEVEN, WHOLE_HOUR, THIRTEEN, WHOLE_HOUR)] // O7
    [InlineData(NINE, WHOLE_HOUR, ELEVEN, WHOLE_HOUR)] // O8
    [InlineData(TEN, HALF_HOUR, ELEVEN, HALF_HOUR)] // O9
    [InlineData(NINE, WHOLE_HOUR, THIRTEEN, WHOLE_HOUR)] // O10
    public async Task OverlappingNewWindowIsConflictAndNotStored(int startHour, int startMinute, int endHour, int endMinute)
    {
        // O7, O8, O9, O10
        var window = ArrangeWindow();

        await SendAsync(id: null, TestData.TimeOfDay(startHour, startMinute), TestData.TimeOfDay(endHour, endMinute))
            .ShouldBeProblemAsync(HttpStatusCode.Conflict);

        ReadSchedules().Should().ContainSingle().Which.Should().BeEquivalentTo(window);
    }

    [Theory]
    [InlineData(TWELVE, FOURTEEN)] // O11
    [InlineData(EIGHT, TEN)] // O12
    public async Task WindowThatOnlyTouchesIsAccepted(int startHour, int endHour)
    {
        // O11, O12
        ArrangeWindow();

        await SendAsync(id: null, TestData.TimeOfDay(startHour), TestData.TimeOfDay(endHour))
            .ShouldHaveStatusAsync(HttpStatusCode.OK);

        ReadSchedules().Should().HaveCount(TWO_WINDOWS);
    }

    [Fact]
    public async Task EditedWindowIsNotComparedWithItself()
    {
        // O13
        var window = ArrangeWindow();

        await SendAsync(window.Id, WindowStart, TestData.TimeOfDay(THIRTEEN)).ShouldHaveStatusAsync(HttpStatusCode.OK);

        ReadSchedules().Should().ContainSingle().Which.EndDate.Should().Be(TestData.TimeOfDay(THIRTEEN));
    }

    [Fact]
    public async Task EditThatOverlapsOtherWindowIsConflictAndChangesNothing()
    {
        // O14
        var window = ArrangeWindow();
        var other = databaseApi.Arrange(context =>
            TestData.AddSchedule(context, TestData.TimeOfDay(FOURTEEN), TestData.TimeOfDay(SIXTEEN)));

        await SendAsync(window.Id, TestData.TimeOfDay(ELEVEN), TestData.TimeOfDay(FIFTEEN))
            .ShouldBeProblemAsync(HttpStatusCode.Conflict);

        ReadSchedules().Should().BeEquivalentTo([window, other]);
    }

    [Theory]
    [InlineData(TEN, TEN)] // O15
    [InlineData(TWELVE, TEN)] // O16
    public async Task EndThatIsNotAfterStartIsBadRequest(int startHour, int endHour)
    {
        // O15, O16
        await nowApi.Client
            .PostApiAsync(
                ApiRoutes.UPDATE_SCHEDULE,
                new { startDate = TestData.TimeOfDay(startHour), endDate = TestData.TimeOfDay(endHour) })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingStartIsBadRequest()
    {
        // O17
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { endDate = WindowEnd })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingEndIsBadRequest()
    {
        // O17
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { startDate = WindowStart })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task StartThatIsNotIsoDateTimeIsBadRequest()
    {
        // Review R3: the body follows the same strict ISO 8601 rule as the period of GetSchedule.
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { startDate = DATE_WITHOUT_TIME, endDate = WindowEnd })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task EndThatIsNotIsoDateTimeIsBadRequest()
    {
        // Review R3
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { startDate = WindowStart, endDate = DATE_WITHOUT_TIME })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task IdThatIsNotGuidIsBadRequest()
    {
        // O18
        await nowApi.Client
            .PostApiAsync(
                ApiRoutes.UPDATE_SCHEDULE, new { id = ApiRequests.NOT_A_GUID, startDate = WindowStart, endDate = WindowEnd })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Schedule ArrangeWindow() => databaseApi.Arrange(context => TestData.AddSchedule(context, WindowStart, WindowEnd));

    private Task<HttpResponseMessage> SendAsync(Guid? id, DateTimeOffset startDate, DateTimeOffset endDate) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_SCHEDULE, new { id, startDate, endDate });

    private List<Schedule> ReadSchedules() => databaseApi.Read(context => context.Schedules.AsNoTracking().ToList());
}
