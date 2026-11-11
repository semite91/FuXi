namespace FuXi.Api.Words;

/// <summary>The body of UpdateWordKnownStatus.</summary>
public sealed record UpdateWordKnownStatusRequest
{
    public required Guid WordId { get; init; }

    public required bool IsKnown { get; init; }
}
