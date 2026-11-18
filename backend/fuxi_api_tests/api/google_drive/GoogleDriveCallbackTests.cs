using System.Globalization;
using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.GoogleDrive;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.GoogleDrive;

/// <summary>Phase 6c sections A3 and B (test_scenarios_2026_11_17_19_42): GET /api/GoogleDriveCallback.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GoogleDriveCallbackTests : IDisposable
{
    private const string OTHER_REFRESH_TOKEN = "1//other-refresh-token";
    private const string OTHER_EMAIL = "other@example.com";
    private const string TOKEN_ADDRESS = "https://oauth2.googleapis.com/token";
    private const string ABOUT_ADDRESS = "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)";

    private const string FAILING_FUNCTION_SQL = """
        CREATE OR REPLACE FUNCTION fail_statement() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Failure injected by a test';
        END;
        $$ LANGUAGE plpgsql
        """;
    private const string FAIL_EMAIL_INSERT_SQL =
        "CREATE TRIGGER fail_email_insert BEFORE INSERT ON \"Settings\" FOR EACH ROW " +
        "WHEN (NEW.\"Code\" = '" + SettingCodes.GOOGLE_DRIVE_EMAIL + "') EXECUTE FUNCTION fail_statement()";

    private readonly DatabaseApi api = new();

    public GoogleDriveCallbackTests() => GoogleDriveTestData.Configure(api.Settings);

    [Fact]
    public async Task CodeIsSentToGoogleTokenEndpointAsForm()
    {
        // B1
        await SignInAsync();

        var request = api.Google.Requests[0];
        request.Method.Should().Be(HttpMethod.Post);
        request.Address.Should().Be(new Uri(TOKEN_ADDRESS));
        var form = QueryHelpers.ParseQuery(request.Body);
        form["grant_type"].ToString().Should().Be("authorization_code");
        form["code"].ToString().Should().Be(GoogleDriveTestData.CODE);
        form["redirect_uri"].ToString().Should().Be(GoogleDriveTestData.REDIRECT_URI);
        form["client_id"].ToString().Should().Be(GoogleDriveTestData.CLIENT_ID);
        form["client_secret"].ToString().Should().Be(GoogleDriveTestData.CLIENT_SECRET);
    }

    [Fact]
    public async Task EmailIsReadWithTheAccessTokenFromDriveAbout()
    {
        // B2
        await SignInAsync();

        api.Google.Requests.Should().HaveCount(2);
        var about = api.Google.Requests[1];
        about.Method.Should().Be(HttpMethod.Get);
        about.Address.Should().Be(new Uri(ABOUT_ADDRESS));
        about.Authorization!.Scheme.Should().Be("Bearer");
        about.Authorization.Parameter.Should().Be(GoogleDriveTestData.ACCESS_TOKEN);
    }

    [Fact]
    public async Task SuccessfulSignInSavesRefreshTokenAndEmailAndRedirectsConnected()
    {
        // B3
        using var response = await SignInAsync();

        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.CONNECTED_ADDRESS));
        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN] = GoogleDriveTestData.REFRESH_TOKEN,
            [SettingCodes.GOOGLE_DRIVE_EMAIL] = GoogleDriveTestData.EMAIL,
        });
    }

    [Fact]
    public async Task SameEmailUpdatesRowsInPlaceAndKeepsFolder()
    {
        // B4
        await SignInAsync();
        AddFolder();
        var idsBefore = ReadIds();
        api.Google.AnswerTokenWith(HttpStatusCode.OK, GoogleDriveTestData.TokenAnswer(GoogleDriveTestData.ACCESS_TOKEN, OTHER_REFRESH_TOKEN, GoogleDriveTestData.DRIVE_SCOPE));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.CONNECTED_ADDRESS));
        ReadIds().Should().Equal(idsBefore);
        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN] = OTHER_REFRESH_TOKEN,
            [SettingCodes.GOOGLE_DRIVE_EMAIL] = GoogleDriveTestData.EMAIL,
            [SettingCodes.GOOGLE_DRIVE_FOLDER_ID] = GoogleDriveTestData.FOLDER_ID,
        });
    }

    [Fact]
    public async Task SameEmailWithOtherLettersKeepsFolder()
    {
        // B4 (review): Google may answer the same account with other upper and lower case letters
        await SignInAsync();
        AddFolder();
        api.Google.AnswerAboutWith(HttpStatusCode.OK, GoogleDriveTestData.AboutAnswer(GoogleDriveTestData.EMAIL.ToUpperInvariant()));

        await SignInAsync();

        ReadRows()[SettingCodes.GOOGLE_DRIVE_FOLDER_ID].Should().Be(GoogleDriveTestData.FOLDER_ID);
    }

    [Fact]
    public async Task OtherEmailClearsTheSavedFolder()
    {
        // B5
        await SignInAsync();
        AddFolder();
        api.Google.AnswerAboutWith(HttpStatusCode.OK, GoogleDriveTestData.AboutAnswer(OTHER_EMAIL));

        await SignInAsync();

        ReadRows().Should().BeEquivalentTo(new Dictionary<string, string>
        {
            [SettingCodes.GOOGLE_DRIVE_REFRESH_TOKEN] = GoogleDriveTestData.REFRESH_TOKEN,
            [SettingCodes.GOOGLE_DRIVE_EMAIL] = OTHER_EMAIL,
            [SettingCodes.GOOGLE_DRIVE_FOLDER_ID] = string.Empty,
        });
    }

    [Fact]
    public async Task StateIsAcceptedJustBeforeTenMinutes()
    {
        // A3
        var state = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10) - TimeSpan.FromSeconds(1));

        using var response = await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.CONNECTED_ADDRESS));
    }

    [Fact]
    public async Task StateIsRefusedAfterTenMinutes()
    {
        // A3, B6
        var state = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);
        api.Clock.Advance(TimeSpan.FromMinutes(10));

        using var response = await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Theory]
    [InlineData("state-this-api-never-made")]
    [InlineData("")]
    [InlineData(null)]
    public async Task UnknownOrMissingStateIsRefused(string? state)
    {
        // B6
        await GoogleDriveConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state));

        ShouldBeRefused(response);
    }

    [Fact]
    public async Task UsedStateIsRefusedTheSecondTime()
    {
        // B6
        var state = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);
        await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state)).ShouldHaveStatusAsync(HttpStatusCode.Redirect);
        var rowsBefore = ReadRows();

        using var response = await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state));

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        api.Google.Requests.Should().HaveCount(2);
        ReadRows().Should().BeEquivalentTo(rowsBefore);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(GoogleDriveTestData.CODE)] // an error wins even when a code came with it
    public async Task CancelledOnGoogleIsRefused(string? code)
    {
        // B7
        var state = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);

        using var response = await CallbackAsync(("error", "access_denied"), ("code", code), ("state", state));

        ShouldBeRefused(response);
    }

    [Theory]
    [InlineData(HttpStatusCode.BadRequest, """{"error":"invalid_grant"}""")]
    [InlineData(HttpStatusCode.InternalServerError, "{}")]
    public async Task TokenErrorStatusSavesNothingAndIsLoggedWithStatus(HttpStatusCode status, string answer)
    {
        // B8, B10
        api.Google.AnswerTokenWith(status, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response).Message.Should().Contain(((int)status).ToString(CultureInfo.InvariantCulture));
    }

    [Theory]
    [InlineData(null, GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.DRIVE_SCOPE)]
    [InlineData("", GoogleDriveTestData.REFRESH_TOKEN, GoogleDriveTestData.DRIVE_SCOPE)]
    [InlineData(GoogleDriveTestData.ACCESS_TOKEN, null, GoogleDriveTestData.DRIVE_SCOPE)]
    [InlineData(GoogleDriveTestData.ACCESS_TOKEN, "", GoogleDriveTestData.DRIVE_SCOPE)]
    [InlineData(GoogleDriveTestData.ACCESS_TOKEN, GoogleDriveTestData.REFRESH_TOKEN, null)]
    [InlineData(GoogleDriveTestData.ACCESS_TOKEN, GoogleDriveTestData.REFRESH_TOKEN, "openid email")]
    [InlineData(GoogleDriveTestData.ACCESS_TOKEN, GoogleDriveTestData.REFRESH_TOKEN, "https://www.googleapis.com/auth/drive.readonly.metadata")]
    public async Task IncompleteTokenAnswerSavesNothingAndIsLogged(string? accessToken, string? refreshToken, string? scope)
    {
        // B8: a missing token, or the Learner unticked Drive on the consent screen
        api.Google.AnswerTokenWith(HttpStatusCode.OK, GoogleDriveTestData.TokenAnswer(accessToken, refreshToken, scope));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task ScopeAmongOtherScopesIsAccepted()
    {
        // B8: Google lists every granted scope, joined with spaces
        api.Google.AnswerTokenWith(HttpStatusCode.OK, GoogleDriveTestData.TokenAnswer(
            GoogleDriveTestData.ACCESS_TOKEN, GoogleDriveTestData.REFRESH_TOKEN, "openid " + GoogleDriveTestData.DRIVE_SCOPE));

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.CONNECTED_ADDRESS));
    }

    [Theory]
    [InlineData(HttpStatusCode.Unauthorized, "{}")]
    [InlineData(HttpStatusCode.OK, """{"user":{}}""")]
    [InlineData(HttpStatusCode.OK, """{"user":{"emailAddress":""}}""")]
    [InlineData(HttpStatusCode.OK, "<html>Bad gateway</html>")]
    public async Task FailedAboutCallSavesNothingAndIsLogged(HttpStatusCode status, string answer)
    {
        // B9, B10
        api.Google.AnswerAboutWith(status, answer);

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task AboutTimeoutSavesNothingAndIsLogged()
    {
        // B9: HttpClient reports its own timeout as a cancelled task
        api.Google.FailAboutWith(new TaskCanceledException("The request timed out.", new TimeoutException()));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task UnreachableGoogleSavesNothingAndIsLogged()
    {
        // B8, B10
        api.Google.FailTokenWith(new HttpRequestException("No connection could be made."));

        using var response = await SignInAsync();

        ShouldFailWithOneErrorLog(response);
    }

    [Fact]
    public async Task RowsAreWrittenAllOrNone()
    {
        // B3: the email insert fails in the database
        api.Arrange(context =>
        {
            context.Database.ExecuteSqlRaw(FAILING_FUNCTION_SQL);
            context.Database.ExecuteSqlRaw(FAIL_EMAIL_INSERT_SQL);
        });

        using var response = await SignInAsync();

        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        ReadRows().Should().BeEmpty();
    }

    public void Dispose() => api.Dispose();

    // A refused callback never reaches Google and changes no Settings row.
    private void ShouldBeRefused(HttpResponseMessage response)
    {
        response.StatusCode.Should().Be(HttpStatusCode.Redirect);
        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        api.Google.Requests.Should().BeEmpty();
        ReadRows().Should().BeEmpty();
    }

    // A failed sign-in saves nothing and logs one error that holds no code, token or secret.
    private LogEntry ShouldFailWithOneErrorLog(HttpResponseMessage response)
    {
        response.Headers.Location.Should().Be(new Uri(GoogleDriveTestData.FAILED_ADDRESS));
        ReadRows().Should().BeEmpty();
        var entry = api.Logs.Of(typeof(GoogleDriveService).FullName!).Should().ContainSingle().Subject;
        entry.Level.Should().Be(LogLevel.Error);
        var logged = entry.Message + entry.Exception;
        logged.Should().NotContain(GoogleDriveTestData.CODE)
            .And.NotContain(GoogleDriveTestData.CLIENT_SECRET)
            .And.NotContain(GoogleDriveTestData.ACCESS_TOKEN)
            .And.NotContain(GoogleDriveTestData.REFRESH_TOKEN);

        return entry;
    }

    private void AddFolder() =>
        api.Arrange(context =>
        {
            context.Settings.Add(new Setting { Code = SettingCodes.GOOGLE_DRIVE_FOLDER_ID, Value = GoogleDriveTestData.FOLDER_ID });
            context.SaveChanges();
        });

    // Starts a sign-in and comes back from Google with a code, the way the Learner's browser does.
    private async Task<HttpResponseMessage> SignInAsync()
    {
        var state = await GoogleDriveConnectTests.ConnectStateAsync(api.Client);

        return await CallbackAsync(("code", GoogleDriveTestData.CODE), ("state", state));
    }

    private Dictionary<string, Guid> ReadIds() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Id));

    private Dictionary<string, string> ReadRows() =>
        api.Read(context => context.Settings.AsNoTracking().ToDictionary(setting => setting.Code, setting => setting.Value));

    private Task<HttpResponseMessage> CallbackAsync(params (string Name, string? Value)[] query) =>
        api.Client.GetApiAsync(ApiRoutes.GOOGLE_DRIVE_CALLBACK, query);
}
