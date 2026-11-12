namespace FuXi.Api.Words;

/// <summary>A Word found by the filter, with its Rotation state.</summary>
public sealed record FilteredWord(
    Guid Id,
    string Name,
    bool IsReinforcement,
    bool IsKnown,
    DateTimeOffset? LastShownDate,
    int ShownCount,
    int KnownCount,
    bool IsRotated,
    int? Counter);
