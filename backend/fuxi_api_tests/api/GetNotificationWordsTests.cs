using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Words;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section C: the internal function that tops up the Rotation and returns the Due Words.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetNotificationWordsTests : IDisposable
{
    private const int NEARLY_FULL_ROTATION = 17;
    private const int FULL_ROTATION = TestData.SEEDED_ROTATION_COUNT;
    private const int OVERFULL_ROTATION = 22;
    private const int SPARE_WORD_COUNT = 10;
    private const int SMALL_ROTATION_COUNT = 3;
    private const int ADDABLE_WORD_COUNT = 2;
    private const int SINGLE_ROTATION_COUNT = 1;
    private const int RANDOM_RUN_COUNT = 30;
    private const int MINIMUM_DIFFERENT_CHOICES = 2;
    private const int COUNTER = 2;
    private const int DUE_AFTER_MINUTES = COUNTER * TestData.SEEDED_ROTATION_PERIOD;
    private const int REINFORCED_COUNTER = 5;
    private const int CHANGED_ROTATION_PERIOD = 60;
    private const int CHANGED_REINFORCEMENT_PERIOD = 120;
    private const int MINUTES_BETWEEN_OLD_AND_NEW_ROTATION_PERIOD = 30;
    private const int ONE_MINUTE = 1;
    private const int HOURS_AWAY_FROM_CLOCK = 48;
    private const string SPARE_PREFIX = "spare";
    private const string REINFORCED_NAME = "reinforced";

    private readonly DatabaseApi api = new();

    [Theory]
    [InlineData(NEARLY_FULL_ROTATION, FULL_ROTATION)] // C1
    [InlineData(FULL_ROTATION, FULL_ROTATION)] // C2
    [InlineData(OVERFULL_ROTATION, OVERFULL_ROTATION)] // C3
    public async Task TopUpFillsRotationUpToRotationCount(int entriesBefore, int entriesAfter)
    {
        // C1, C2, C3
        var rotated = api.Arrange(context =>
        {
            TestData.AddWords(context, SPARE_WORD_COUNT, SPARE_PREFIX);

            return TestData.AddRotatedWords(context, entriesBefore);
        });

        await api.GetNotificationWordsAsync(TestData.Now);

        var rotatedWordIds = ReadRotatedWordIds();
        rotatedWordIds.Should().HaveCount(entriesAfter);
        rotatedWordIds.Should().Contain(rotated.Select(word => word.Id));
    }

    [Theory]
    [InlineData(false, false, true)] // C4
    [InlineData(true, true, true)] // C5
    [InlineData(false, true, true)] // The rule's third allowed combination.
    [InlineData(true, false, false)] // C6
    public async Task TopUpAddsOnlyWordsThatAreNotKnownOrAreReinforced(bool isKnown, bool isReinforcement, bool isAdded)
    {
        // C4, C5, C6
        var word = api.Arrange(context => TestData.AddWord(context, isKnown: isKnown, isReinforcement: isReinforcement));

        await api.GetNotificationWordsAsync(TestData.Now);

        ReadRotatedWordIds().Contains(word.Id).Should().Be(isAdded);
    }

    [Fact]
    public async Task TopUpAddsNoSecondEntryForRotatedWord()
    {
        // C7
        var word = api.Arrange(context => TestData.AddRotatedWords(context, SINGLE_ROTATION_COUNT).Single());

        await api.GetNotificationWordsAsync(TestData.Now);

        ReadRotatedWordIds().Should().Equal(word.Id);
    }

    [Fact]
    public async Task TopUpAddsOnlyWordsThatExist()
    {
        // C8
        var addable = api.Arrange(context =>
        {
            TestData.SetConfig(context, TestData.ROTATION_COUNT_CODE, SMALL_ROTATION_COUNT);
            TestData.AddWord(context, TestData.OTHER_WORD_NAME, isKnown: true);

            return TestData.AddWords(context, ADDABLE_WORD_COUNT);
        });

        await api.GetNotificationWordsAsync(TestData.Now);

        ReadRotatedWordIds().Should().BeEquivalentTo(addable.Select(word => word.Id));
    }

    [Fact]
    public async Task TopUpWithoutAddableWordAddsNothing()
    {
        // C9
        api.Arrange(context => TestData.AddWord(context, isKnown: true));

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Should().BeEmpty();
        ReadRotatedWordIds().Should().BeEmpty();
    }

    [Fact]
    public async Task AddedEntryStartsWithCounterOneAndNoLastShownDate()
    {
        // C10, C11
        api.Arrange(context => TestData.AddWord(context));

        await api.GetNotificationWordsAsync(TestData.Now);

        var entry = api.Read(context => context.RotatedWords.AsNoTracking().Single());
        entry.Counter.Should().Be(TestData.FIRST_COUNTER);
        entry.LastShownDate.Should().BeNull();
    }

    [Fact]
    public async Task TopUpChoosesWordsRandomly()
    {
        // C12: the Rotation is emptied before each run, so every run starts from the same data.
        api.Arrange(context =>
        {
            TestData.SetConfig(context, TestData.ROTATION_COUNT_CODE, SINGLE_ROTATION_COUNT);
            TestData.AddWords(context, SPARE_WORD_COUNT);
        });
        var chosenWordIds = new HashSet<Guid>();

        for (var run = 0; run < RANDOM_RUN_COUNT; run++)
        {
            api.Arrange(context => context.RotatedWords.ExecuteDelete());
            await api.GetNotificationWordsAsync(TestData.Now);
            chosenWordIds.Add(ReadRotatedWordIds().Should().ContainSingle().Subject);
        }

        chosenWordIds.Should().HaveCountGreaterThanOrEqualTo(MINIMUM_DIFFERENT_CHOICES);
    }

    [Fact]
    public async Task NeverShownWordIsDue()
    {
        // C13
        var word = ArrangeRotatedWord(lastShownDate: null);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Select(due => due.Id).Should().Equal(word.Id);
    }

    [Theory]
    [InlineData(DUE_AFTER_MINUTES, true)] // C14
    [InlineData(DUE_AFTER_MINUTES - ONE_MINUTE, false)] // C15
    public async Task WordIsDueAfterCounterTimesRotationPeriod(int minutesSinceShown, bool isDue)
    {
        // C14, C15
        var word = ArrangeRotatedWord(TestData.Now.AddMinutes(-minutesSinceShown), COUNTER);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Any(due => due.Id == word.Id).Should().Be(isDue);
    }

    [Theory]
    [InlineData(TestData.SEEDED_REINFORCEMENT_PERIOD, true)] // C16
    [InlineData(TestData.SEEDED_REINFORCEMENT_PERIOD - ONE_MINUTE, false)] // C17
    public async Task ReinforcedWordIsDueAfterReinforcementPeriod(int minutesSinceShown, bool isDue)
    {
        // C16, C17
        var word = ArrangeRotatedWord(TestData.Now.AddMinutes(-minutesSinceShown), isReinforcement: true);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Any(due => due.Id == word.Id).Should().Be(isDue);
    }

    [Fact]
    public async Task ReinforcedWordIgnoresCounter()
    {
        // C18: with the Counter in the rule the Word would wait five times longer.
        var lastShownDate = TestData.Now.AddMinutes(-TestData.SEEDED_REINFORCEMENT_PERIOD);
        var word = ArrangeRotatedWord(lastShownDate, REINFORCED_COUNTER, isReinforcement: true);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Select(due => due.Id).Should().Equal(word.Id);
    }

    [Fact]
    public async Task KnownWordInRotationIsReturnedWhenDue()
    {
        // C19
        var word = ArrangeRotatedWord(lastShownDate: null, isKnown: true);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Select(due => due.Id).Should().Equal(word.Id);
    }

    [Fact]
    public async Task WordAddedByTopUpIsReturnedInSameRun()
    {
        // C20
        var word = api.Arrange(context => TestData.AddWord(context));

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Select(due => due.Id).Should().Equal(word.Id);
    }

    [Fact]
    public async Task DueRuleUsesGivenDateInsteadOfClock()
    {
        // C21: the clock stays at its start, far from the dates given here.
        var lastShownDate = TestData.Now.AddHours(HOURS_AWAY_FROM_CLOCK);
        var dueDate = lastShownDate.AddMinutes(TestData.SEEDED_ROTATION_PERIOD);
        var word = ArrangeRotatedWord(lastShownDate);

        var wordsBeforeDueDate = await api.GetNotificationWordsAsync(dueDate.AddMinutes(-ONE_MINUTE));
        var wordsAtDueDate = await api.GetNotificationWordsAsync(dueDate);

        wordsBeforeDueDate.Should().BeEmpty();
        wordsAtDueDate.Select(due => due.Id).Should().Equal(word.Id);
    }

    [Fact]
    public async Task ChangedPeriodsAreUsed()
    {
        // C22: each Word gets the opposite result under the seeded periods.
        var (waiting, reinforced) = api.Arrange(context =>
        {
            TestData.SetConfig(context, TestData.ROTATION_PERIOD_CODE, CHANGED_ROTATION_PERIOD);
            TestData.SetConfig(context, TestData.REINFORCEMENT_PERIOD_CODE, CHANGED_REINFORCEMENT_PERIOD);
            var waitingWord = TestData.AddWord(context);
            TestData.AddRotatedWord(
                context, waitingWord, lastShownDate: TestData.Now.AddMinutes(-MINUTES_BETWEEN_OLD_AND_NEW_ROTATION_PERIOD));
            var reinforcedWord = TestData.AddWord(context, REINFORCED_NAME, isReinforcement: true);
            TestData.AddRotatedWord(
                context, reinforcedWord, lastShownDate: TestData.Now.AddMinutes(-CHANGED_REINFORCEMENT_PERIOD));

            return (waitingWord, reinforcedWord);
        });

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Select(due => due.Id).Should().Equal(reinforced.Id);
        words.Should().NotContain(due => due.Id == waiting.Id);
    }

    [Fact]
    public async Task ResultItemHoldsOnlyIdAndName()
    {
        // C23
        var word = ArrangeRotatedWord(lastShownDate: null);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Should().Equal(new NotificationWord(word.Id, word.Name));
        typeof(NotificationWord).GetProperties().Select(property => property.Name)
            .Should().BeEquivalentTo(nameof(NotificationWord.Id), nameof(NotificationWord.Name));
    }

    [Fact]
    public async Task NoDueWordGivesEmptyList()
    {
        // C24
        ArrangeRotatedWord(TestData.Now);

        var words = await api.GetNotificationWordsAsync(TestData.Now);

        words.Should().BeEmpty();
    }

    public void Dispose() => api.Dispose();

    // The only Word is already in the Rotation, so the top-up has nothing to add.
    private Word ArrangeRotatedWord(
        DateTimeOffset? lastShownDate, int counter = TestData.FIRST_COUNTER, bool isKnown = false, bool isReinforcement = false) =>
        api.Arrange(context =>
        {
            var word = TestData.AddWord(context, isKnown: isKnown, isReinforcement: isReinforcement);
            TestData.AddRotatedWord(context, word, counter, lastShownDate);

            return word;
        });

    private List<Guid> ReadRotatedWordIds() =>
        api.Read(context => context.RotatedWords.AsNoTracking().Select(entry => entry.WordId).ToList());
}
