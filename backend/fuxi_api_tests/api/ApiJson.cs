using System.Text.Json;

namespace FuXi.Api.Tests.Api;

/// <summary>Reads the fields of a JSON answer by their contract names.</summary>
public static class ApiJson
{
    public static IReadOnlyList<JsonElement> Items(this JsonElement list) => [.. list.EnumerateArray()];

    public static IReadOnlyList<string> FieldNames(this JsonElement item) =>
        [.. item.EnumerateObject().Select(property => property.Name)];

    public static string? Text(this JsonElement item, string field) => item.GetProperty(field).GetString();

    public static Guid GuidOf(this JsonElement item, string field) => item.GetProperty(field).GetGuid();

    public static bool Flag(this JsonElement item, string field) => item.GetProperty(field).GetBoolean();

    public static int Number(this JsonElement item, string field) => item.GetProperty(field).GetInt32();

    public static DateTimeOffset? Date(this JsonElement item, string field)
    {
        var value = item.GetProperty(field);

        return value.ValueKind == JsonValueKind.Null ? null : value.GetDateTimeOffset();
    }

    public static IReadOnlyList<Guid> Ids(this IEnumerable<JsonElement> items) =>
        [.. items.Select(item => item.GuidOf(ApiFields.ID))];

    public static IReadOnlyList<string?> Names(this IEnumerable<JsonElement> items) =>
        [.. items.Select(item => item.Text(ApiFields.NAME))];
}
