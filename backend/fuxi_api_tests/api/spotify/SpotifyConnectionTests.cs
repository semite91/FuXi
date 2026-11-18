using System.Net;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Spotify;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api.Spotify;

/// <summary>
/// Phase 6e section C (test_scenarios_2026_11_18_18_30): GET /api/GetSpotifyConnection and
/// POST /api/UpdateSpotifyPlaylist.
/// </summary>
[Collection(nameof(SmokeTests))]
public sealed class SpotifyConnectionTests : IDisposable
{
    private const string NOT_A_PLAYLIST_LINK = "This is not a Spotify playlist link.";
    private const string OTHER_PLAYLIST_ID = "0vvXsWCC9xrXsKd4FyS8kM";
    private const string PLAYLIST_LINK = "https://open.spotify.com/playlist/" + SpotifyTestData.PLAYLIST_ID;

    private readonly DatabaseApi api = new();

    public SpotifyConnectionTests() => SpotifyTestData.Configure(api.Settings);

    [Fact]
    public async Task NoRefreshTokenIsNotConnected()
    {
        // C1
        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.NAME).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.PLAYLIST_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task EmptyRefreshTokenIsNotConnected()
    {
        // C1
        AddRows(string.Empty, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.NAME).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.PLAYLIST_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task ConnectedAnswersNameAndPlaylist()
    {
        // C2
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.Text(ApiFields.NAME).Should().Be(SpotifyTestData.DISPLAY_NAME);
        answer.Text(ApiFields.PLAYLIST_ID).Should().Be(SpotifyTestData.PLAYLIST_ID);
    }

    [Fact]
    public async Task EmptyNameAndPlaylistAnswerNull()
    {
        // C2
        AddRows(SpotifyTestData.REFRESH_TOKEN, string.Empty, string.Empty);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.GetProperty(ApiFields.NAME).ValueKind.Should().Be(JsonValueKind.Null);
        answer.GetProperty(ApiFields.PLAYLIST_ID).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task AnswerHoldsNoRefreshTokenAndNoUserId()
    {
        // C3
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.SPOTIFY_USER_ID, Value = SpotifyTestData.USER_ID });
            context.SaveChanges();
        });

        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_SPOTIFY_CONNECTION);

        (await response.ReadTextAsync()).Should().NotContain(SpotifyTestData.REFRESH_TOKEN).And.NotContain(SpotifyTestData.USER_ID);
        (await response.ReadJsonAsync()).FieldNames().Should().BeEquivalentTo(ApiFields.IS_CONNECTED, ApiFields.NAME, ApiFields.PLAYLIST_ID);
    }

    [Theory]
    [InlineData(PLAYLIST_LINK)]
    [InlineData(PLAYLIST_LINK + "?si=0123456789abcdef")]
    [InlineData("https://open.spotify.com/intl-tr/playlist/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("  " + PLAYLIST_LINK + "  ")]
    [InlineData("http://open.spotify.com/playlist/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("https://open.spotify.com/user/learner.name/playlist/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("spotify:playlist:" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("spotify:user:learner.name:playlist:" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData(SpotifyTestData.PLAYLIST_ID)]
    public async Task PlaylistLinkOrIdIsSavedAsThePlaylistId(string playlistLink)
    {
        // C4, C5
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);

        using var response = await SavePlaylistAsync(playlistLink);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadJsonAsync()).Text(ApiFields.PLAYLIST_ID).Should().Be(SpotifyTestData.PLAYLIST_ID);
        ReadRows()[SettingCodes.SPOTIFY_PLAYLIST_ID].Should().Be(SpotifyTestData.PLAYLIST_ID);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("https://open.spotify.com/album/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("https://open.spotify.com/track/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("https://open.spotify.com/artist/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("https://example.com/playlist/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("https://open.spotify.com/playlist/")]
    [InlineData("https://open.spotify.com/user/learner.name/album/" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("spotify:user:learner.name:album:" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("spotify:album:" + SpotifyTestData.PLAYLIST_ID)]
    [InlineData("playlist id with spaces")]
    [InlineData("37i9dQZF1DXcBWIGoYBM5!")]
    [InlineData("hello")]
    public async Task NotAPlaylistLinkIsRefused(string playlistLink)
    {
        // C6
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);

        using var response = await SavePlaylistAsync(playlistLink);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
        (await response.ReadJsonAsync()).Text(ApiFields.DETAIL).Should().Be(NOT_A_PLAYLIST_LINK);
        ReadRows()[SettingCodes.SPOTIFY_PLAYLIST_ID].Should().Be(SpotifyTestData.PLAYLIST_ID);
    }

    [Fact]
    public async Task MissingPlaylistLinkIsRefused()
    {
        // C6
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);

        await api.Client.PostApiAsync(ApiRoutes.UPDATE_SPOTIFY_PLAYLIST, new { }).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
        ReadRows().Should().NotContainKey(SettingCodes.SPOTIFY_PLAYLIST_ID);
    }

    [Fact]
    public async Task NotConnectedIsAConflict()
    {
        // C7
        await SavePlaylistAsync(PLAYLIST_LINK).ShouldBeProblemAsync(HttpStatusCode.Conflict);

        ReadRows().Should().BeEmpty();
    }

    [Fact]
    public async Task OtherPlaylistUpdatesTheRowInPlace()
    {
        // C8
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);
        var idBefore = ReadPlaylistRowId();

        using var response = await SavePlaylistAsync(OTHER_PLAYLIST_ID);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        ReadPlaylistRowId().Should().Be(idBefore);
        ReadRows()[SettingCodes.SPOTIFY_PLAYLIST_ID].Should().Be(OTHER_PLAYLIST_ID);
    }

    [Fact]
    public async Task SavingRefreshesTheTokenAndChecksThePlaylistWithItsAccessToken()
    {
        // C9
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);

        using var response = await SavePlaylistAsync(PLAYLIST_LINK);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        var requests = api.Spotify.Requests;
        requests.Should().HaveCount(2);
        requests[0].Address.Host.Should().Be(SpotifyTestData.TOKEN_HOST);
        requests[0].Body.Should().Contain("grant_type=refresh_token").And.Contain("refresh_token=" + SpotifyTestData.REFRESH_TOKEN);
        requests[0].Authorization!.Scheme.Should().Be("Basic");
        requests[1].Address.AbsolutePath.Should().Be("/v1/playlists/" + SpotifyTestData.PLAYLIST_ID + "/items");
        requests[1].Authorization!.Parameter.Should().Be(SpotifyTestData.ACCESS_TOKEN);
    }

    [Theory]
    [InlineData(HttpStatusCode.Forbidden)]
    [InlineData(HttpStatusCode.NotFound)]
    [InlineData(HttpStatusCode.Unauthorized)]
    public async Task PlaylistTheAccountCannotReadIsRefusedAndNotSaved(HttpStatusCode status)
    {
        // C10
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, SpotifyTestData.PLAYLIST_ID);
        api.Spotify.AnswerPlaylistWith(status, "{}");

        using var response = await SavePlaylistAsync(OTHER_PLAYLIST_ID);

        response.StatusCode.Should().Be(HttpStatusCode.UnprocessableEntity);
        (await response.ReadJsonAsync()).Text(ApiFields.DETAIL).Should().Contain("Choose one you own or collaborate on");
        ReadRows()[SettingCodes.SPOTIFY_PLAYLIST_ID].Should().Be(SpotifyTestData.PLAYLIST_ID);
    }

    [Theory]
    [InlineData(HttpStatusCode.BadRequest)]
    [InlineData(HttpStatusCode.Unauthorized)]
    public async Task EndedSignInIsAConflictAndNotSaved(HttpStatusCode status)
    {
        // C11
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);
        api.Spotify.AnswerTokenWith(status, "{\"error\":\"invalid_grant\"}");

        using var response = await SavePlaylistAsync(PLAYLIST_LINK);

        response.StatusCode.Should().Be(HttpStatusCode.Conflict);
        (await response.ReadJsonAsync()).Text(ApiFields.DETAIL).Should().Contain("Connect Spotify again");
        ReadRows().Should().NotContainKey(SettingCodes.SPOTIFY_PLAYLIST_ID);
        api.Spotify.Requests.Should().HaveCount(1);
    }

    [Theory]
    [InlineData(HttpStatusCode.InternalServerError, true)]
    [InlineData(HttpStatusCode.TooManyRequests, true)]
    [InlineData(HttpStatusCode.InternalServerError, false)]
    public async Task SpotifyFailingWhileCheckingIsABadGatewayAndNotSaved(HttpStatusCode status, bool onToken)
    {
        // C12
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);
        if (onToken)
        {
            api.Spotify.AnswerTokenWith(status, "{}");
        }
        else
        {
            api.Spotify.AnswerPlaylistWith(status, "{}");
        }

        using var response = await SavePlaylistAsync(PLAYLIST_LINK);

        response.StatusCode.Should().Be(HttpStatusCode.BadGateway);
        ReadRows().Should().NotContainKey(SettingCodes.SPOTIFY_PLAYLIST_ID);
    }

    [Fact]
    public async Task SpotifyNotReachableWhileCheckingIsABadGatewayWithoutTokensInTheAnswer()
    {
        // C12
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);
        api.Spotify.FailPlaylistWith(new HttpRequestException("connection refused"));

        using var response = await SavePlaylistAsync(PLAYLIST_LINK);

        response.StatusCode.Should().Be(HttpStatusCode.BadGateway);
        (await response.ReadTextAsync()).Should().NotContain(SpotifyTestData.REFRESH_TOKEN).And.NotContain(SpotifyTestData.ACCESS_TOKEN);
        ReadRows().Should().NotContainKey(SettingCodes.SPOTIFY_PLAYLIST_ID);
    }

    [Fact]
    public async Task EmptySpotifyKeysAreAConflictAndNotSaved()
    {
        // C13
        AddRows(SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.DISPLAY_NAME, null);
        api.Settings[SpotifySettings.CLIENT_ID_KEY] = string.Empty;

        await SavePlaylistAsync(PLAYLIST_LINK).ShouldBeProblemAsync(HttpStatusCode.Conflict);

        ReadRows().Should().NotContainKey(SettingCodes.SPOTIFY_PLAYLIST_ID);
        api.Spotify.Requests.Should().BeEmpty();
    }

    public void Dispose() => api.Dispose();

    // A null value leaves its row out.
    private void AddRows(string refreshToken, string? name, string? playlistId) =>
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.SPOTIFY_REFRESH_TOKEN, Value = refreshToken });
            if (name is not null)
            {
                context.Settings.Add(new Setting { Code = SettingCodes.SPOTIFY_NAME, Value = name });
            }

            if (playlistId is not null)
            {
                context.Settings.Add(new Setting { Code = SettingCodes.SPOTIFY_PLAYLIST_ID, Value = playlistId });
            }

            context.SaveChanges();
        });

    private Task<HttpResponseMessage> SavePlaylistAsync(string playlistLink) =>
        api.Client.PostApiAsync(ApiRoutes.UPDATE_SPOTIFY_PLAYLIST, new { playlistLink });

    private async Task<JsonElement> GetConnectionAsync()
    {
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_SPOTIFY_CONNECTION);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return await response.ReadJsonAsync();
    }

    private Guid ReadPlaylistRowId() =>
        api.Read(context => context.Settings.AsNoTracking().Single(setting => setting.Code == SettingCodes.SPOTIFY_PLAYLIST_ID).Id);

    private Dictionary<string, string> ReadRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));
}
