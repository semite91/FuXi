using System.Net;
using FluentAssertions;
using FuXi.Api.GoogleDrive;
using FuXi.Api.Tests.Api.Notion;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.GoogleDrive;

/// <summary>Phase 6c section A (test_scenarios_2026_11_17_19_42): GET /api/GoogleDriveConnect.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GoogleDriveConnectTests
{
    private const string AUTHORIZE_ADDRESS = "https://accounts.google.com/o/oauth2/v2/auth";

    [Fact]
    public async Task ConnectRedirectsToGoogleWithDriveReadOnlyOfflineAccessAndState()
    {
        // A1
        using var api = new NowApi(GoogleDriveTestData.ConfiguredSettings());

        using var response = await api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CONNECT);

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        var location = response.Headers.Location!;
        location.GetLeftPart(UriPartial.Path).Should().Be(AUTHORIZE_ADDRESS);
        var query = QueryHelpers.ParseQuery(location.Query);
        query["client_id"].ToString().Should().Be(GoogleDriveTestData.CLIENT_ID);
        query["response_type"].ToString().Should().Be("code");
        query["redirect_uri"].ToString().Should().Be(GoogleDriveTestData.REDIRECT_URI);
        query["scope"].ToString().Should().Be(GoogleDriveTestData.DRIVE_SCOPE);
        query["access_type"].ToString().Should().Be("offline");
        query["prompt"].ToString().Should().Be("consent");
        query["state"].ToString().Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public async Task EachConnectHasItsOwnState()
    {
        // A2
        using var api = new NowApi(GoogleDriveTestData.ConfiguredSettings());

        var first = await ConnectStateAsync(api.Client);
        var second = await ConnectStateAsync(api.Client);

        first.Should().NotBe(second);
    }

    [Fact]
    public async Task NotionStateIsRefusedByTheGoogleDriveCallback()
    {
        // A4
        using var api = new NowApi(BothSourcesConfigured());
        var notionState = await NotionConnectTests.ConnectStateAsync(api.Client);

        using var response = await api.Client.GetApiAsync(
            ApiRoutes.GOOGLE_DRIVE_CALLBACK, ("code", GoogleDriveTestData.CODE), ("state", notionState));

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        api.Host.Google.Requests.Should().BeEmpty();
    }

    [Fact]
    public async Task GoogleDriveStateIsRefusedByTheNotionCallback()
    {
        // A4
        using var api = new NowApi(BothSourcesConfigured());
        var googleState = await ConnectStateAsync(api.Client);

        using var response = await api.Client.GetApiAsync(
            ApiRoutes.NOTION_CALLBACK, ("code", NotionTestData.CODE), ("state", googleState));

        response.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        api.Host.Notion.Requests.Should().BeEmpty();
    }

    [Theory]
    [InlineData(GoogleDriveSettings.CLIENT_ID_KEY)]
    [InlineData(GoogleDriveSettings.CLIENT_SECRET_KEY)]
    [InlineData(GoogleDriveSettings.REDIRECT_URI_KEY)]
    public async Task MissingKeyIsLoggedAndConnectFails(string key)
    {
        // A5
        using var api = new NowApi(GoogleDriveTestData.SettingsWithout(key));

        using var connect = await api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CONNECT);
        using var callback = await api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CALLBACK, ("code", GoogleDriveTestData.CODE), ("state", "any"));

        connect.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        callback.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        api.Host.Google.Requests.Should().BeEmpty();
        var entry = api.Host.Logs.Of(typeof(GoogleDriveSettings).FullName!).Should().ContainSingle().Subject;
        entry.Level.Should().Be(LogLevel.Error);
        entry.Message.Should().Contain(key).And.Contain(GoogleDriveSettings.SOURCE_NAME);
    }

    [Fact]
    public void ConfiguredKeysLogNothing()
    {
        // A5
        using var api = new NowApi(GoogleDriveTestData.ConfiguredSettings());

        _ = api.Services;

        api.Host.Logs.Of(typeof(GoogleDriveSettings).FullName!).Should().BeEmpty();
    }

    [Fact]
    public async Task MissingGoogleKeysLeaveNotionWorking()
    {
        // A5
        using var api = new NowApi(NotionTestData.ConfiguredSettings());

        using var response = await api.Client.GetApiAsync(ApiRoutes.NOTION_CONNECT);

        response.Headers.Location!.Host.Should().Be("api.notion.com");
    }

    /// <summary>Calls /api/GoogleDriveConnect and returns the state value of its redirect.</summary>
    public static async Task<string> ConnectStateAsync(HttpClient client)
    {
        using var response = await client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CONNECT);
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);

        return QueryHelpers.ParseQuery(response.Headers.Location!.Query)["state"].ToString();
    }

    private static NowApiSettings BothSourcesConfigured() => GoogleDriveTestData.ConfiguredSettings() with
    {
        NotionClientId = NotionTestData.CLIENT_ID,
        NotionClientSecret = NotionTestData.CLIENT_SECRET,
        NotionRedirectUri = NotionTestData.REDIRECT_URI,
    };
}
