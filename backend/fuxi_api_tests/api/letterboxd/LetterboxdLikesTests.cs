using System.Net;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api.Letterboxd;

/// <summary>
/// Phase 6d sections A and B (test_scenarios_2026_11_18_12_40): POST /api/UploadLetterboxdLikes and
/// GET /api/GetLetterboxdLikes.
/// </summary>
[Collection(nameof(SmokeTests))]
public sealed class LetterboxdLikesTests : IDisposable
{
    private const string NOT_A_LIKES_FILE = "The file must be a CSV with the Date, Name and Year columns.";
    private const string HEADER = "Date,Name,Year,Letterboxd URI";
    private const string FILM = "2024-03-01,Perfect Days,2023,https://boxd.it/aaaa";
    private const string OTHER_FILM = "2024-04-02,\"Hello, World\",2019,https://boxd.it/bbbb";
    private const string SECRET_NAME = "Secret Film Name";
    private const int MAX_BYTES = 5 * 1024 * 1024;

    private static readonly UTF8Encoding STRICT_UTF8 = new(false);
    private readonly DatabaseApi api = new();

    [Fact]
    public async Task ValidCsvIsSavedAndCounted()
    {
        // A1
        var csv = Csv(HEADER, FILM, OTHER_FILM);

        using var response = await UploadAsync(csv);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadJsonAsync()).Number(ApiFields.MOVIE_COUNT).Should().Be(2);
        ReadRows()[SettingCodes.LETTERBOXD_LIKED_FILMS_CSV].Should().Be(csv);
    }

    [Fact]
    public async Task BomAndExtraColumnsAreAcceptedAndTextIsKept()
    {
        // A2
        var csv = "﻿" + Csv(HEADER, FILM);

        using var response = await UploadAsync(csv);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        ReadRows()[SettingCodes.LETTERBOXD_LIKED_FILMS_CSV].Should().Be(csv);
    }

    [Fact]
    public async Task QuotedNewlineInANameIsOneRow()
    {
        // A1: a name may hold a comma or a line break inside its quotes
        var csv = Csv(HEADER, "2024-03-01,\"Two\nLines\",2020,https://boxd.it/cccc", FILM);

        using var response = await UploadAsync(csv);

        (await response.ReadJsonAsync()).Number(ApiFields.MOVIE_COUNT).Should().Be(2);
    }

    [Fact]
    public async Task NewUploadUpdatesTheRowInPlace()
    {
        // A3
        (await UploadAsync(Csv(HEADER, FILM))).Dispose();
        var idBefore = ReadRowId();
        var newCsv = Csv(HEADER, OTHER_FILM);

        using var response = await UploadAsync(newCsv);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        ReadRowId().Should().Be(idBefore);
        ReadRows()[SettingCodes.LETTERBOXD_LIKED_FILMS_CSV].Should().Be(newCsv);
    }

    [Theory]
    [InlineData("Name,Year")]
    [InlineData("Date,Year")]
    [InlineData("Date,Name")]
    [InlineData("date,name,year")]
    public async Task MissingColumnIsRefused(string header)
    {
        // A4
        using var response = await UploadAsync(Csv(header, "2024-03-01,Perfect Days"));

        await AssertRefusedAsync(response);
    }

    [Theory]
    [InlineData("")]
    [InlineData(HEADER)]
    public async Task EmptyOrHeaderOnlyFileIsRefused(string text)
    {
        // A5
        using var response = await UploadAsync(text);

        await AssertRefusedAsync(response);
    }

    [Fact]
    public async Task MissingFilePartIsRefused()
    {
        // A5
        using var response = await api.Client.PostFileApiAsync(
            ApiRoutes.UPLOAD_LETTERBOXD_LIKES, STRICT_UTF8.GetBytes(Csv(HEADER, FILM)), partName: "other");

        await AssertRefusedAsync(response);
    }

    [Fact]
    public async Task FileThatIsNotUtf8IsRefused()
    {
        // A6
        byte[] bytes = [.. STRICT_UTF8.GetBytes(HEADER + "\n2024-03-01,"), 0xC3, 0x28, .. STRICT_UTF8.GetBytes(",2023\n")];

        using var response = await api.Client.PostFileApiAsync(ApiRoutes.UPLOAD_LETTERBOXD_LIKES, bytes);

        await AssertRefusedAsync(response);
    }

    [Fact]
    public async Task FileLargerThanFiveMegabytesIsRefused()
    {
        // A6
        var bigRow = "2024-03-01,Perfect Days,2023," + new string('x', 1000);
        var rows = Enumerable.Repeat(bigRow, (MAX_BYTES / bigRow.Length) + 1);

        using var response = await UploadAsync(Csv(HEADER, [.. rows]));

        await AssertRefusedAsync(response);
    }

    [Fact]
    public async Task FileWithANulCharacterIsRefusedNotAServerError()
    {
        // A6, review: PostgreSQL text cannot hold U+0000
        using var response = await UploadAsync(Csv(HEADER, "2024-03-01,Perfect\0Days,2023,https://boxd.it/aaaa"));

        await AssertRefusedAsync(response);
        ReadRows().Should().NotContainKey(SettingCodes.LETTERBOXD_LIKED_FILMS_CSV);
    }

    [Fact]
    public async Task UploadWithoutTheAppHeaderIsRefused()
    {
        // review: a form on another website sends no custom header, so it is refused
        using var response = await api.Client.PostFileApiAsync(
            ApiRoutes.UPLOAD_LETTERBOXD_LIKES, STRICT_UTF8.GetBytes(Csv(HEADER, FILM)), withAppHeader: false);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
        ReadRows().Should().NotContainKey(SettingCodes.LETTERBOXD_LIKED_FILMS_CSV);
    }

    [Fact]
    public async Task OnlyRowsWithANameAndANumericYearAreCounted()
    {
        // A1, review: the engine skips the other rows, so they are not movies
        var csv = Csv(HEADER, FILM, "2024-03-02,,2020,https://boxd.it/x1", "2024-03-03,No Year,n/a,https://boxd.it/x2", "2024-03-04,Empty Year,,https://boxd.it/x3", OTHER_FILM);

        using var response = await UploadAsync(csv);

        (await response.ReadJsonAsync()).Number(ApiFields.MOVIE_COUNT).Should().Be(2);
    }

    [Fact]
    public async Task FileWithOnlyUnusableRowsIsRefused()
    {
        // A5, review
        using var response = await UploadAsync(Csv(HEADER, "2024-03-02,,2020,https://boxd.it/x1", "2024-03-03,No Year,n/a,https://boxd.it/x2"));

        await AssertRefusedAsync(response);
    }

    [Fact]
    public async Task RefusedUploadKeepsTheOldText()
    {
        // A7
        var oldCsv = Csv(HEADER, FILM);
        (await UploadAsync(oldCsv)).Dispose();

        (await UploadAsync(Csv("Name,Year", "Perfect Days,2023"))).Dispose();

        ReadRows()[SettingCodes.LETTERBOXD_LIKED_FILMS_CSV].Should().Be(oldCsv);
    }

    [Fact]
    public async Task NoLogAndNoAnswerHoldsAMovieName()
    {
        // A8
        using var refused = await UploadAsync(Csv("Name,Year", $"{SECRET_NAME},2023"));
        using var accepted = await UploadAsync(Csv(HEADER, $"2024-03-01,{SECRET_NAME},2023,https://boxd.it/dddd"));

        (await refused.ReadTextAsync()).Should().NotContain(SECRET_NAME);
        (await accepted.ReadTextAsync()).Should().NotContain(SECRET_NAME);
        api.Logs.Entries.Should().NotContain(entry => entry.Message.Contains(SECRET_NAME));
    }

    [Fact]
    public async Task NoRowIsNoUpload()
    {
        // B1
        var answer = await GetLikesAsync();

        answer.Flag(ApiFields.HAS_UPLOAD).Should().BeFalse();
        answer.Number(ApiFields.MOVIE_COUNT).Should().Be(0);
    }

    [Fact]
    public async Task EmptyRowIsNoUpload()
    {
        // B1
        AddRow(string.Empty);

        var answer = await GetLikesAsync();

        answer.Flag(ApiFields.HAS_UPLOAD).Should().BeFalse();
        answer.Number(ApiFields.MOVIE_COUNT).Should().Be(0);
    }

    [Fact]
    public async Task SavedCsvIsCounted()
    {
        // B2
        AddRow(Csv(HEADER, FILM, OTHER_FILM, "2024-05-03,Third,2021,https://boxd.it/eeee"));

        var answer = await GetLikesAsync();

        answer.Flag(ApiFields.HAS_UPLOAD).Should().BeTrue();
        answer.Number(ApiFields.MOVIE_COUNT).Should().Be(3);
    }

    [Fact]
    public async Task AnswerHoldsNoCsvText()
    {
        // B3
        AddRow(Csv(HEADER, $"2024-03-01,{SECRET_NAME},2023,https://boxd.it/dddd"));

        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_LETTERBOXD_LIKES);

        (await response.ReadTextAsync()).Should().NotContain(SECRET_NAME);
        (await response.ReadJsonAsync()).FieldNames().Should().BeEquivalentTo(ApiFields.HAS_UPLOAD, ApiFields.MOVIE_COUNT);
    }

    public void Dispose() => api.Dispose();

    private static string Csv(string header, params string[] rows) => string.Join('\n', [header, .. rows]) + "\n";

    private static async Task AssertRefusedAsync(HttpResponseMessage response)
    {
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
        (await response.ReadJsonAsync()).Text(ApiFields.DETAIL).Should().Be(NOT_A_LIKES_FILE);
    }

    private Task<HttpResponseMessage> UploadAsync(string text) =>
        api.Client.PostFileApiAsync(ApiRoutes.UPLOAD_LETTERBOXD_LIKES, STRICT_UTF8.GetBytes(text));

    private async Task<JsonElement> GetLikesAsync()
    {
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_LETTERBOXD_LIKES);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return await response.ReadJsonAsync();
    }

    private void AddRow(string value) =>
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.LETTERBOXD_LIKED_FILMS_CSV, Value = value });
            context.SaveChanges();
        });

    private Guid ReadRowId() =>
        api.Read(context => context.Settings.AsNoTracking().Single(setting => setting.Code == SettingCodes.LETTERBOXD_LIKED_FILMS_CSV).Id);

    private Dictionary<string, string> ReadRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));
}
