namespace FuXi.Api.Schedules;

/// <summary>A Notification Window as the schedule calendar shows it.</summary>
public sealed record ScheduleItem(Guid Id, DateTimeOffset StartDate, DateTimeOffset EndDate);
