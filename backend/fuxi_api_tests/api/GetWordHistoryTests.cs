using System.Net;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section G: GetWordHistory.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetWordHistoryTests : IDisposable
{
    private const int HISTORY_COUNT = 3;
    private const int OLDEST_HOURS_AGO = 3;
    private const int MIDDLE_HOURS_AGO = 2;
    private const int NEWEST_HOURS_AGO = 1;

    private static readonly DateTimeOffset OldestDate = TestData.Now.AddHours(-OLDEST_HOURS_AGO);
    private static readonly DateTimeOffset MiddleDate = TestData.Now.AddHours(-MIDDLE_HOURS_AGO);
    private static readonly DateTimeOffset NewestDate = TestData.Now.AddHours(-NEWEST_HOURS_AGO);

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task ThreeEntriesGiveThreeItemsNewestFirst()
    {
        // G1, G2: stored in an order that is neither oldest first nor newest first.
        var word = ArrangeWordWithHistory();

        var items = await GetHistoryAsync(word.Id);

        items.Should().HaveCount(HISTORY_COUNT);
        items.Select(item => item.Date(ApiFields.DATE)).Should().Equal(NewestDate, MiddleDate, OldestDate);
        items.Select(item => item.Flag(ApiFields.IS_KNOWN)).Should().Equal(true, false, true);
    }

    [Fact]
    public async Task ItemHoldsOnlyIsKnownAndDate()
    {
        // G3
        var word = ArrangeWordWithHistory();

        var items = await GetHistoryAsync(word.Id);

        items.Should().AllSatisfy(item => item.FieldNames().Should().BeEquivalentTo(ApiFields.IS_KNOWN, ApiFields.DATE));
    }

    [Fact]
    public async Task HistoryOfOtherWordIsNotReturned()
    {
        // G4
        var word = ArrangeWordWithHistory();
        databaseApi.Arrange(context =>
        {
            var other = TestData.AddWord(context, TestData.OTHER_WORD_NAME);
            TestData.AddHistory(context, other, isKnown: true, TestData.Now);
        });

        var items = await GetHistoryAsync(word.Id);

        items.Select(item => item.Date(ApiFields.DATE)).Should().Equal(NewestDate, MiddleDate, OldestDate);
    }

    [Fact]
    public async Task WordWithoutHistoryGivesEmptyList()
    {
        // G5
        var word = databaseApi.Arrange(context => TestData.AddWord(context));

        var items = await GetHistoryAsync(word.Id);

        items.Should().BeEmpty();
    }

    [Fact]
    public async Task UnknownWordIsNotFound()
    {
        // G6
        ArrangeWordWithHistory();

        await databaseApi.Client.GetApiAsync(ApiRoutes.GET_WORD_HISTORY, (ApiFields.WORD_ID, Guid.NewGuid().ToString()))
            .ShouldBeProblemAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task WordIdThatIsNotGuidIsBadRequest()
    {
        // G7
        await nowApi.Client.GetApiAsync(ApiRoutes.GET_WORD_HISTORY, (ApiFields.WORD_ID, ApiRequests.NOT_A_GUID))
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Word ArrangeWordWithHistory() =>
        databaseApi.Arrange(context =>
        {
            var word = TestData.AddWord(context);
            TestData.AddHistory(context, word, isKnown: false, MiddleDate);
            TestData.AddHistory(context, word, isKnown: true, NewestDate);
            TestData.AddHistory(context, word, isKnown: true, OldestDate);

            return word;
        });

    private Task<IReadOnlyList<JsonElement>> GetHistoryAsync(Guid wordId) =>
        databaseApi.Client.GetItemsAsync(ApiRoutes.GET_WORD_HISTORY, (ApiFields.WORD_ID, wordId.ToString()));
}
