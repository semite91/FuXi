using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section P: DeleteSchedule.</summary>
[Collection(nameof(SmokeTests))]
public sealed class DeleteScheduleTests : IDisposable
{
    private const int FIRST_START = 10;
    private const int FIRST_END = 12;
    private const int SECOND_START = 14;
    private const int SECOND_END = 16;

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task EntryIsDeletedAndOtherEntryStays()
    {
        // P1, P2
        var (window, other) = ArrangeTwoWindows();

        await DeleteAsync(databaseApi.Client, window.Id.ToString()).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadSchedules().Should().ContainSingle().Which.Should().BeEquivalentTo(other);
    }

    [Fact]
    public async Task UnknownIdIsNotFound()
    {
        // P3
        var (window, other) = ArrangeTwoWindows();

        await DeleteAsync(databaseApi.Client, Guid.NewGuid().ToString()).ShouldBeProblemAsync(HttpStatusCode.NotFound);

        ReadSchedules().Should().BeEquivalentTo([window, other]);
    }

    [Fact]
    public async Task IdThatIsNotGuidIsBadRequest()
    {
        // P4
        await DeleteAsync(nowApi.Client, ApiRequests.NOT_A_GUID).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private static Task<HttpResponseMessage> DeleteAsync(HttpClient client, string id) =>
        client.DeleteApiAsync(ApiRoutes.DELETE_SCHEDULE, (ApiFields.ID, id));

    private (Schedule Window, Schedule Other) ArrangeTwoWindows() =>
        databaseApi.Arrange(context => (
            TestData.AddSchedule(context, TestData.TimeOfDay(FIRST_START), TestData.TimeOfDay(FIRST_END)),
            TestData.AddSchedule(context, TestData.TimeOfDay(SECOND_START), TestData.TimeOfDay(SECOND_END))));

    private List<Schedule> ReadSchedules() => databaseApi.Read(context => context.Schedules.AsNoTracking().ToList());
}
