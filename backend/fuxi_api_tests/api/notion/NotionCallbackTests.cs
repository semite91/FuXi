using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Notion;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Notion;

/// <summary>Phase 6b section B (test_scenarios_2026_11_17_11_48): GET /api/NotionCallback.</summary>
[Collection(nameof(SmokeTests))]
public sealed class NotionCallbackTests : IDisposable
{
    private const string OTHER_ACCESS_TOKEN = "secret_other-access-token";
    private const string OTHER_REFRESH_TOKEN = "nrt_other-refresh-token";
    private const string OTHER_WORKSPACE_NAME = "Other Workspace";

    private const string FAILING_FUNCTION_SQL = """
        CREATE OR REPLACE FUNCTION fail_statement() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Failure injected by a test';
        END;
        $$ LANGUAGE plpgsql
        """;
    private const string FAIL_WORKSPACE_NAME_INSERT_SQL =
        "CREATE TRIGGER fail_workspace_name_insert BEFORE INSERT ON \"Settings\" FOR EACH ROW " +
        "WHEN (NEW.\"Code\" = '" + SettingCodes.NOTION_WORKSPACE_NAME + "') EXECUTE FUNCTION fail_statement()";

    private readonly DatabaseApi api = new();

    public NotionCallbackTests() => NotionTestData.Configure(api.Settings);

    [Fact]
    public async Task SuccessfulSignInRedirectsToSettingsConnected()
    {
        // B4
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("code", NotionTestData.CODE), ("state", state));

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(NotionTestData.CONNECTED_ADDRESS));
    }

    [Fact]
    public async Task CodeIsSentToNotionTokenEndpointWithBasicClientCredentials()
    {
        // B1
        await SignInAsync();

        var request = api.Notion.Requests.Should().ContainSingle().Subject;
        request.Method.Should().Be(HttpMethod.Post);
        request.Address.Should().Be(new Uri("https://api.notion.com/v1/oauth/token"));
        request.Authorization!.Scheme.Should().Be("Basic");
        Encoding.UTF8.GetString(Convert.FromBase64String(request.Authorization.Parameter!))
            .Should().Be($"{NotionTestData.CLIENT_ID}:{NotionTestData.CLIENT_SECRET}");
        using var body = JsonDocument.Parse(request.Body);
        body.RootElement.GetProperty("grant_type").GetString().Should().Be("authorization_code");
        body.RootElement.GetProperty("code").GetString().Should().Be(NotionTestData.CODE);
        body.RootElement.GetProperty("redirect_uri").GetString().Should().Be(NotionTestData.REDIRECT_URI);
    }

    [Fact]
    public async Task SuccessfulSignInSavesTokensAndWorkspaceName()
    {
        // B2
        await SignInAsync();

        ReadNotionRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.NOTION_ACCESS_TOKEN] = NotionTestData.ACCESS_TOKEN,
            [SettingCodes.NOTION_REFRESH_TOKEN] = NotionTestData.REFRESH_TOKEN,
            [SettingCodes.NOTION_WORKSPACE_NAME] = NotionTestData.WORKSPACE_NAME,
        });
    }

    [Fact]
    public async Task NewSignInUpdatesExistingRowsInPlace()
    {
        // B3
        await SignInAsync();
        var idsBefore = ReadNotionIds();
        api.Notion.AnswerWith(HttpStatusCode.OK, NotionTestData.TokenAnswer(OTHER_ACCESS_TOKEN, OTHER_REFRESH_TOKEN, OTHER_WORKSPACE_NAME));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(NotionTestData.CONNECTED_ADDRESS));
        ReadNotionIds().Should().Equal(idsBefore);
        ReadNotionRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.NOTION_ACCESS_TOKEN] = OTHER_ACCESS_TOKEN,
            [SettingCodes.NOTION_REFRESH_TOKEN] = OTHER_REFRESH_TOKEN,
            [SettingCodes.NOTION_WORKSPACE_NAME] = OTHER_WORKSPACE_NAME,
        });
    }

    [Theory]
    [InlineData("state-this-api-never-made")]
    [InlineData("")]
    [InlineData(null)]
    public async Task UnknownOrMissingStateIsRefusedWithoutCallingNotion(string? state)
    {
        // B5
        await NotionConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("code", NotionTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Fact]
    public async Task StateIsAcceptedJustBeforeTenMinutes()
    {
        // A3
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10) - TimeSpan.FromSeconds(1));

        using var response = await CallbackAsync(("code", NotionTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(NotionTestData.CONNECTED_ADDRESS));
    }

    [Fact]
    public async Task StateIsRefusedAfterTenMinutes()
    {
        // A3, B5
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10));

        using var response = await CallbackAsync(("code", NotionTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Fact]
    public async Task UsedStateIsRefusedTheSecondTime()
    {
        // B6
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);
        await CallbackAsync(("code", NotionTestData.CODE), ("state", state)).ShouldHaveStatusAsync(HttpStatusCode.Redirect);
        var rowsBefore = ReadNotionRows();
        api.Notion.AnswerWith(HttpStatusCode.OK, NotionTestData.TokenAnswer(OTHER_ACCESS_TOKEN, OTHER_REFRESH_TOKEN, OTHER_WORKSPACE_NAME));

        using var response = await CallbackAsync(("code", NotionTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        api.Notion.Requests.Should().ContainSingle();
        ReadNotionRows().Should().BeEquivalentTo(rowsBefore);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(NotionTestData.CODE)] // an error wins even when a code came with it
    public async Task CancelledOnNotionIsRefusedWithoutCallingNotion(string? code)
    {
        // B7
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("error", "access_denied"), ("code", code), ("state", state));

        ShouldBeRefused(response);
    }

    [Theory]
    [InlineData(HttpStatusCode.BadRequest, """{"error":"invalid_grant"}""")]
    [InlineData(HttpStatusCode.InternalServerError, "{}")]
    public async Task ErrorStatusSavesNothingAndIsLoggedWithStatus(HttpStatusCode status, string answer)
    {
        // B8
        api.Notion.AnswerWith(status, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response).Message.Should().Contain(((int)status).ToString(CultureInfo.InvariantCulture));
    }

    [Theory]
    [InlineData("""{"refresh_token":"nrt_refresh-token-of-a-test","workspace_name":"Learner's Workspace"}""")]
    [InlineData("""{"access_token":"","workspace_name":"Learner's Workspace"}""")]
    public async Task AnswerWithoutAccessTokenSavesNothingAndIsLogged(string answer)
    {
        // B8
        api.Notion.AnswerWith(HttpStatusCode.OK, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task NotionTimeoutSavesNothingAndIsLogged()
    {
        // B8: HttpClient reports its own timeout as a cancelled task
        api.Notion.FailWith(new TaskCanceledException("The request timed out.", new TimeoutException()));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task UnreachableNotionSavesNothingAndIsLogged()
    {
        // B8
        api.Notion.FailWith(new HttpRequestException("No connection could be made."));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task UnreadableNotionAnswerSavesNothingAndIsLogged()
    {
        // B8
        api.Notion.AnswerWith(HttpStatusCode.OK, "<html>Bad gateway</html>");

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Theory]
    [InlineData(null, NotionTestData.WORKSPACE_NAME, "", NotionTestData.WORKSPACE_NAME)]
    [InlineData(NotionTestData.REFRESH_TOKEN, null, NotionTestData.REFRESH_TOKEN, "")]
    public async Task MissingOptionalFieldIsSavedEmpty(string? refreshToken, string? workspaceName, string savedRefresh, string savedName)
    {
        // B9
        api.Notion.AnswerWith(HttpStatusCode.OK, NotionTestData.TokenAnswer(NotionTestData.ACCESS_TOKEN, refreshToken, workspaceName));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(NotionTestData.CONNECTED_ADDRESS));
        ReadNotionRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.NOTION_ACCESS_TOKEN] = NotionTestData.ACCESS_TOKEN,
            [SettingCodes.NOTION_REFRESH_TOKEN] = savedRefresh,
            [SettingCodes.NOTION_WORKSPACE_NAME] = savedName,
        });
    }

    [Fact]
    public async Task RowsAreWrittenAllOrNone()
    {
        // B10: the last of the three inserts fails in the database
        api.Arrange(context =>
        {
            context.Database.ExecuteSqlRaw(FAILING_FUNCTION_SQL);
            context.Database.ExecuteSqlRaw(FAIL_WORKSPACE_NAME_INSERT_SQL);
        });

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        ReadNotionRows().Should().BeEmpty();
    }

    public void Dispose() => api.Dispose();

    // A refused callback never reaches Notion and changes no Settings row.
    private void ShouldBeRefused(HttpResponseMessage response)
    {
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        api.Notion.Requests.Should().BeEmpty();
        ReadNotionRows().Should().BeEmpty();
    }

    // A failed exchange saves nothing and logs one error that holds no code and no secret.
    private LogEntry ShouldFailWithOneErrorLog(HttpResponseMessage response)
    {
        response.Headers.Location.Should().Be(new Uri(NotionTestData.FAILED_ADDRESS));
        ReadNotionRows().Should().BeEmpty();
        var entry = api.Logs.Of(typeof(NotionService).FullName!).Should().ContainSingle().Subject;
        entry.Level.Should().Be(LogLevel.Error);
        var logged = entry.Message + entry.Exception;
        logged.Should().NotContain(NotionTestData.CODE)
            .And.NotContain(NotionTestData.CLIENT_SECRET)
            .And.NotContain(NotionTestData.REFRESH_TOKEN);

        return entry;
    }

    private Dictionary<string, Guid> ReadNotionIds() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Id));

    // Starts a sign-in and comes back from Notion with a code, the way the Learner's browser does.
    private async Task<HttpResponseMessage> SignInAsync()
    {
        var state = await NotionConnectTests.ConnectStateAsync(api.Client);

        return await CallbackAsync(("code", NotionTestData.CODE), ("state", state));
    }

    private Dictionary<string, string> ReadNotionRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));

    private Task<HttpResponseMessage> CallbackAsync(params (string Name, string? Value)[] query) =>
        api.Client.GetApiAsync(ApiRoutes.NOTION_CALLBACK, query);
}
