using System.Text;
using System.Text.Encodings.Web;
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

    // Relaxed escaping writes letters such as 'ş' as UTF-8 instead of \uXXXX, so more Words fit. Safe here: the service worker
    // reads the payload with JSON.parse and never puts it into HTML. Quotes, backslashes and control characters are still escaped.
    private static readonly JsonSerializerOptions JSON_OPTIONS =
        new(JsonSerializerDefaults.Web) { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    // The JSON of a payload without Words, and the bytes each Word after the first adds between the names and between the ids.
    private static readonly int EMPTY_PAYLOAD_BYTES = Utf8Length(new NotificationPayload(string.Empty, string.Empty).ToJson());
    private static readonly int SEPARATOR_BYTES = Utf8Length(TITLE_SEPARATOR) + Utf8Length(WORD_ID_SEPARATOR);
    private static readonly int WORD_ID_BYTES = Utf8Length(Guid.Empty.ToString());

    /// <summary>Joins the names and the ids in the same order.</summary>
    public static NotificationPayload From(IReadOnlyList<NotificationWord> words) =>
        new(string.Join(TITLE_SEPARATOR, words.Select(word => word.Name)), string.Join(WORD_ID_SEPARATOR, words.Select(word => word.Id)));

    /// <summary>
    /// Goes through the Words once, in their order, and keeps each Word that still fits in <see cref="MAX_PAYLOAD_BYTES"/>.
    /// A Word that does not fit is left out and the next ones are tried; a Word that alone is too long is also named.
    /// </summary>
    public static FittedPayload Fit(IReadOnlyList<NotificationWord> words)
    {
        var fitting = new List<NotificationWord>();
        var tooLongWordIds = new List<Guid>();
        var size = EMPTY_PAYLOAD_BYTES;
        foreach (var word in words)
        {
            var wordBytes = WordBytes(word);
            if (EMPTY_PAYLOAD_BYTES + wordBytes > MAX_PAYLOAD_BYTES)
            {
                tooLongWordIds.Add(word.Id);
                continue;
            }

            var addedBytes = wordBytes + (fitting.Count == 0 ? 0 : SEPARATOR_BYTES);
            if (size + addedBytes <= MAX_PAYLOAD_BYTES)
            {
                fitting.Add(word);
                size += addedBytes;
            }
        }

        return new FittedPayload(fitting.Count == 0 ? null : CheckedJson(fitting), tooLongWordIds);
    }

    /// <summary>The JSON the service worker reads: {"title": ..., "wordIds": ...}.</summary>
    public string ToJson() => JsonSerializer.Serialize(this, JSON_OPTIONS);

    // The size was counted Word by Word, so the payload is not serialised again for every Word; this proves it against the real JSON.
    private static string CheckedJson(IReadOnlyList<NotificationWord> words)
    {
        var json = From(words).ToJson();

        return Utf8Length(json) <= MAX_PAYLOAD_BYTES
            ? json
            : throw new InvalidOperationException($"The notification payload is longer than {MAX_PAYLOAD_BYTES} bytes.");
    }

    // The name as the serialiser escapes it (the same encoder as JSON_OPTIONS), and the id.
    private static int WordBytes(NotificationWord word) =>
        JsonEncodedText.Encode(word.Name, JavaScriptEncoder.UnsafeRelaxedJsonEscaping).EncodedUtf8Bytes.Length + WORD_ID_BYTES;

    private static int Utf8Length(string text) => Encoding.UTF8.GetByteCount(text);
}
