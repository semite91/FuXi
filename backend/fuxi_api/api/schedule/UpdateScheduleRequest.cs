using System.Text.Json.Serialization;

namespace FuXi.Api.Schedules;

/// <summary>The body of UpdateSchedule. Without an id a new Notification Window is added.</summary>
public sealed record UpdateScheduleRequest
{
    public Guid? Id { get; init; }

    [JsonConverter(typeof(IsoDateTimeJsonConverter))]
    public required DateTimeOffset StartDate { get; init; }

    [JsonConverter(typeof(IsoDateTimeJsonConverter))]
    public required DateTimeOffset EndDate { get; init; }
}
