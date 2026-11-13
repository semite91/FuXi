namespace FuXi.Api.Push;

/// <summary>
/// The JSON of the Words that fit in one push message, or null when none fits, and the ids of the Words whose name alone
/// makes a push message too long.
/// </summary>
public sealed record FittedPayload(string? Json, IReadOnlyList<Guid> TooLongWordIds);
