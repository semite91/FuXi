namespace FuXi.Api.Database.Entities;

/// <summary>A word that is currently in the rotation.</summary>
public class RotatedWord
{
    public Guid Id { get; set; }

    public Guid WordId { get; set; }

    public DateTimeOffset? LastShownDate { get; set; }

    public int Counter { get; set; }
}
