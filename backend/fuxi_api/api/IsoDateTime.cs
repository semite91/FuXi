using System.Globalization;

namespace FuXi.Api;

/// <summary>Reads ISO 8601 date-times that arrive as text.</summary>
public static class IsoDateTime
{
    // Seconds, an optional fraction and an optional offset, such as 2026-11-11T10:00:00.000Z.
    public const string FORMAT = "yyyy-MM-dd'T'HH:mm:ss.FFFFFFFK";

    /// <summary>Parses the text into a UTC instant. A value without offset is read as UTC.</summary>
    public static bool TryParse(string? text, out DateTimeOffset value)
    {
        var isParsed = DateTimeOffset.TryParseExact(
            text, FORMAT, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var parsed);
        value = parsed.ToUniversalTime();

        return isParsed;
    }
}
