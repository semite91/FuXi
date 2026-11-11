namespace FuXi.Api.Words;

/// <summary>The checked filter. A null field means any value.</summary>
public sealed record WordFilter(string? Name, bool? IsReinforcement, bool? IsKnown, bool? IsRotated)
{
    private const string FLAG_INVALID = "isReinforcement, isKnown and isRotated must be true, false or empty.";

    public bool IsEmpty => Name is null && IsReinforcement is null && IsKnown is null && IsRotated is null;

    /// <summary>Reads the query fields. A name of only spaces counts as empty.</summary>
    public static WordFilter Parse(WordFilterRequest request) =>
        new(
            string.IsNullOrWhiteSpace(request.Name) ? null : request.Name.Trim(),
            ParseFlag(request.IsReinforcement),
            ParseFlag(request.IsKnown),
            ParseFlag(request.IsRotated));

    private static bool? ParseFlag(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }

        return bool.TryParse(text, out var flag) ? flag : throw ApiException.BadRequest(FLAG_INVALID);
    }
}
