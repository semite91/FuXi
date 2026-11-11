namespace FuXi.Api.Words;

/// <summary>The body of UpdateWordContent.</summary>
public sealed record UpdateWordContentRequest
{
    public required Guid Id { get; init; }

    public string? Content { get; init; }
}
