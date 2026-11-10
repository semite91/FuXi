namespace FuXi.Api.Database.Entities;

/// <summary>One answer the Learner gave for a word.</summary>
public class WordHistory
{
    public Guid Id { get; set; }

    public Guid WordId { get; set; }

    public bool IsKnown { get; set; }

    public DateTimeOffset Date { get; set; }
}
