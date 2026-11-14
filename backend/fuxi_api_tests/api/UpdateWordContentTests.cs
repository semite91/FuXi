using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section H: UpdateWordContent.</summary>
[Collection(nameof(SmokeTests))]
public sealed class UpdateWordContentTests : IDisposable
{
    private const string CONTENT = "A story about an apple.";
    private const string OLD_CONTENT = "An older story.";
    private const string INJECTION_CONTENT = "It's \"quoted\"'); DROP TABLE \"Words\"; SELECT * FROM \"Config\" WHERE 'a' = 'a' --";
    private const int SHOWN_COUNT = 5;
    private const int KNOWN_COUNT = 2;
    private const int TWO_WORDS = 2;

    // Phase 5b: a Drive photo is a JPEG data: URL; 120 KB is the upper end of its stored size.
    private const int DRIVE_PHOTO_BYTES = 120 * 1024;
    private const string DRIVE_PHOTO_START = "{\"method\":\"photo\",\"image_url\":\"data:image/jpeg;base64,";
    private const string DRIVE_PHOTO_END = "\"}";
    private const char BASE64_CHARACTER = 'A';

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Fact]
    public async Task ContentIsStoredAndNoOtherColumnChanges()
    {
        // H1, H2
        var word = databaseApi.Arrange(context => TestData.AddWord(
            context, isKnown: true, isReinforcement: true, shownCount: SHOWN_COUNT, knownCount: KNOWN_COUNT, content: OLD_CONTENT));

        await UpdateAsync(word.Id, CONTENT).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var stored = ReadWord(word);
        stored.Content.Should().Be(CONTENT);
        stored.Should().BeEquivalentTo(word, options => options.Excluding(expected => expected.Content));
    }

    [Fact]
    public async Task OtherWordIsNotChanged()
    {
        // H3
        var (word, other) = databaseApi.Arrange(context =>
            (TestData.AddWord(context), TestData.AddWord(context, TestData.OTHER_WORD_NAME, content: OLD_CONTENT)));

        await UpdateAsync(word.Id, CONTENT).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(other).Should().BeEquivalentTo(other);
    }

    [Fact]
    public async Task QuotesAndSqlKeywordsAreStoredAsPlainText()
    {
        // H4
        var (word, other) = databaseApi.Arrange(context =>
            (TestData.AddWord(context), TestData.AddWord(context, TestData.OTHER_WORD_NAME)));

        await UpdateAsync(word.Id, INJECTION_CONTENT).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        ReadWord(word).Content.Should().Be(INJECTION_CONTENT);
        ReadWord(other).Should().BeEquivalentTo(other);
        databaseApi.Read(context => context.Words.Count()).Should().Be(TWO_WORDS);
        databaseApi.Read(context => context.Configs.Count()).Should().Be(TestData.SEEDED_CONFIG_COUNT);
    }

    [Fact]
    public async Task DrivePhotoContentOfAbout120KilobytesIsStoredUnchanged()
    {
        // 5b J3
        var payloadLength = DRIVE_PHOTO_BYTES - DRIVE_PHOTO_START.Length - DRIVE_PHOTO_END.Length;
        var drivePhoto = DRIVE_PHOTO_START + new string(BASE64_CHARACTER, payloadLength) + DRIVE_PHOTO_END;
        var word = databaseApi.Arrange(context => TestData.AddWord(context));

        await UpdateAsync(word.Id, drivePhoto).ShouldHaveStatusAsync(HttpStatusCode.NoContent);

        var stored = ReadWord(word).Content;
        stored.Should().HaveLength(DRIVE_PHOTO_BYTES);
        stored.Should().Be(drivePhoto);
    }

    [Fact]
    public async Task UnknownWordIsNotFound()
    {
        // H5
        databaseApi.Arrange(context => TestData.AddWord(context));

        await UpdateAsync(Guid.NewGuid(), CONTENT).ShouldBeProblemAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task IdThatIsNotGuidIsBadRequest()
    {
        // H6
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_CONTENT, new { id = ApiRequests.NOT_A_GUID, content = CONTENT })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task EmptyContentIsBadRequest()
    {
        // H7
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_CONTENT, new { id = Guid.NewGuid(), content = string.Empty })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingContentIsBadRequest()
    {
        // H7
        await nowApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_CONTENT, new { id = Guid.NewGuid() })
            .ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private Task<HttpResponseMessage> UpdateAsync(Guid id, string content) =>
        databaseApi.Client.PostApiAsync(ApiRoutes.UPDATE_WORD_CONTENT, new { id, content });

    private Word ReadWord(Word word) =>
        databaseApi.Read(context => context.Words.AsNoTracking().Single(stored => stored.Id == word.Id));
}
