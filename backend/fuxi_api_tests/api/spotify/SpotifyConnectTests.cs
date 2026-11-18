using System.Net;
using FluentAssertions;
using FuXi.Api.Spotify;
using FuXi.Api.Tests.Api.GoogleDrive;
using FuXi.Api.Tests.Api.Notion;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Spotify;

/// <summary>Phase 6e section A (test_scenarios_2026_11_18_18_30): GET /api/SpotifyConnect.</summary>
[Collection(nameof(SmokeTests))]
public sealed class SpotifyConnectTests
{
    private const string AUTHORIZE_ADDRESS = "https://accounts.spotify.com/authorize";

    [Fact]
    public async Task ConnectRedirectsToSpotifyWithPlaylistScopesAndState()
    {
        // A1
        using var api = new NowApi(SpotifyTestData.ConfiguredSettings());

        using var response = await api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CONNECT);

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        var location = response.Headers.Location!;
        location.GetLeftPart(UriPartial.Path).Should().Be(AUTHORIZE_ADDRESS);
        var query = QueryHelpers.ParseQuery(location.Query);
        query["client_id"].ToString().Should().Be(SpotifyTestData.CLIENT_ID);
        query["response_type"].ToString().Should().Be("code");
        query["redirect_uri"].ToString().Should().Be(SpotifyTestData.REDIRECT_URI);
        query["scope"].ToString().Should().Be(SpotifyTestData.SCOPES);
        query["show_dialog"].ToString().Should().Be("true");
        query["state"].ToString().Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public async Task EachConnectHasItsOwnState()
    {
        // A2
        using var api = new NowApi(SpotifyTestData.ConfiguredSettings());

        var first = await ConnectStateAsync(api.Client);
        var second = await ConnectStateAsync(api.Client);

        first.Should().NotBe(second);
    }

    [Fact]
    public async Task OtherSourceStatesAreRefusedBySpotifyAndTheOtherWayRound()
    {
        // A4
        using var api = new NowApi(AllSourcesConfigured());
        var notionState = await NotionConnectTests.ConnectStateAsync(api.Client);
        var googleState = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);
        var spotifyState = await ConnectStateAsync(api.Client);

        using var fromNotion = await api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CALLBACK, ("code", SpotifyTestData.CODE), ("state", notionState));
        using var fromGoogle = await api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CALLBACK, ("code", SpotifyTestData.CODE), ("state", googleState));
        using var toNotion = await api.Client.GetApiAsync(ApiRoutes.NOTION_CALLBACK, ("code", NotionTestData.CODE), ("state", spotifyState));
        using var toGoogle = await api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CALLBACK, ("code", GoogleDriveTestData.CODE), ("state", spotifyState));

        fromNotion.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        fromGoogle.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        toNotion.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        toGoogle.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        api.Host.Spotify.Requests.Should().BeEmpty();
    }

    [Theory]
    [InlineData(SpotifySettings.CLIENT_ID_KEY)]
    [InlineData(SpotifySettings.CLIENT_SECRET_KEY)]
    [InlineData(SpotifySettings.REDIRECT_URI_KEY)]
    public async Task MissingKeyIsLoggedAndConnectFails(string key)
    {
        // A5
        using var api = new NowApi(SpotifyTestData.SettingsWithout(key));

        using var connect = await api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CONNECT);
        using var callback = await api.Client.GetApiAsync(ApiRoutes.SPOTIFY_CALLBACK, ("code", SpotifyTestData.CODE), ("state", "any"));

        connect.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        callback.Headers.Location.Should().Be(new Uri(SpotifyTestData.FAILED_ADDRESS));
        api.Host.Spotify.Requests.Should().BeEmpty();
        var entry = api.Host.Logs.Of(typeof(SpotifySettings).FullName!).Should().ContainSingle().Subject;
        entry.Level.Should().Be(LogLevel.Error);
        entry.Message.Should().Contain(key).And.Contain(SpotifySettings.SOURCE_NAME);
    }

    [Fact]
    public async Task MissingSpotifyKeysLeaveNotionAndGoogleDriveWorking()
    {
        // A5
        using var api = new NowApi(NotionTestData.ConfiguredSettings() with
        {
            GoogleClientId = GoogleDriveTestData.CLIENT_ID,
            GoogleClientSecret = GoogleDriveTestData.CLIENT_SECRET,
            GoogleRedirectUri = GoogleDriveTestData.REDIRECT_URI,
        });

        using var notion = await api.Client.GetApiAsync(ApiRoutes.NOTION_CONNECT);
        using var google = await api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CONNECT);

        notion.Headers.Location!.Host.Should().Be("api.notion.com");
        google.Headers.Location!.Host.Should().Be("accounts.google.com");
    }

    /// <summary>Calls /api/SpotifyConnect and returns the state value of its redirect.</summary>
    public static async Task<string> ConnectStateAsync(HttpClient client)
    {
        using var response = await client.GetApiAsync(ApiRoutes.SPOTIFY_CONNECT);
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);

        return QueryHelpers.ParseQuery(response.Headers.Location!.Query)["state"].ToString();
    }

    private static NowApiSettings AllSourcesConfigured() => SpotifyTestData.ConfiguredSettings() with
    {
        NotionClientId = NotionTestData.CLIENT_ID,
        NotionClientSecret = NotionTestData.CLIENT_SECRET,
        NotionRedirectUri = NotionTestData.REDIRECT_URI,
        GoogleClientId = GoogleDriveTestData.CLIENT_ID,
        GoogleClientSecret = GoogleDriveTestData.CLIENT_SECRET,
        GoogleRedirectUri = GoogleDriveTestData.REDIRECT_URI,
    };
}
