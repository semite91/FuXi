using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section I: UpdateIsReinforcement.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateIsReinforcementTests : IDisposable
{
    private const int HISTORY_COUNT = 2;
    private const int HOURS_SINCE_FIRST_ANSWER = 1;

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Theory]
    [InlineData(false, true)] // I1, I3
    [InlineData(true, false)] // I2, I4
    public async Task FlagIsSetAndWordLeavesRotation(bool wasReinforcement, bool isReinforcement)
    {
        // I1, I2, I3, I4
        var word = ArrangeWord(wasReinforcement, isRotated: true);

        await UpdateAsync(word.Id, isReinforcement).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).IsReinforcement.Should().Be(isReinforcement);
        ReadRotatedWordIds().Should().BeEmpty();
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task WordOutsideRotationIsUpdatedWithoutError(bool isReinforcement)
    {
        // I5
        var word = ArrangeWord(!isReinforcement, isRotated: false);

        await UpdateAsync(word.Id, isReinforcement).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).IsReinforcement.Should().Be(isReinforcement);
    }

    [Fact]
    public async Task OtherWordStaysInRotation()
    {
        // I6
        var word = ArrangeWord(wasReinforcement: false, isRotated: true);
        var other = ArrangeWord(wasReinforcement: false, isRotated: true, TestData.OTHER_WORD_NAME);

        await UpdateAsync(word.Id, isReinforcement: true).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadRotatedWordIds().Should().Equal(other.Id);
        ReadWord(other).Should().BeEquivalentTo(other);
    }

    [Fact]
    public async Task WordHistoryIsKept()
    {
        // I7
        var word = ArrangeWord(wasReinforcement: false, isRotated: true);
        databaseApi.Arrange(context =>
        {
            TestData.AddHistory(context, word, isKnown: false, TestData.Now.AddHours(-HOURS_SINCE_FIRST_ANSWER));
            TestData.AddHistory(context, word, isKnown: true, TestData.Now);
        });

        await UpdateAsync(word.Id, isReinforcement: true).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        databaseApi.Read(context => context.WordHistories.Count(history => history.WordId == word.Id)).Should().Be(HISTORY_COUNT);
    }

    [Fact]
    public async Task FailureWhileDeletingRotationEntryKeepsFlag()
    {
        // I8
        var word = ArrangeWord(wasReinforcement: false, isRotated: true);
        databaseApi.Arrange(TestData.FailRotatedWordDelete);

        await UpdateAsync(word.Id, isReinforcement: true).ShouldBeProblemAsync(HttpStatusCode.InternalServerError);

        ReadWord(word).IsReinforcement.Should().BeFalse();
        ReadRotatedWordIds().Should().Equal(word.Id);
    }

    [Fact]
    public async Task UnknownWordIsNotFound()
    {
        // I9
        ArrangeWord(wasReinforcement: false, isRotated: true);

        await UpdateAsync(Guid.NewGuid(), isReinforcement: true).ShouldBeProblemAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task WordIdThatIsNotGuidIsBadRequest()
    {
        // I10
        await nowApi.Client
            .PostApiAsync(ApiRoutes.UPDATE_IS_REINFORCEMENT, new { wordId = ApiRequests.NOT_A_GUID, isReinforcement = true })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task RequestWithoutIsReinforcementIsBadRequest()
    {
        // I11
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_IS_REINFORCEMENT, new { wordId = Guid.NewGuid() })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Word ArrangeWord(bool wasReinforcement, bool isRotated, string name = TestData.WORD_NAME) =>
        databaseApi.Arrange(context =>
        {
            var word = TestData.AddWord(context, name, isReinforcement: wasReinforcement);
            if (isRotated)
            {
                TestData.AddRotatedWord(context, word);
            }

            return word;
        });

    private Task<HttpResponseMessage> UpdateAsync(Guid wordId, bool isReinforcement) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_IS_REINFORCEMENT, new { wordId, isReinforcement });

    private Word ReadWord(Word word) =>
        databaseApi.Read(context => context.Words.AsNoTracking().Single(stored => stored.Id == word.Id));

    private List<Guid> ReadRotatedWordIds() =>
        databaseApi.Read(context => context.RotatedWords.AsNoTracking().Select(entry => entry.WordId).ToList());
}
