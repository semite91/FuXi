using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section F: UpdateWordKnownStatus.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateWordKnownStatusTests : IDisposable
{
    private const int COUNTER = 3;
    private const int RAISED_COUNTER = 4;
    private const int SHOWN_COUNT = 5;
    private const int RAISED_SHOWN_COUNT = 6;
    private const int KNOWN_COUNT = 2;
    private const int RAISED_KNOWN_COUNT = 3;
    private const int DAYS_SINCE_SHOWN = 1;

    private static readonly DateTimeOffset EarlierShownDate = TestData.Now.AddDays(-DAYS_SINCE_SHOWN);

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Theory]
    [InlineData(true, RAISED_COUNTER)] // F1
    [InlineData(false, TestData.FIRST_COUNTER)] // F2
    public async Task AnswerRaisesOrResetsCounter(bool isKnown, int expectedCounter)
    {
        // F1, F2, F14
        var word = ArrangeRotatedWord();

        await AnswerAsync(word.Id, isKnown).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var entry = ReadRotatedWord(word);
        entry.Should().NotBeNull();
        entry!.Counter.Should().Be(expectedCounter);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task AnswerSetsLastShownDateToNow(bool isKnown)
    {
        // F3
        var word = ArrangeRotatedWord();

        await AnswerAsync(word.Id, isKnown).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadRotatedWord(word)!.LastShownDate.Should().Be(TestData.Now);
    }

    [Theory]
    [InlineData(true, RAISED_KNOWN_COUNT)] // F4, F6
    [InlineData(false, KNOWN_COUNT)] // F5, F7
    public async Task AnswerRaisesShownCountAndCountsKnownAnswers(bool isKnown, int expectedKnownCount)
    {
        // F4, F5, F6, F7
        var word = ArrangeRotatedWord();

        await AnswerAsync(word.Id, isKnown).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var stored = ReadWord(word);
        stored.ShownCount.Should().Be(RAISED_SHOWN_COUNT);
        stored.KnownCount.Should().Be(expectedKnownCount);
    }

    [Theory]
    [InlineData(false, true, true)] // F8
    [InlineData(false, false, false)] // F9
    [InlineData(true, false, true)] // F10
    public async Task WordBecomesKnownAndNeverUnknown(bool wasKnown, bool isKnown, bool expectedIsKnown)
    {
        // F8, F9, F10
        var word = ArrangeRotatedWord(wasKnown);

        await AnswerAsync(word.Id, isKnown).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).IsKnown.Should().Be(expectedIsKnown);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task AnswerAddsOneWordHistoryEntry(bool isKnown)
    {
        // F11, F12, F13
        var word = ArrangeRotatedWord();

        await AnswerAsync(word.Id, isKnown).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var history = databaseApi.Read(context => context.WordHistories.AsNoTracking().ToList()).Should().ContainSingle().Subject;
        history.WordId.Should().Be(word.Id);
        history.IsKnown.Should().Be(isKnown);
        history.Date.Should().Be(TestData.Now);
    }

    [Fact]
    public async Task UnknownWordIsNotFound()
    {
        // F15
        ArrangeRotatedWord();

        await AnswerAsync(Guid.NewGuid(), isKnown: true).ShouldBeProblemAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task WordOutsideRotationIsNotFoundAndNotChanged()
    {
        // F16, F17
        var word = databaseApi.Arrange(context => TestData.AddWord(context, shownCount: SHOWN_COUNT, knownCount: KNOWN_COUNT));

        await AnswerAsync(word.Id, isKnown: true).ShouldBeProblemAsync(HttpStatusCode.NotFound);

        ReadWord(word).Should().BeEquivalentTo(word);
        databaseApi.Read(context => context.WordHistories.Count()).Should().Be(0);
        ReadRotatedWord(word).Should().BeNull();
    }

    [Fact]
    public async Task FailureWhileSavingWordHistoryRollsEverythingBack()
    {
        // F18
        var word = ArrangeRotatedWord();
        var entry = ReadRotatedWord(word);
        databaseApi.Arrange(TestData.FailWordHistoryInsert);

        await AnswerAsync(word.Id, isKnown: true).ShouldBeProblemAsync(HttpStatusCode.InternalServerError);

        ReadWord(word).Should().BeEquivalentTo(word);
        ReadRotatedWord(word).Should().BeEquivalentTo(entry);
        databaseApi.Read(context => context.WordHistories.Count()).Should().Be(0);
    }

    [Fact]
    public async Task WordIdThatIsNotGuidIsBadRequest()
    {
        // F19
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_KNOWN_STATUS, new { wordId = ApiRequests.NOT_A_GUID, isKnown = true })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task RequestWithoutIsKnownIsBadRequest()
    {
        // F20
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_KNOWN_STATUS, new { wordId = Guid.NewGuid() })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Word ArrangeRotatedWord(bool isKnown = false) =>
        databaseApi.Arrange(context =>
        {
            var word = TestData.AddWord(context, isKnown: isKnown, shownCount: SHOWN_COUNT, knownCount: KNOWN_COUNT);
            TestData.AddRotatedWord(context, word, COUNTER, EarlierShownDate);

            return word;
        });

    private Task<HttpResponseMessage> AnswerAsync(Guid wordId, bool isKnown) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_KNOWN_STATUS, new { wordId, isKnown });

    private Word ReadWord(Word word) =>
        databaseApi.Read(context => context.Words.AsNoTracking().Single(stored => stored.Id == word.Id));

    private RotatedWord? ReadRotatedWord(Word word) =>
        databaseApi.Read(context => context.RotatedWords.AsNoTracking().SingleOrDefault(entry => entry.WordId == word.Id));
}
