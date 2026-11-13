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

    private static ServiceProvider CreateApiServices()
    {
        var collection = new ServiceCollection().AddLogging();
        collection.AddFuXiApi();

        return collection.BuildServiceProvider();
    }
}
