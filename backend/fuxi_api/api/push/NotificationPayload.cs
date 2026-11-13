using System.Text.Json;
using FuXi.Api.Words;

namespace FuXi.Api.Push;

/// <summary>The data of one push notification: the Word names as its title and the Word ids the click opens.</summary>
public sealed record NotificationPayload(string Title, string WordIds)
{
    private const string TITLE_SEPARATOR = ", ";
    private const string WORD_ID_SEPARATOR = ",";

    private static readonly JsonSerializerOptions JSON_OPTIONS = new(JsonSerializerDefaults.Web);

    /// <summary>Joins the names and the ids in the same order.</summary>
    public static NotificationPayload From(IReadOnlyList<NotificationWord> words) =>
        new(string.Join(TITLE_SEPARATOR, words.Select(word => word.Name)), string.Join(WORD_ID_SEPARATOR, words.Select(word => word.Id)));

    /// <summary>The JSON the service worker reads: {"title": ..., "wordIds": ...}.</summary>
    public string ToJson() => JsonSerializer.Serialize(this, JSON_OPTIONS);
}
