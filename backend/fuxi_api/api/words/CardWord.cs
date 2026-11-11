namespace FuXi.Api.Words;

/// <summary>A Word in the Rotation with the data its Flashcard shows.</summary>
public sealed record CardWord(
    Guid Id,
    string Name,
    string Translation,
    int Counter,
    bool IsReinforcement,
    DateTimeOffset? LastShownDate,
    string? Content);
