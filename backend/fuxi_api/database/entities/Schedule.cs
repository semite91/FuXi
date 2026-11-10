namespace FuXi.Api.Database.Entities;

/// <summary>A notification window.</summary>
public class Schedule
{
    public Guid Id { get; set; }

    public DateTimeOffset StartDate { get; set; }

    public DateTimeOffset EndDate { get; set; }
}
