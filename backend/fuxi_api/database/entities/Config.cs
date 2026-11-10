namespace FuXi.Api.Database.Entities;

/// <summary>A setting the Learner can change.</summary>
public class Config
{
    public Guid Id { get; set; }

    public required string Name { get; set; }

    public required string Code { get; set; }

    public required string Value { get; set; }

    public InputType InputType { get; set; }
}
