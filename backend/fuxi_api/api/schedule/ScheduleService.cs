using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Schedules;

/// <summary>The Notification Window logic behind the schedule endpoints.</summary>
public sealed class ScheduleService(FuXiDbContext database)
{
    private const int PERIOD_VALUE_COUNT = 2;

    private const string PERIOD_INVALID = "period must be given exactly twice, as ISO 8601 date-times, the first before the second.";
    private const string END_NOT_AFTER_START = "endDate must be after startDate.";
    private const string SCHEDULE_NOT_FOUND = "The Notification Window was not found.";
    private const string SCHEDULE_OVERLAPS = "The Notification Window overlaps another one.";

    /// <summary>Returns the Notification Windows that overlap the period, ordered by start.</summary>
    public async Task<IReadOnlyList<ScheduleItem>> GetScheduleAsync(string[]? period, CancellationToken cancellationToken)
    {
        var (periodStart, periodEnd) = ParsePeriod(period);

        return await database.Schedules.AsNoTracking()
            .Where(schedule => schedule.StartDate < periodEnd && schedule.EndDate > periodStart)
            .OrderBy(schedule => schedule.StartDate)
            .Select(schedule => new ScheduleItem(schedule.Id, schedule.StartDate, schedule.EndDate))
            .ToListAsync(cancellationToken);
    }

    /// <summary>Adds a Notification Window, or updates the one with the given id. Overlapping another one is rejected.</summary>
    public async Task<ScheduleSaved> UpdateScheduleAsync(UpdateScheduleRequest request, CancellationToken cancellationToken)
    {
        var startDate = request.StartDate.ToUniversalTime();
        var endDate = request.EndDate.ToUniversalTime();
        if (endDate <= startDate)
        {
            throw ApiException.BadRequest(END_NOT_AFTER_START);
        }

        var schedule = await FindOrCreateAsync(request.Id, cancellationToken);
        if (await OverlapsAnotherAsync(schedule.Id, startDate, endDate, cancellationToken))
        {
            throw ApiException.Conflict(SCHEDULE_OVERLAPS);
        }

        schedule.StartDate = startDate;
        schedule.EndDate = endDate;
        await database.SaveChangesAsync(cancellationToken);

        return new ScheduleSaved(schedule.Id);
    }

    /// <summary>Deletes a Notification Window.</summary>
    public async Task DeleteScheduleAsync(Guid id, CancellationToken cancellationToken)
    {
        var deletedCount = await database.Schedules.Where(schedule => schedule.Id == id).ExecuteDeleteAsync(cancellationToken);
        if (deletedCount == 0)
        {
            throw ApiException.NotFound(SCHEDULE_NOT_FOUND);
        }
    }

    // A new entry is only saved when the caller saves; its id is created by the database.
    private async Task<Schedule> FindOrCreateAsync(Guid? id, CancellationToken cancellationToken)
    {
        if (id is null)
        {
            return database.Schedules.Add(new Schedule()).Entity;
        }

        return await database.Schedules.SingleOrDefaultAsync(schedule => schedule.Id == id, cancellationToken)
            ?? throw ApiException.NotFound(SCHEDULE_NOT_FOUND);
    }

    // Windows that only touch do not overlap. The entry is never compared with itself.
    private Task<bool> OverlapsAnotherAsync(Guid ownId, DateTimeOffset startDate, DateTimeOffset endDate, CancellationToken cancellationToken) =>
        database.Schedules.AnyAsync(
            other => other.Id != ownId && other.StartDate < endDate && other.EndDate > startDate,
            cancellationToken);

    private static (DateTimeOffset Start, DateTimeOffset End) ParsePeriod(string[]? period)
    {
        if (period is not { Length: PERIOD_VALUE_COUNT }
            || !IsoDateTime.TryParse(period[0], out var periodStart)
            || !IsoDateTime.TryParse(period[^1], out var periodEnd)
            || periodStart >= periodEnd)
        {
            throw ApiException.BadRequest(PERIOD_INVALID);
        }

        return (periodStart, periodEnd);
    }
}
