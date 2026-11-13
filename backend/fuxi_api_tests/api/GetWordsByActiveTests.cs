using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section E: GetWordsByActive.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetWordsByActiveTests : IDisposable
{
    private const int ADDABLE_WORD_COUNT = 3;
    private const int ONE_MINUTE = 1;
    private const string WAITING_NAME = "waiting";
    private const string NEWER_NAME = "a-newer";
    private const string OLDER_NAME = "b-older";
    private const string NEVER_SHOWN_NAME = "c-never-shown";
    private const int OLDER_SHOWN_PERIODS = 2;

    private readonly DatabaseApi api = new();

    [Fact]
    public async Task ReturnsExactlyWordsOfGetNotificationWordsForCurrentDate()
    {
        // E1
        var (due, waiting) = api.Arrange(context =>
        {
            var dueWord = TestData.AddWord(context);
            TestData.AddRotatedWord(context, dueWord);
            var waitingWord = TestData.AddWord(context, WAITING_NAME);
            TestData.AddRotatedWord(context, waitingWord, lastShownDate: TestData.Now);

            return (dueWord, waitingWord);
        });

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        var notificationWords = await api.GetNotificationWordsAsync(api.Clock.GetUtcNow());
        items.Ids().Should().Equal(due.Id);
        items.Ids().Should().NotContain(waiting.Id);
        items.Ids().Should().BeEquivalentTo(notificationWords.Select(word => word.Id));
    }

    [Fact]
    public async Task ItemHasFieldsOfCardWord()
    {
        // E2
        ArrangeWordShownAt(lastShownDate: null);

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        items.Should().ContainSingle().Which.FieldNames().Should().BeEquivalentTo(ApiFields.CARD_WORD_FIELDS);
    }

    [Fact]
    public async Task RotationThatIsNotFullIsToppedUp()
    {
        // E3
        var words = api.Arrange(context => TestData.AddWords(context, ADDABLE_WORD_COUNT));

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        var rotatedWordIds = api.Read(context => context.RotatedWords.AsNoTracking().Select(entry => entry.WordId).ToList());
        rotatedWordIds.Should().BeEquivalentTo(words.Select(word => word.Id));
        items.Ids().Should().BeEquivalentTo(rotatedWordIds);
    }

    [Fact]
    public async Task NoDueWordGivesEmptyList()
    {
        // E4
        ArrangeWordShownAt(TestData.Now);

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        items.Should().BeEmpty();
    }

    [Fact]
    public async Task CurrentDateComesFromFakeClock()
    {
        // E5: the real clock is months ahead, so it would call the Word Due at once.
        var word = ArrangeWordShownAt(TestData.Now.AddMinutes(ONE_MINUTE - TestData.SEEDED_ROTATION_PERIOD));

        var itemsBeforeDueDate = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);
        api.Clock.Advance(TimeSpan.FromMinutes(ONE_MINUTE));
        var itemsAtDueDate = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        itemsBeforeDueDate.Should().BeEmpty();
        itemsAtDueDate.Ids().Should().Equal(word.Id);
    }

    [Fact]
    public async Task ItemsComeInOrderOfGetNotificationWords()
    {
        // Phase 4 E10: never shown first, then the oldest shown, then by name; added out of order.
        var expected = api.Arrange(context =>
        {
            var newer = AddWordShownAt(context, NEWER_NAME, TestData.Now.AddMinutes(-TestData.SEEDED_ROTATION_PERIOD));
            var older = AddWordShownAt(context, OLDER_NAME, TestData.Now.AddMinutes(-TestData.SEEDED_ROTATION_PERIOD * OLDER_SHOWN_PERIODS));
            var neverShown = AddWordShownAt(context, NEVER_SHOWN_NAME, lastShownDate: null);

            return new[] { neverShown, older, newer };
        });

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_ACTIVE);

        items.Ids().Should().Equal(expected.Select(word => word.Id));
    }

    public void Dispose() => api.Dispose();

    // The only Word is already in the Rotation, so the top-up has nothing to add.
    private Word ArrangeWordShownAt(DateTimeOffset? lastShownDate) =>
        api.Arrange(context => AddWordShownAt(context, TestData.WORD_NAME, lastShownDate));

    private static Word AddWordShownAt(FuXiDbContext context, string name, DateTimeOffset? lastShownDate)
    {
        var word = TestData.AddWord(context, name);
        TestData.AddRotatedWord(context, word, lastShownDate: lastShownDate);

        return word;
    }
}
