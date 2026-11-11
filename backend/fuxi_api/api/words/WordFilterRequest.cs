namespace FuXi.Api.Words;

/// <summary>The filter fields as they arrive in the query. An empty field means any value.</summary>
public sealed record WordFilterRequest(string? Name, string? IsReinforcement, string? IsKnown, string? IsRotated);
