using System.Text;
using System.Text.Json;
using FuXi.Api.Words;

namespace FuXi.Api.Push;

/// <summary>The data of one push notification: the Word names as its title and the Word ids the click opens.</summary>
public sealed record NotificationPayload(string Title, string WordIds)
{
    /// <summary>
    /// The longest JSON one push message carries. Push services accept 4096 bytes of encrypted body; aes128gcm takes an
    /// 86-byte header, a 16-byte tag and 1 padding delimiter byte of that.
    /// </summary>
    public const int MAX_PAYLOAD_BYTES = 3993;

    private const string TITLE_SEPARATOR = ", ";
    private const string WORD_ID_SEPARATOR = ",";

    private static readonly JsonSerializerOptions JSON_OPTIONS = new(JsonSerializerDefaults.Web);

    // The JSON of a payload without Words, and the bytes each Word after the first adds between the names and between the ids.
    private static readonly int EMPTY_PAYLOAD_BYTES = Utf8Length(new NotificationPayload(string.Empty, string.Empty).ToJson());
    private static readonly int SEPARATOR_BYTES = Utf8Length(TITLE_SEPARATOR) + Utf8Length(WORD_ID_SEPARATOR);
    private static readonly int WORD_ID_BYTES = Utf8Length(Guid.Empty.ToString());

    /// <summary>Joins the names and the ids in the same order.</summary>
    public static NotificationPayload From(IReadOnlyList<NotificationWord> words) =>
        new(string.Join(TITLE_SEPARATOR, words.Select(word => word.Name)), string.Join(WORD_ID_SEPARATOR, words.Select(word => word.Id)));

    /// <summary>
    /// The JSON of the first Words, in their order, whose payload fits in <see cref="MAX_PAYLOAD_BYTES"/>; the other Words are left out.
    /// Null when not even the first Word fits.
    /// </summary>
    public static string? FittingJson(IReadOnlyList<NotificationWord> words)
    {
        var count = CountFittingWords(words);
        if (count == 0)
        {
            return null;
        }

        var json = From(words.Take(count).ToList()).ToJson();

        // The size was counted Word by Word; this proves the count against the real JSON.
        return Utf8Length(json) <= MAX_PAYLOAD_BYTES
            ? json
            : throw new InvalidOperationException($"The notification payload is longer than {MAX_PAYLOAD_BYTES} bytes.");
    }

    /// <summary>The JSON the service worker reads: {"title": ..., "wordIds": ...}.</summary>
    public string ToJson() => JsonSerializer.Serialize(this, JSON_OPTIONS);

    // Adds up the escaped bytes each Word adds to the JSON, so the payload is not serialised again for every Word.
    private static int CountFittingWords(IReadOnlyList<NotificationWord> words)
    {
        var size = EMPTY_PAYLOAD_BYTES;
        var count = 0;
        foreach (var word in words)
        {
            size += WordBytes(word) + (count == 0 ? 0 : SEPARATOR_BYTES);
            if (size > MAX_PAYLOAD_BYTES)
            {
                break;
            }

            count++;
        }

        return count;
    }

    // The name as the serialiser escapes it (the default encoder, as JSON_OPTIONS sets none), and the id.
    private static int WordBytes(NotificationWord word) => JsonEncodedText.Encode(word.Name).EncodedUtf8Bytes.Length + WORD_ID_BYTES;

    private static int Utf8Length(string text) => Encoding.UTF8.GetByteCount(text);
}
