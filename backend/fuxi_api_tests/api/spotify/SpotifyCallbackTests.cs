using System.Globalization;
using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Spotify;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Spotify;

/// <summary>Phase 6e sections A3 and B (test_scenarios_2026_11_18_18_30): GET /api/SpotifyCallback.</summary>
[Collection(nameof(SmokeTests))]
public sealed class SpotifyCallbackTests : IDisposable
{
    private const string OTHER_REFRESH_TOKEN = "AQD-other-refresh-token";
    private const string OTHER_USER_ID = "other-user-id";
    private const string TOKEN_ADDRESS = "https://accounts.spotify.com/api/token";
    private const string ME_ADDRESS = "https://api.spotify.com/v1/me";

    private const string FAILING_FUNCTION_SQL = """
        CREATE OR REPLACE FUNCTION fail_statement() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Failure injected by a test';
        END;
        $$ LANGUAGE plpgsql
        """;
    private const string FAIL_NAME_INSERT_SQL =
        "CREATE TRIGGER fail_name_insert BEFORE INSERT ON \"Settings\" FOR EACH ROW " +
        "WHEN (NEW.\"Code\" = '" + SettingCodes.SPOTIFY_NAME + "') EXECUTE FUNCTION fail_statement()";

    private readonly DatabaseApi api = new();

    public SpotifyCallbackTests() => SpotifyTestData.Configure(api.Settings);

    [Fact]
    public async Task CodeIsSentToSpotifyTokenEndpointWithBasicHeader()
    {
        // B1
        await SignInAsync();

        var request = api.Spotify.Requests[0];
        request.Method.Should().Be(HttpMethod.Post);
        request.Address.Should().Be(new Uri(TOKEN_ADDRESS));
        var form = QueryHelpers.ParseQuery(request.Body);
        form["grant_type"].ToString().Should().Be("authorization_code");
        form["code"].ToString().Should().Be(SpotifyTestData.CODE);
        form["redirect_uri"].ToString().Should().Be(SpotifyTestData.REDIRECT_URI);
        request.Authorization!.Scheme.Should().Be("Basic");
        var credentials = System.Text.Encoding.UTF8.GetString(Convert.FromBase64String(request.Authorization.Parameter!));
        credentials.Should().Be($"{SpotifyTestData.CLIENT_ID}:{SpotifyTestData.CLIENT_SECRET}");
    }

    [Fact]
    public async Task UserIsReadWithTheAccessTokenFromMe()
    {
        // B2
        await SignInAsync();

        api.Spotify.Requests.Should().HaveCount(2);
        var me = api.Spotify.Requests[1];
        me.Method.Should().Be(HttpMethod.Get);
        me.Address.Should().Be(new Uri(ME_ADDRESS));
        me.Authorization!.Scheme.Should().Be("Bearer");
        me.Authorization.Parameter.Should().Be(SpotifyTestData.ACCESS_TOKEN);
    }

    [Fact]
    public async Task SuccessfulSignInSavesTheRowsAndRedirectsConnected()
    {
        // B3
        using var response = await SignInAsync();

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.CONNECTED_ADDRESS));
        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.SPOTIFY_REFRESH_TOKEN] = SpotifyTestData.REFRESH_TOKEN,
            [SettingCodes.SPOTIFY_USER_ID] = SpotifyTestData.USER_ID,
            [SettingCodes.SPOTIFY_NAME] = SpotifyTestData.DISPLAY_NAME,
        });
    }

    [Fact]
    public async Task MissingDisplayNameSavesTheUserIdAsTheName()
    {
        // B4
        api.Spotify.AnswerMeWith(HttpStatusCode.OK, SpotifyTestData.MeAnswer(SpotifyTestData.USER_ID, null));

        await SignInAsync();

        ReadRows()[SettingCodes.SPOTIFY_NAME].Should().Be(SpotifyTestData.USER_ID);
    }

    [Fact]
    public async Task SameUserUpdatesRowsInPlaceAndKeepsPlaylist()
    {
        // B5
        await SignInAsync();
        AddPlaylist();
        var idsBefore = ReadIds();
        api.Spotify.AnswerTokenWith(HttpStatusCode.OK, SpotifyTestData.TokenAnswer(SpotifyTestData.ACCESS_TOKEN, OTHER_REFRESH_TOKEN, SpotifyTestData.SCOPES));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.CONNECTED_ADDRESS));
        ReadIds().Should().Equal(idsBefore);
        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.SPOTIFY_REFRESH_TOKEN] = OTHER_REFRESH_TOKEN,
            [SettingCodes.SPOTIFY_USER_ID] = SpotifyTestData.USER_ID,
            [SettingCodes.SPOTIFY_NAME] = SpotifyTestData.DISPLAY_NAME,
            [SettingCodes.SPOTIFY_PLAYLIST_ID] = SpotifyTestData.PLAYLIST_ID,
        });
    }

    [Fact]
    public async Task OtherUserClearsTheSavedPlaylist()
    {
        // B6
        await SignInAsync();
        AddPlaylist();
        api.Spotify.AnswerMeWith(HttpStatusCode.OK, SpotifyTestData.MeAnswer(OTHER_USER_ID, "Other"));

        await SignInAsync();

        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.SPOTIFY_REFRESH_TOKEN] = SpotifyTestData.REFRESH_TOKEN,
            [SettingCodes.SPOTIFY_USER_ID] = OTHER_USER_ID,
            [SettingCodes.SPOTIFY_NAME] = "Other",
            [SettingCodes.SPOTIFY_PLAYLIST_ID] = string.Empty,
        });
    }

    [Fact]
    public async Task StateIsAcceptedJustBeforeTenMinutes()
    {
        // A3
        var state = await SpotifyConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10) - TimeSpan.FromSeconds(1));

        using var response = await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.CONNECTED_ADDRESS));
    }

    [Fact]
    public async Task StateIsRefusedAfterTenMinutes()
    {
        // A3, B7
        var state = await SpotifyConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10));

        using var response = await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Theory]
    [InlineData("state-this-api-never-made")]
    [InlineData("")]
    [InlineData(null)]
    public async Task UnknownOrMissingStateIsRefused(string? state)
    {
        // B7
        await SpotifyConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Fact]
    public async Task UsedStateIsRefusedTheSecondTime()
    {
        // B7
        var state = await SpotifyConnectTests.ConnectStateAsync(api.Client);
        await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state)).ShouldHaveStatusAsync(HttpStatusCode.Redirect);
        var rowsBefore = ReadRows();

        using var response = await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        api.Spotify.Requests.Should().HaveCount(2);
        ReadRows().Should().BeEquivalentTo(rowsBefore);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(SpotifyTestData.CODE)] // an error wins even when a code came with it
    public async Task CancelledOnSpotifyIsRefused(string? code)
    {
        // B8
        var state = await SpotifyConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("error", "access_denied"), ("code", code), ("state", state));

        ShouldBeRefused(response);
    }

    [Theory]
    [InlineData(HttpStatusCode.BadRequest, """{"error":"invalid_grant"}""")]
    [InlineData(HttpStatusCode.InternalServerError, "{}")]
    public async Task TokenErrorStatusSavesNothingAndIsLoggedWithStatus(HttpStatusCode status, string answer)
    {
        // B9, B11
        api.Spotify.AnswerTokenWith(status, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response).Message.Should().Contain(((int)status).ToString(CultureInfo.InvariantCulture));
    }

    [Theory]
    [InlineData(null, SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.SCOPES)]
    [InlineData("", SpotifyTestData.REFRESH_TOKEN, SpotifyTestData.SCOPES)]
    [InlineData(SpotifyTestData.ACCESS_TOKEN, null, SpotifyTestData.SCOPES)]
    [InlineData(SpotifyTestData.ACCESS_TOKEN, "", SpotifyTestData.SCOPES)]
    [InlineData(SpotifyTestData.ACCESS_TOKEN, SpotifyTestData.REFRESH_TOKEN, null)]
    [InlineData(SpotifyTestData.ACCESS_TOKEN, SpotifyTestData.REFRESH_TOKEN, "playlist-read-private")]
    [InlineData(SpotifyTestData.ACCESS_TOKEN, SpotifyTestData.REFRESH_TOKEN, "playlist-read-collaborative")]
    public async Task IncompleteTokenAnswerSavesNothingAndIsLogged(string? accessToken, string? refreshToken, string? scope)
    {
        // B9: a missing token, or the Learner unticked a playlist scope on the consent screen
        api.Spotify.AnswerTokenWith(HttpStatusCode.OK, SpotifyTestData.TokenAnswer(accessToken, refreshToken, scope));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task ScopeAmongOtherScopesIsAccepted()
    {
        // B9: Spotify lists every granted scope, joined with spaces
        api.Spotify.AnswerTokenWith(HttpStatusCode.OK, SpotifyTestData.TokenAnswer(
            SpotifyTestData.ACCESS_TOKEN, SpotifyTestData.REFRESH_TOKEN, "user-read-private " + SpotifyTestData.SCOPES));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.CONNECTED_ADDRESS));
    }

    [Theory]
    [InlineData(HttpStatusCode.Unauthorized, "{}")]
    [InlineData(HttpStatusCode.OK, "{}")]
    [InlineData(HttpStatusCode.OK, "<html>Bad gateway</html>")]
    public async Task FailedMeCallSavesNothingAndIsLogged(HttpStatusCode status, string answer)
    {
        // B10, B11
        api.Spotify.AnswerMeWith(status, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task MeTimeoutSavesNothingAndIsLogged()
    {
        // B10: HttpClient reports its own timeout as a cancelled task
        api.Spotify.FailMeWith(new TaskCanceledException("The request timed out.", new TimeoutException()));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task UnreachableSpotifySavesNothingAndIsLogged()
    {
        // B9, B11
        api.Spotify.FailTokenWith(new HttpRequestException("No connection could be made."));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task RowsAreWrittenAllOrNone()
    {
        // B3: the name insert fails in the database
        api.Arrange(context =>
        {
            context.Database.ExecuteSqlRaw(FAILING_FUNCTION_SQL);
            context.Database.ExecuteSqlRaw(FAIL_NAME_INSERT_SQL);
        });

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        ReadRows().Should().BeEmpty();
    }

    public void Dispose() => api.Dispose();

    // A refused callback never reaches Spotify and changes no Settings row.
    private void ShouldBeRefused(HttpResponseMessage response)
    {
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        api.Spotify.Requests.Should().BeEmpty();
        ReadRows().Should().BeEmpty();
    }

    // A failed sign-in saves nothing and logs one error that holds no code, token or secret.
    private LogEntry ShouldFailWithOneErrorLog(HttpResponseMessage response)
    {
        response.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        ReadRows().Should().BeEmpty();
        var entry = api.Logs.Of(typeof(SpotifyService).FullName!).Should().ContainSingle().Subject;
        entry.Level.Should().Be(LogLevel.Error);
        var logged = entry.Message + entry.Exception;
        logged.Should().NotContain(SpotifyTestData.CODE)
            .And.NotContain(SpotifyTestData.CLIENT_SECRET)
            .And.NotContain(SpotifyTestData.ACCESS_TOKEN)
            .And.NotContain(SpotifyTestData.REFRESH_TOKEN);

        return entry;
    }

    private void AddPlaylist() =>
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.SPOTIFY_PLAYLIST_ID, Value = SpotifyTestData.PLAYLIST_ID });
            context.SaveChanges();
        });

    // Starts a sign-in and comes back from Spotify with a code, the way the Learner's browser does.
    private async Task<HttpResponseMessage> SignInAsync()
    {
        var state = await SpotifyConnectTests.ConnectStateAsync(api.Client);

        return await CallbackAsync(("code", SpotifyTestData.CODE), ("state", state));
    }

    private Dictionary<string, Guid> ReadIds() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Id));

    private Dictionary<string, string> ReadRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));

    private Task<HttpResponseMessage> CallbackAsync(params (string Name, string? Value)[] query) =>
        api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CALLBACK, query);
}
