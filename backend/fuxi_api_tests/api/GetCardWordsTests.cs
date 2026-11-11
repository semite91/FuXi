using System.Net;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section D: GetCardWords.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetCardWordsTests : IDisposable
{
    private const char ID_SEPARATOR = ',';
    private const int TWO_WORDS = 2;
    private const int THREE_WORDS = 3;
    private const int COUNTER = 4;
    private const int HOURS_SINCE_SHOWN = 2;
    private const string CONTENT = "A story about an apple.";

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task TwoIdsReturnBothWords()
    {
        // D1
        var words = databaseApi.Arrange(context => TestData.AddRotatedWords(context, TWO_WORDS));

        var items = await GetCardWordsAsync(words[0].Id, words[1].Id);

        items.Ids().Should().BeEquivalentTo([words[0].Id, words[1].Id]);
    }

    [Fact]
    public async Task OneIdReturnsOneWord()
    {
        // D2
        var words = databaseApi.Arrange(context => TestData.AddRotatedWords(context, TWO_WORDS));

        var items = await GetCardWordsAsync(words[0].Id);

        items.Ids().Should().Equal(words[0].Id);
    }

    [Fact]
    public async Task ItemHoldsWordAndRotationFields()
    {
        // D3, D4
        var lastShownDate = TestData.Now.AddHours(-HOURS_SINCE_SHOWN);
        var word = databaseApi.Arrange(context =>
        {
            var added = TestData.AddWord(context, isReinforcement: true, content: CONTENT);
            TestData.AddRotatedWord(context, added, COUNTER, lastShownDate);

            return added;
        });

        var item = (await GetCardWordsAsync(word.Id)).Should().ContainSingle().Subject;

        item.FieldNames().Should().BeEquivalentTo(ApiFields.CARD_WORD_FIELDS);
        item.GuidOf(ApiFields.ID).Should().Be(word.Id);
        item.Text(ApiFields.NAME).Should().Be(TestData.WORD_NAME);
        item.Text(ApiFields.TRANSLATION).Should().Be(TestData.TRANSLATION);
        item.Flag(ApiFields.IS_REINFORCEMENT).Should().BeTrue();
        item.Text(ApiFields.CONTENT).Should().Be(CONTENT);
        item.Number(ApiFields.COUNTER).Should().Be(COUNTER);
        item.Date(ApiFields.LAST_SHOWN_DATE).Should().Be(lastShownDate);
    }

    [Fact]
    public async Task WordOutsideRotationIsLeftOut()
    {
        // D5
        var (rotated, notRotated) = databaseApi.Arrange(context =>
            (TestData.AddRotatedWords(context, TWO_WORDS)[0], TestData.AddWord(context)));

        var items = await GetCardWordsAsync(rotated.Id, notRotated.Id);

        items.Ids().Should().Equal(rotated.Id);
    }

    [Fact]
    public async Task UnknownIdIsLeftOut()
    {
        // D6
        var word = databaseApi.Arrange(context => TestData.AddRotatedWords(context, TWO_WORDS)[0]);

        var items = await GetCardWordsAsync(word.Id, Guid.NewGuid());

        items.Ids().Should().Equal(word.Id);
    }

    [Fact]
    public async Task RepeatedIdReturnsWordOnce()
    {
        // D7
        var word = databaseApi.Arrange(context => TestData.AddRotatedWords(context, TWO_WORDS)[0]);

        var items = await GetCardWordsAsync(word.Id, word.Id);

        items.Ids().Should().Equal(word.Id);
    }

    [Fact]
    public async Task ValueThatIsNotGuidIsBadRequest()
    {
        // D8
        var wordIds = string.Join(ID_SEPARATOR, Guid.NewGuid(), ApiRequests.NOT_A_GUID);

        await nowApi.Client.GetApiAsync(ApiRoutes.GET_CARD_WORDS, (ApiFields.WORD_IDS, wordIds))
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingListIsBadRequest()
    {
        // D9
        await nowApi.Client.GetApiAsync(ApiRoutes.GET_CARD_WORDS).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task EmptyListIsBadRequest()
    {
        // D9
        await nowApi.Client.GetApiAsync(ApiRoutes.GET_CARD_WORDS, (ApiFields.WORD_IDS, string.Empty))
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task WordsComeInOrderOfIds()
    {
        // D10: neither the order they were stored in nor the order of their names.
        var words = databaseApi.Arrange(context => TestData.AddRotatedWords(context, THREE_WORDS));
        Guid[] requestedOrder = [words[1].Id, words[2].Id, words[0].Id];

        var items = await GetCardWordsAsync(requestedOrder);

        items.Ids().Should().Equal(requestedOrder);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Task<IReadOnlyList<JsonElement>> GetCardWordsAsync(params Guid[] wordIds) =>
        databaseApi.Client.GetItemsAsync(ApiRoutes.GET_CARD_WORDS, (ApiFields.WORD_IDS, string.Join(ID_SEPARATOR, wordIds)));
}
