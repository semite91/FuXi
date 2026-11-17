using System.Net;
using FluentAssertions;
using FuXi.Api.Notion;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Notion;

/// <summary>Phase 6b section A (test_scenarios_2026_11_17_11_48): GET /api/NotionConnect.</summary>
[Collection(nameof(SmokeTests))]
public sealed class NotionConnectTests
{
    private const string AUTHORIZE_ADDRESS = "https://api.notion.com/v1/oauth/authorize";

    [Fact]
    public async Task ConnectRedirectsToNotionAuthorizeWithClientAndState()
    {
        // A1
        using var api = new NowApi(NotionTestData.ConfiguredSettings());

        using var response = await api.Client.GetApiAsync(ApiRoutes.NOTION_CONNECT);

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        var location = response.Headers.Location!;
        location.GetLeftPart(UriPartial.Path).Should().Be(AUTHORIZE_ADDRESS);
        var query = QueryHelpers.ParseQuery(location.Query);
        query["client_id"].ToString().Should().Be(NotionTestData.CLIENT_ID);
        query["response_type"].ToString().Should().Be("code");
        query["owner"].ToString().Should().Be("user");
        query["redirect_uri"].ToString().Should().Be(NotionTestData.REDIRECT_URI);
        query["state"].ToString().Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public async Task EachConnectHasItsOwnState()
    {
        // A2
        using var api = new NowApi(NotionTestData.ConfiguredSettings());

        var first = await ConnectStateAsync(api.Client);
        var second = await ConnectStateAsync(api.Client);

        first.Should().NotBe(second);
    }

    [Fact]
    public void ConfiguredKeysLogNothing()
    {
        // A4
        using var api = new NowApi(NotionTestData.ConfiguredSettings());

        _ = api.Services;

        api.Host.Logs.Of(typeof(NotionSettings).FullName!).Should().BeEmpty();
    }

    [Fact]
    public async Task AppUrlWithClosingSlashGivesOneSlashBeforeSettings()
    {
        // A4, B4
        using var api = new NowApi(NotionTestData.ConfiguredSettings() with { AppUrl = NotionTestData.APP_URL + "/" });

        using var callback = await api.Client.GetApiAsync(ApiRoutes.NOTION_CALLBACK, ("state", "unknown"));

        callback.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
    }

    [Theory]
    [InlineData(NotionSettings.CLIENT_ID_KEY)]
    [InlineData(NotionSettings.CLIENT_SECRET_KEY)]
    [InlineData(NotionSettings.REDIRECT_URI_KEY)]
    [InlineData(NotionSettings.APP_URL_KEY)]
    public void MissingKeyIsLoggedAndApiStillStarts(string key)
    {
        // A4
        using var api = new NowApi(NotionTestData.SettingsWithout(key));

        var start = () => api.Services;

        start.Should().NotThrow();
        api.Host.Logs.Of(typeof(NotionSettings).FullName!).Should().ContainSingle()
            .Which.Should().Match<LogEntry>(entry => entry.Level == LogLevel.Error && entry.Message.Contains(key));
    }

    [Theory]
    [InlineData(NotionSettings.CLIENT_ID_KEY)]
    [InlineData(NotionSettings.CLIENT_SECRET_KEY)]
    [InlineData(NotionSettings.REDIRECT_URI_KEY)]
    public async Task MissingClientKeyMakesConnectAndCallbackFail(string key)
    {
        // A4
        using var api = new NowApi(NotionTestData.SettingsWithout(key));

        using var connect = await api.Client.GetApiAsync(ApiRoutes.NOTION_CONNECT);
        using var callback = await api.Client.GetApiAsync(ApiRoutes.NOTION_CALLBACK, ("code", NotionTestData.CODE), ("state", "any"));

        connect.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        callback.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        api.Host.Notion.Requests.Should().BeEmpty();
    }

    [Theory]
    [InlineData(ApiRoutes.NOTION_CONNECT)]
    [InlineData(ApiRoutes.NOTION_CALLBACK)]
    public async Task MissingAppUrlAnswersServerError(string route)
    {
        // A4
        using var api = new NowApi(NotionTestData.SettingsWithout(NotionSettings.APP_URL_KEY));

        await api.Client.GetApiAsync(route).ShouldBeProblemAsync(HttpStatusCode.InternalServerError);
    }

    /// <summary>Calls /api/NotionConnect and returns the state value of its redirect.</summary>
    public static async Task<string> ConnectStateAsync(HttpClient client)
    {
        using var response = await client.GetApiAsync(ApiRoutes.NOTION_CONNECT);
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);

        return QueryHelpers.ParseQuery(response.Headers.Location!.Query)["state"].ToString();
    }
}
