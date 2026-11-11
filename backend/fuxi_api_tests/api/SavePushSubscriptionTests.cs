using System.Net;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section R: SavePushSubscription.</summary>
[Collection(nameof(SmokeTests))]
public sealed class SavePushSubscriptionTests : IDisposable
{
    private const string ENDPOINT_FIELD = "endpoint";
    private const string P256DH_FIELD = "p256dh";
    private const string AUTH_FIELD = "auth";
    private const string FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send/subscription-1";
    private const string MOZILLA_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/subscription-1";
    private const string WINDOWS_ENDPOINT = "https://db5p.notify.windows.com/w/?token=subscription-1";
    private const string APPLE_ENDPOINT = "https://web.push.apple.com/subscription-1";
    private const string JMT17_ENDPOINT = "https://jmt17.google.com/fcm/send/subscription-1";
    private const string SPACE = " ";
    private const string ENDPOINT_AFTER_SPACE = SPACE + FCM_ENDPOINT;
    private const string ENDPOINT_BEFORE_SPACE = FCM_ENDPOINT + SPACE;
    private const string HTTP_ENDPOINT ="http://fcm.googleapis.com/fcm/send/subscription-1";
    private const string OTHER_HOST_ENDPOINT = "https://push.example.com/subscription-1";
    private const string NOT_A_SUB_DOMAIN_ENDPOINT = "https://fakenotify.windows.com/w/?token=subscription-1";
    private const string LOOK_ALIKE_ENDPOINT = "https://fcm.googleapis.com.example.com/fcm/send/subscription-1";
    private const string IPV4_ENDPOINT = "https://127.0.0.1/fcm/send/subscription-1";
    private const string IPV6_ENDPOINT = "https://[::1]/fcm/send/subscription-1";
    private const string LOCALHOST_ENDPOINT = "https://localhost/fcm/send/subscription-1";
    private const string TEXT_ENDPOINT = "not-a-url";
    private const string RELATIVE_ENDPOINT = "/fcm/send/subscription-1";
    private const string P256DH = "p256dh-of-a-test";
    private const string AUTH = "auth-of-a-test";
    private const string OTHER_P256DH = "other-p256dh-of-a-test";
    private const string OTHER_AUTH = "other-auth-of-a-test";
    private const int HOURS_UNTIL_SECOND_CALL = 1;

    private readonly DatabaseApi databaseApi = new();
    private readonly NowApi nowApi = new();

    [Theory]
    [InlineData(FCM_ENDPOINT)] // R1, R2, R3
    [InlineData(MOZILLA_ENDPOINT)] // R9
    [InlineData(WINDOWS_ENDPOINT)] // R9
    [InlineData(APPLE_ENDPOINT)] // R9
    [InlineData(JMT17_ENDPOINT)] // Review R10
    public async Task ValidSubscriptionIsSavedWithSentValuesAndCurrentDate(string endpoint)
    {
        // R1, R2, R3, R9
        using var response = await SaveAsync(databaseApi.Client, endpoint, P256DH, AUTH);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadTextAsync()).Should().BeEmpty();
        var stored = ReadSubscriptions().Should().ContainSingle().Subject;
        stored.Endpoint.Should().Be(endpoint);
        stored.P256dh.Should().Be(P256DH);
        stored.Auth.Should().Be(AUTH);
        stored.CreatedDate.Should().Be(TestData.Now);
    }

    [Fact]
    public async Task ExistingEndpointIsNotAddedAgainAndNotChanged()
    {
        // R4, R5
        await SaveAsync(databaseApi.Client, FCM_ENDPOINT, P256DH, AUTH).ShouldHaveStatusAsync(HttpStatusCode.OK);
        var existing = ReadSubscriptions().Should().ContainSingle().Subject;
        databaseApi.Clock.Advance(TimeSpan.FromHours(HOURS_UNTIL_SECOND_CALL));

        using var response = await SaveAsync(databaseApi.Client, FCM_ENDPOINT, OTHER_P256DH, OTHER_AUTH);

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.ReadTextAsync()).Should().BeEmpty();
        ReadSubscriptions().Should().ContainSingle().Which.Should().BeEquivalentTo(existing);
    }

    [Theory]
    [InlineData(null, P256DH, AUTH)]
    [InlineData("", P256DH, AUTH)]
    [InlineData(FCM_ENDPOINT, null, AUTH)]
    [InlineData(FCM_ENDPOINT, "", AUTH)]
    [InlineData(FCM_ENDPOINT, P256DH, null)]
    [InlineData(FCM_ENDPOINT, P256DH, "")]
    public async Task MissingOrEmptyFieldIsBadRequest(string? endpoint, string? p256dh, string? auth)
    {
        // R6: a null value here means the property is not sent at all.
        await SaveAsync(nowApi.Client, endpoint, p256dh, auth).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Theory]
    [InlineData(TEXT_ENDPOINT)] // R7
    [InlineData(RELATIVE_ENDPOINT)] // R7
    [InlineData(HTTP_ENDPOINT)] // R8
    [InlineData(OTHER_HOST_ENDPOINT)] // R10
    [InlineData(NOT_A_SUB_DOMAIN_ENDPOINT)] // R10
    [InlineData(LOOK_ALIKE_ENDPOINT)] // R11
    [InlineData(IPV4_ENDPOINT)] // R12
    [InlineData(IPV6_ENDPOINT)] // R12
    [InlineData(LOCALHOST_ENDPOINT)] // R12
    public async Task EndpointOutsideAllowedPushServicesIsBadRequest(string endpoint)
    {
        // R7, R8, R10, R11, R12
        await SaveAsync(nowApi.Client, endpoint, P256DH, AUTH).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Theory]
    [InlineData(ENDPOINT_AFTER_SPACE)]
    [InlineData(ENDPOINT_BEFORE_SPACE)]
    public async Task EndpointWithSurroundingWhitespaceIsBadRequest(string endpoint)
    {
        // Review R4: the endpoint is stored and compared as sent, so it must arrive without padding.
        await SaveAsync(nowApi.Client, endpoint, P256DH, AUTH).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Theory]
    [InlineData(FCM_ENDPOINT)]
    [InlineData(MOZILLA_ENDPOINT)]
    [InlineData(WINDOWS_ENDPOINT)]
    [InlineData(APPLE_ENDPOINT)]
    [InlineData(JMT17_ENDPOINT)] // Review R10
    public async Task EndpointOfAllowedPushServicePassesCheck(string endpoint)
    {
        // R9: this host has no database, so an allowed endpoint gets past the check and fails only at saving.
        await SaveAsync(nowApi.Client, endpoint, P256DH, AUTH).ShouldHaveStatusAsync(HttpStatusCode.InternalServerError);
    }

    public void Dispose()
    {
        databaseApi.Dispose();
        nowApi.Dispose();
    }

    private static Task<HttpResponseMessage> SaveAsync(HttpClient client, string? endpoint, string? p256dh, string? auth)
    {
        (string Name, string? Value)[] fields = [(ENDPOINT_FIELD, endpoint), (P256DH_FIELD, p256dh), (AUTH_FIELD, auth)];
        var body = fields.Where(field => field.Value is not null).ToDictionary(field => field.Name, field => field.Value);

        return client.PostApiAsync(ApiRoutes.SAVE_PUSH_SUBSCRIPTION, body);
    }

    private List<PushSubscription> ReadSubscriptions() =>
        databaseApi.Read(context => context.PushSubscriptions.AsNoTracking().ToList());
}
