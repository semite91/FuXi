namespace FuXi.Api.Database.Entities;

/// <summary>An app-wide setting, found by its Code.</summary>
public class Setting
{
    public Guid Id { get; set; }

    public required string Code { get; set; }

    public required string Value { get; set; }
}
