using System.Text.Json;
using System.Text.Json.Serialization;

namespace FuXi.Api;

/// <summary>Reads a JSON date-time with the rule of <see cref="IsoDateTime"/>, so a value without offset is UTC.</summary>
public sealed class IsoDateTimeJsonConverter : JsonConverter<DateTimeOffset>
{
    private const string NOT_ISO_DATE_TIME = "The value is not an ISO 8601 date-time.";

    public override DateTimeOffset Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        reader.TokenType == JsonTokenType.String && IsoDateTime.TryParse(reader.GetString(), out var value)
            ? value
            : throw new JsonException(NOT_ISO_DATE_TIME);

    public override void Write(Utf8JsonWriter writer, DateTimeOffset value, JsonSerializerOptions options) =>
        writer.WriteStringValue(value);
}
