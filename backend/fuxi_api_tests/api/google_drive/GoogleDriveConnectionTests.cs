using System.Net;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api.GoogleDrive;

/// <summary>
/// Phase 6c section C (test_scenarios_2026_11_17_19_42): GET /api/GetGoogleDriveConnection and
/// POST /api/UpdateGoogleDriveFolder.
/// </summary>
[Collection(nameof(SmokeTests))]
public sealed class GoogleDriveConnectionTests : IDisposable
{
    private const string NOT_A_FOLDER_LINK = "This is not a Google Drive folder link.";
    private const string OTHER_FOLDER_ID = "0BzOtherFolder_Id-42";

    private readonly DatabaseApi api = new();

    [Fact]
    public async Task NoRefreshTokenIsNotConnected()
    {
        // C1
        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.EMAIL).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.FOLDER_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task EmptyRefreshTokenIsNotConnected()
    {
        // C1
        AddRows(string.Empty, GoogleDriveTestData.EMAIL, GoogleDriveTestData.FOLDER_ID);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.EMAIL).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.FOLDER_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task ConnectedAnswersEmailAndFolder()
    {
        // C2
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, GoogleDriveTestData.FOLDER_ID);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.Text(ApiFields.EMAIL).Should().Be(GoogleDriveTestData.EMAIL);
        answer.Text(ApiFields.FOLDER_ID).Should().Be(GoogleDriveTestData.FOLDER_ID);
    }

    [Fact]
    public async Task EmptyEmailAndFolderAnswerNull()
    {
        // C2
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, string.Empty, string.Empty);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.GetProperty(ApiFields.EMAIL).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.FOLDER_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task AnswerHoldsNoRefreshToken()
    {
        // C3
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, GoogleDriveTestData.FOLDER_ID);

        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_GOOGLE_DRIVE_CONNECTION);

        (await response.ReadTextAsync()).Should().NotContain(GoogleDriveTestData.REFRESH_TOKEN);
        (await response.ReadJsonAsync()).FieldNames().Should().BeEquivalentTo(ApiFields.IS_CONNECTED, ApiFields.EMAIL, ApiFields.FOLDER_ID);
    }

    [Theory]
    [InlineData("https://drive.google.com/drive/folders/" + GoogleDriveTestData.FOLDER_ID)]
    [InlineData("https://drive.google.com/drive/folders/" + GoogleDriveTestData.FOLDER_ID + "?usp=sharing")]
    [InlineData("https://drive.google.com/drive/u/0/folders/" + GoogleDriveTestData.FOLDER_ID)]
    [InlineData("https://drive.google.com/drive/u/1/folders/" + GoogleDriveTestData.FOLDER_ID + "/")]
    [InlineData("  https://drive.google.com/drive/folders/" + GoogleDriveTestData.FOLDER_ID + "  ")]
    [InlineData(GoogleDriveTestData.FOLDER_ID)]
    public async Task FolderLinkOrIdIsSavedAsTheFolderId(string folderLink)
    {
        // C4, C5
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, null);

        using var response = await SaveFolderAsync(folderLink);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadJsonAsync()).Text(ApiFields.FOLDER_ID).Should().Be(GoogleDriveTestData.FOLDER_ID);
        ReadRows()[SettingCodes.GOOGLE_DRIVE_FOLDER_ID].Should().Be(GoogleDriveTestData.FOLDER_ID);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("https://drive.google.com/file/d/" + GoogleDriveTestData.FOLDER_ID + "/view")]
    [InlineData("https://example.com/drive/folders/" + GoogleDriveTestData.FOLDER_ID)]
    [InlineData("http://drive.google.com/drive/folders/" + GoogleDriveTestData.FOLDER_ID)]
    [InlineData("https://drive.google.com/drive/folders/")]
    [InlineData("folder id with spaces")]
    [InlineData("1AbC/../etc")]
    [InlineData("hello")]
    [InlineData("1AbCdEfGhIjKl")]
    public async Task NotAFolderLinkIsRefused(string folderLink)
    {
        // C6
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, GoogleDriveTestData.FOLDER_ID);

        using var response = await SaveFolderAsync(folderLink);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
        (await response.ReadJsonAsync()).Text(ApiFields.DETAIL).Should().Be(NOT_A_FOLDER_LINK);
        ReadRows()[SettingCodes.GOOGLE_DRIVE_FOLDER_ID].Should().Be(GoogleDriveTestData.FOLDER_ID);
    }

    [Fact]
    public async Task MissingFolderLinkIsRefused()
    {
        // C6
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, null);

        await api.Client.PostApiAsync(ApiRoutes.UPDATE_GOOGLE_DRIVE_FOLDER, new { }).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
        ReadRows().Should().NotContainKey(SettingCodes.GOOGLE_DRIVE_FOLDER_ID);
    }

    [Fact]
    public async Task NotConnectedIsAConflict()
    {
        // C7
        await SaveFolderAsync(GoogleDriveTestData.FOLDER_ID).ShouldBeProblemAsync(HttpStatusCode.Conflict);

        ReadRows().Should().BeEmpty();
    }

    [Fact]
    public async Task OtherFolderUpdatesTheRowInPlace()
    {
        // C8
        AddRows(GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.EMAIL, GoogleDriveTestData.FOLDER_ID);
        var idBefore = ReadFolderRowId();

        using var response = await SaveFolderAsync(OTHER_FOLDER_ID);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        ReadFolderRowId().Should().Be(idBefore);
        ReadRows()[SettingCodes.GOOGLE_DRIVE_FOLDER_ID].Should().Be(OTHER_FOLDER_ID);
    }

    public void Dispose() => api.Dispose();

    // A null value leaves its row out.
    private void AddRows(string refreshToken, string? email, string? folderId) =>
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN, Value = refreshToken });
            if (email is not null)
            {
                context.Settings.Add(new Setting { Code = SettingCodes.GOOGLE_DRIVE_EMAIL, Value = email });
            }

            if (folderId is not null)
            {
                context.Settings.Add(new Setting { Code = SettingCodes.GOOGLE_DRIVE_FOLDER_ID, Value = folderId });
            }

            context.SaveChanges();
        });

    private Task<HttpResponseMessage> SaveFolderAsync(string folderLink) =>
        api.Client.PostApiAsync(ApiRoutes.UPDATE_GOOGLE_DRIVE_FOLDER, new { folderLink });

    private async Task<JsonElement> GetConnectionAsync()
    {
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_GOOGLE_DRIVE_CONNECTION);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return await response.ReadJsonAsync();
    }

    private Guid ReadFolderRowId() =>
        api.Read(context => context.Settings.AsNoTracking().Single(setting => setting.Code == SettingCodes.GOOGLE_DRIVE_FOLDER_ID).Id);

    private Dictionary<string, string> ReadRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));
}
