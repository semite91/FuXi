using System.Net;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section J: GetWordsByFilter.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetWordsByFilterTests : IDisposable
{
    private const string TRUE = "true";
    private const string FALSE = "false";
    private const string NOT_A_BOOLEAN = "maybe";
    private const string ONLY_SPACES = "   ";
    private const string RUN = "run";
    private const string RUN_UPPERCASE = "RUN";
    private const string RUNNER = "Runner";
    private const string OVERRUN = "overrun";
    private const string BRUNCH = "brunch";
    private const string PERCENT_NAME = "100%";
    private const string PERCENT_LOOK_ALIKE = "1000";
    private const string UNDERSCORE_NAME = "a_c";
    private const string UNDERSCORE_LOOK_ALIKE = "abc";
    private const string PLAIN = "plain";
    private const string KNOWN = "known";
    private const string REINFORCED = "reinforced";
    private const string ROTATED = "rotated";
    private const string KNOWN_RUN = "rerun";
    private const string NO_MATCH = "zzz";
    private const string FIRST_NAME = "apple";
    private const string MIDDLE_NAME = "banana";
    private const string LAST_NAME = "cherry";
    private const string MANY_PREFIX = "many";
    private const int MANY_WORD_COUNT = 150;
    private const int SHOWN_COUNT = 5;
    private const int KNOWN_COUNT = 2;
    private const int HOURS_SINCE_SHOWN = 2;
    private const int COUNTER = 4;
    private static readonly string[] FILTER_FIELDS =
        [ApiFields.NAME, ApiFields.IS_REINFORCEMENT, ApiFields.IS_KNOWN, ApiFields.IS_ROTATED];
    private static readonly string[] ITEM_FIELDS =
    [
        ApiFields.ID,
        ApiFields.NAME,
        ApiFields.IS_REINFORCEMENT,
        ApiFields.IS_KNOWN,
        ApiFields.LAST_SHOWN_DATE,
        ApiFields.SHOWN_COUNT,
        ApiFields.KNOWN_COUNT,
        ApiFields.IS_ROTATED,
        ApiFields.COUNTER,
    ];

    private static readonly DateTimeOffset LastShownDate = TestData.Now.AddHours(-HOURS_SINCE_SHOWN);

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task NameMatchesWordsThatStartOrEndWithIt()
    {
        // J1, J2
        databaseApi.Arrange(context => AddWordsNamed(context, RUN, RUNNER, OVERRUN, BRUNCH));

        var items = await FilterAsync((ApiFields.NAME, RUN));

        items.Names().Should().BeEquivalentTo(RUN, RUNNER, OVERRUN);
    }

    [Fact]
    public async Task NameIgnoresCase()
    {
        // J3
        databaseApi.Arrange(context => AddWordsNamed(context, RUNNER, BRUNCH));

        var items = await FilterAsync((ApiFields.NAME, RUN_UPPERCASE));

        items.Names().Should().Equal(RUNNER);
    }

    [Theory]
    [InlineData(PERCENT_NAME, PERCENT_LOOK_ALIKE)] // J4
    [InlineData(UNDERSCORE_NAME, UNDERSCORE_LOOK_ALIKE)] // J5
    public async Task PatternCharactersInNameAreLiteral(string name, string lookAlike)
    {
        // J4, J5
        databaseApi.Arrange(context => AddWordsNamed(context, name, lookAlike));

        var items = await FilterAsync((ApiFields.NAME, name));

        items.Names().Should().Equal(name);
    }

    [Fact]
    public async Task NameOfOnlySpacesCountsAsEmpty()
    {
        // J6: an empty filter is answered without the database, and this host has none.
        var items = await nowApi.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_FILTER, (ApiFields.NAME, ONLY_SPACES));

        items.Should().BeEmpty();
    }

    [Theory]
    [InlineData(ApiFields.IS_REINFORCEMENT, TRUE, REINFORCED)] // J7
    [InlineData(ApiFields.IS_REINFORCEMENT, FALSE, PLAIN, KNOWN, ROTATED)] // J8
    [InlineData(ApiFields.IS_KNOWN, TRUE, KNOWN)] // J9
    [InlineData(ApiFields.IS_KNOWN, FALSE, PLAIN, REINFORCED, ROTATED)] // J10
    [InlineData(ApiFields.IS_ROTATED, TRUE, ROTATED)] // J11
    [InlineData(ApiFields.IS_ROTATED, FALSE, PLAIN, KNOWN, REINFORCED)] // J12
    public async Task OneFilledFieldLimitsOnlyByItself(string field, string value, params string[] expectedNames)
    {
        // J7, J8, J9, J10, J11, J12, J13
        databaseApi.Arrange(AddOneWordOfEachKind);

        var items = await FilterAsync((field, value));

        items.Names().Should().BeEquivalentTo(expectedNames);
    }

    [Fact]
    public async Task TwoFilledFieldsMustBothMatch()
    {
        // J14
        databaseApi.Arrange(context =>
        {
            AddWordsNamed(context, RUN, BRUNCH);
            TestData.AddWord(context, KNOWN_RUN, isKnown: true);
            TestData.AddWord(context, KNOWN, isKnown: true);
        });

        var items = await FilterAsync((ApiFields.NAME, RUN), (ApiFields.IS_KNOWN, TRUE));

        items.Names().Should().Equal(KNOWN_RUN);
    }

    [Fact]
    public async Task FilterWithoutAnyFieldGivesEmptyList()
    {
        // J15
        var items = await nowApi.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_FILTER);

        items.Should().BeEmpty();
    }

    [Fact]
    public async Task FilterWithFourEmptyFieldsGivesEmptyList()
    {
        // J15
        var emptyFields = FILTER_FIELDS.Select(field => (field, (string?)string.Empty)).ToArray();

        var items = await nowApi.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_FILTER, emptyFields);

        items.Should().BeEmpty();
    }

    [Fact]
    public async Task RotatedWordItemHoldsFilterFieldsAndRotationDate()
    {
        // J16, J17
        databaseApi.Arrange(context =>
        {
            var word = TestData.AddWord(
                context, isKnown: true, isReinforcement: true, shownCount: SHOWN_COUNT, knownCount: KNOWN_COUNT);
            TestData.AddRotatedWord(context, word, lastShownDate: LastShownDate);
        });

        var item = (await FilterAsync((ApiFields.NAME, TestData.WORD_NAME))).Should().ContainSingle().Subject;

        item.FieldNames().Should().BeEquivalentTo(ITEM_FIELDS);
        item.Text(ApiFields.NAME).Should().Be(TestData.WORD_NAME);
        item.Flag(ApiFields.IS_REINFORCEMENT).Should().BeTrue();
        item.Flag(ApiFields.IS_KNOWN).Should().BeTrue();
        item.Number(ApiFields.SHOWN_COUNT).Should().Be(SHOWN_COUNT);
        item.Number(ApiFields.KNOWN_COUNT).Should().Be(KNOWN_COUNT);
        item.Flag(ApiFields.IS_ROTATED).Should().BeTrue();
        item.Date(ApiFields.LAST_SHOWN_DATE).Should().Be(LastShownDate);
    }

    [Fact]
    public async Task WordOutsideRotationHasNoRotationDate()
    {
        // J18
        databaseApi.Arrange(context => TestData.AddWord(context));

        var item = (await FilterAsync((ApiFields.NAME, TestData.WORD_NAME))).Should().ContainSingle().Subject;

        item.Flag(ApiFields.IS_ROTATED).Should().BeFalse();
        item.Date(ApiFields.LAST_SHOWN_DATE).Should().BeNull();
    }

    [Fact]
    public async Task ItemHoldsWordId()
    {
        // Phase 3 K1
        var word = databaseApi.Arrange(context => TestData.AddWord(context));

        var item = (await FilterAsync((ApiFields.NAME, TestData.WORD_NAME))).Should().ContainSingle().Subject;

        item.GuidOf(ApiFields.ID).Should().Be(word.Id);
    }

    [Fact]
    public async Task RotatedWordItemHoldsRotationCounter()
    {
        // Phase 3 K2
        databaseApi.Arrange(context =>
        {
            var word = TestData.AddWord(context);
            TestData.AddRotatedWord(context, word, counter: COUNTER);
        });

        var item = (await FilterAsync((ApiFields.NAME, TestData.WORD_NAME))).Should().ContainSingle().Subject;

        item.Number(ApiFields.COUNTER).Should().Be(COUNTER);
    }

    [Fact]
    public async Task WordOutsideRotationHasNoCounter()
    {
        // Phase 3 K3
        databaseApi.Arrange(context => TestData.AddWord(context));

        var item = (await FilterAsync((ApiFields.NAME, TestData.WORD_NAME))).Should().ContainSingle().Subject;

        item.GetProperty(ApiFields.COUNTER).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task AllMatchingWordsAreReturnedWithoutPagination()
    {
        // J19
        var words = databaseApi.Arrange(context => TestData.AddWords(context, MANY_WORD_COUNT, MANY_PREFIX));

        var items = await FilterAsync((ApiFields.NAME, MANY_PREFIX));

        items.Should().HaveCount(MANY_WORD_COUNT);
        items.Names().Should().BeEquivalentTo(words.Select(word => word.Name));
    }

    [Fact]
    public async Task MatchingWordsAreOrderedByName()
    {
        // J20: stored in another order than the one expected back.
        databaseApi.Arrange(context => AddWordsNamed(context, LAST_NAME, FIRST_NAME, MIDDLE_NAME));

        var items = await FilterAsync((ApiFields.IS_KNOWN, FALSE));

        items.Names().Should().Equal(FIRST_NAME, MIDDLE_NAME, LAST_NAME);
    }

    [Fact]
    public async Task NoMatchingWordGivesEmptyList()
    {
        // J21
        databaseApi.Arrange(context => AddWordsNamed(context, RUN, BRUNCH));

        var items = await FilterAsync((ApiFields.NAME, NO_MATCH));

        items.Should().BeEmpty();
    }

    [Fact]
    public async Task ValueThatIsNotBooleanIsBadRequest()
    {
        // J22
        await nowApi.Client.GetApiAsync(ApiRoutes.GET_WORDS_BY_FILTER, (ApiFields.IS_KNOWN, NOT_A_BOOLEAN))
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private static void AddWordsNamed(FuXiDbContext context, params string[] names)
    {
        foreach (var name in names)
        {
            TestData.AddWord(context, name);
        }
    }

    // Each Word differs from the plain one in exactly one filter field.
    private static void AddOneWordOfEachKind(FuXiDbContext context)
    {
        TestData.AddWord(context, PLAIN);
        TestData.AddWord(context, KNOWN, isKnown: true);
        TestData.AddWord(context, REINFORCED, isReinforcement: true);
        TestData.AddRotatedWord(context, TestData.AddWord(context, ROTATED));
    }

    private Task<IReadOnlyList<JsonElement>> FilterAsync(params (string Name, string? Value)[] filter) =>
        databaseApi.Client.GetItemsAsync(ApiRoutes.GET_WORDS_BY_FILTER, filter);
}
