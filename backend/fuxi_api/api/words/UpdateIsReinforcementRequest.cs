namespace FuXi.Api.Words;

/// <summary>The body of UpdateIsReinforcement.</summary>
public sealed record UpdateIsReinforcementRequest
{
    public required Guid WordId { get; init; }

    public required bool IsReinforcement { get; init; }
}
