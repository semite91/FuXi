using System.Text;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Push;
using FuXi.Api.Words;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 sections E and F (test_scenarios_2026_11_12_22_06): the parts of a run that need no database.</summary>
[Collection(nameof(SmokeTests))]
public sealed class PushSendingNowTests
{
    private const string APPLE = "apple";
    private const string RIVER = "river";
    private const string TITLE_FIELD = "title";
    private const string WORD_IDS_FIELD = "wordIds";
    private const string APPLE_ID = "0b6a3c4e-1d2f-4a5b-8c9d-0e1f2a3b4c5d";
    private const string RIVER_ID = "9f8e7d6c-5b4a-4392-8170-6f5e4d3c2b1a";
    private const string CONFIGURED_KEY = "configured-key-of-a-test";
    private const string WORD_ID_SEPARATOR = ",";

    // JSON escapes this letter as \u015F, six bytes, so the size must be counted on the escaped JSON.
    private const char ESCAPED_LETTER = 'ş';
    private const int ESCAPED_LETTERS_PER_NAME = 50;
    private const int LONG_WORD_COUNT = 20;

    // {"title":"","wordIds":""} and the "D" text of a Guid.
    private const int EMPTY_PAYLOAD_BYTES = 25;
    private const int WORD_ID_BYTES = 36;

    // The JSON of one Word with an ASCII name of this length is exactly MAX_PAYLOAD_BYTES long.
    private const int LONGEST_FITTING_NAME = NotificationPayload.MAX_PAYLOAD_BYTES - EMPTY_PAYLOAD_BYTES - WORD_ID_BYTES;
    private const char ASCII_LETTER = 'a';

    [Fact]
    public void PayloadIsCamelCaseJsonWithTitleAndWordIdsOnly()
    {
        // E5
        NotificationWord[] words = [new(Guid.Parse(APPLE_ID), APPLE), new(Guid.Parse(RIVER_ID), RIVER)];

        var json = NotificationPayload.From(words).ToJson();

        using var document = JsonDocument.Parse(json);
        document.RootElement.EnumerateObject().Select(property => property.Name).Should().Equal(TITLE_FIELD, WORD_IDS_FIELD);
        document.RootElement.GetProperty(TITLE_FIELD).GetString().Should().Be($"{APPLE}, {RIVER}");
        document.RootElement.GetProperty(WORD_IDS_FIELD).GetString().Should().Be($"{APPLE_ID},{RIVER_ID}");
    }

    [Fact]
    public void PayloadHoldsFirstWordsThatFitInMaxPayloadBytes()
    {
        // E8
        var words = Enumerable.Range(0, LONG_WORD_COUNT)
            .Select(number => new NotificationWord(Guid.NewGuid(), new string(ESCAPED_LETTER, ESCAPED_LETTERS_PER_NAME) + number))
            .ToList();

        var json = NotificationPayload.FittingJson(words)!;

        var count = ReadField(json, WORD_IDS_FIELD).Split(WORD_ID_SEPARATOR).Length;
        count.Should().BeInRange(1, LONG_WORD_COUNT - 1);
        Encoding.UTF8.GetByteCount(json).Should().BeLessThanOrEqualTo(NotificationPayload.MAX_PAYLOAD_BYTES);
        json.Should().Be(NotificationPayload.From(words.Take(count).ToList()).ToJson());
        Encoding.UTF8.GetByteCount(NotificationPayload.From(words.Take(count + 1).ToList()).ToJson())
            .Should().BeGreaterThan(NotificationPayload.MAX_PAYLOAD_BYTES);
    }

    [Fact]
    public void PayloadOfExactlyMaxPayloadBytesIsBuilt()
    {
        // E8
        var json = NotificationPayload.FittingJson([AsciiWord(LONGEST_FITTING_NAME)]);

        Encoding.UTF8.GetByteCount(json!).Should().Be(NotificationPayload.MAX_PAYLOAD_BYTES);
    }

    [Fact]
    public void WordThatAloneExceedsMaxPayloadBytesGivesNoPayload()
    {
        // E8: not even the first Word fits, so there is nothing to send.
        var json = NotificationPayload.FittingJson([AsciiWord(LONGEST_FITTING_NAME + 1), new(Guid.Parse(RIVER_ID), RIVER)]);

        json.Should().BeNull();
    }

    [Theory]
    [InlineData("", "")]
    [InlineData(CONFIGURED_KEY, "")]
    [InlineData("", CONFIGURED_KEY)]
    public async Task EmptyVapidKeysSendNothingAndLogWarning(string publicKey, string privateKey)
    {
        // F7: the database of NowApi is unreachable, so the run must stop before it is used.
        using var api = new NowApi(new NowApiSettings { VapidPublicKey = publicKey, VapidPrivateKey = privateKey });
        await using var scope = api.Services.CreateAsyncScope();

        await scope.ServiceProvider.GetRequiredService<NotificationService>().SendDueWordsAsync(TestContext.Current.CancellationToken);

        api.Host.PushSender.Sent.Should().BeEmpty();
        api.Host.Logs.Of(typeof(NotificationService).FullName!).Should().ContainSingle(entry => entry.Level == LogLevel.Warning);
    }

    [Fact]
    public void PushClientIsBehindInterface()
    {
        // F8: the API sends through IPushMessageSender, and the test hosts replace it with a fake.
        using var provider = CreateApiServices();

        provider.GetRequiredService<IPushMessageSender>().Should().BeOfType<WebPushMessageSender>();
        typeof(NotificationService).GetConstructors().Single().GetParameters()
            .Should().Contain(parameter => parameter.ParameterType == typeof(IPushMessageSender));

        using var api = new NowApi();
        api.Services.GetRequiredService<IPushMessageSender>().Should().BeSameAs(api.Host.PushSender);
    }

    [Fact]
    public void PushClientGetsHttpClientWithTimeoutFromFactory()
    {
        // F10
        using var provider = CreateApiServices();

        using var client = provider.GetRequiredService<IHttpClientFactory>().CreateClient(WebPushMessageSender.HTTP_CLIENT_NAME);

        client.Timeout.Should().Be(WebPushMessageSender.REQUEST_TIMEOUT);
    }

    private static NotificationWord AsciiWord(int nameLength) => new(Guid.Parse(APPLE_ID), new string(ASCII_LETTER, nameLength));

    private static string ReadField(string json, string field)
    {
        using var document = JsonDocument.Parse(json);

        return document.RootElement.GetProperty(field).GetString()!;
    }

    private static ServiceProvider CreateApiServices()
    {
        var collection = new ServiceCollection().AddLogging();
        collection.AddFuXiApi();

        return collection.BuildServiceProvider();
    }
}
