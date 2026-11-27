using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section H: ClearWordContent.</summary>
[Collection(nameof(SmokeTests))]
public sealed class ClearWordContentTests : IDisposable
{
    private const string CONTENT = "A story about an apple.";
    private const int SHOWN_COUNT = 5;
    private const int KNOWN_COUNT = 2;

    private readonly DatabaseApi databaseApi = new();

    [Fact]
    public async Task EveryWordContentIsEmptiedAndNoOtherColumnChanges()
    {
        // H8, H9
        var (word, other) = databaseApi.Arrange(context => (
            TestData.AddWord(context, isKnown: true, isReinforcement: true, shownCount: SHOWN_COUNT, knownCount: KNOWN_COUNT, content: CONTENT),
            TestData.AddWord(context, TestData.OTHER_WORD_NAME, content: CONTENT)));

        await databaseApi.Client.PostApiAsync(ApiRoutes.CLEAR_WORD_CONTENT, new { }).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).Content.Should().BeNull();
        ReadWord(other).Content.Should().BeNull();
        ReadWord(word).Should().BeEquivalentTo(word, options => options.Excluding(expected => expected.Content));
    }

    [Fact]
    public async Task WordsWithoutContentStayAsTheyAre()
    {
        // H10
        var word = databaseApi.Arrange(context => TestData.AddWord(context));

        await databaseApi.Client.PostApiAsync(ApiRoutes.CLEAR_WORD_CONTENT, new { }).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).Should().BeEquivalentTo(word);
    }

    public void Dispose() => databaseApi.Dispose();

    private Word ReadWord(Word word) =>
        databaseApi.Read(context => context.Words.AsNoTracking().Single(stored => stored.Id == word.Id));
}
