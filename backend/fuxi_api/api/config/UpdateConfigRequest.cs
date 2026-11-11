namespace FuXi.Api.Configs;

/// <summary>The body of UpdateConfig and UpdateNotificationPeriod.</summary>
public sealed record UpdateConfigRequest
{
    public required Guid Id { get; init; }

    public string? Value { get; init; }
}
