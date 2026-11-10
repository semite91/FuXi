namespace FuXi.Api.Database.Entities;

/// <summary>A word the Learner studies, with its translation and learning counters.</summary>
public class Word
{
    public Guid Id { get; set; }

    public required string Name { get; set; }

    public required string Translation { get; set; }

    public string? Content { get; set; }

    public bool IsKnown { get; set; }

    public bool IsReinforcement { get; set; }

    public int ShownCount { get; set; }

    public int KnownCount { get; set; }
}
