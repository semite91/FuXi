using System.Buffers.Text;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 section F (test_scenarios_2026_11_12_22_06): the real push sender against a fake push service.</summary>
[Collection(nameof(SmokeTests))]
public sealed partial class WebPushMessageSenderTests
{
    private const string FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send/first";
    private const string MOZILLA_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/second";
    private const string SUBJECT = "mailto:learner@fuxi.test";
    private const string PAYLOAD = """{"title":"apple","wordIds":""}""";
    private const string VAPID_SCHEME = "vapid";
    private const string JWT_ALGORITHM = "ES256";
    private const string ALGORITHM_FIELD = "alg";
    private const string AUDIENCE_FIELD = "aud";
    private const string SUBJECT_FIELD = "sub";
    private const char JWT_PART_SEPARATOR = '.';
    private const int JWT_PART_COUNT = 3;
    private const int AUTH_SECRET_BYTES = 16;

    // An uncompressed elliptic curve point (SEC 1): one marker byte, then X and Y of 32 bytes each.
    private const byte UNCOMPRESSED_POINT_MARKER = 4;
    private const int POINT_MARKER_BYTES = 1;
    private const int COORDINATE_BYTES = 32;

    private static readonly string[] Endpoints = [FCM_ENDPOINT, MOZILLA_ENDPOINT];

    // Only reached when a test fails: a push that never arrives.
    private static readonly TimeSpan WaitLimit = TimeSpan.FromSeconds(10);

    private static CancellationToken Token => TestContext.Current.CancellationToken;

    [Fact]
    public async Task EachSendGetsItsOwnVapidAuthentication()
    {
        // F11: the fake push service answers only once both pushes arrived, so they are signed and sent at the same time;
        // each must still carry a whole VAPID header that verifies with the public key, for the push service it goes to.
        var keys = VapidKeyGenerator.Generate();
        var vapid = new VapidDetails(keys.PublicKey, keys.PrivateKey, SUBJECT);
        using var pushService = new ParallelPushService(Endpoints.Length);
        using var httpClient = new HttpClient(pushService);
        var sender = new WebPushMessageSender(httpClient);

        await Task.WhenAll(Endpoints.Select(endpoint => sender.SendAsync(CreateSubscription(endpoint), PAYLOAD, vapid, Token)))
            .WaitAsync(WaitLimit, Token);

        pushService.Requests.Select(request => request.Endpoint).Should().BeEquivalentTo(Endpoints);
        foreach (var request in pushService.Requests)
        {
            VerifyVapidHeader(request.Authorization, request.Endpoint, keys.PublicKey);
        }
    }

    private static void VerifyVapidHeader(AuthenticationHeaderValue? authorization, string endpoint, string publicKey)
    {
        authorization.Should().NotBeNull();
        authorization!.Scheme.Should().Be(VAPID_SCHEME);
        var match = VapidParameter().Match(authorization.Parameter ?? string.Empty);
        match.Success.Should().BeTrue();
        match.Groups["key"].Value.Should().Be(publicKey);

        var parts = match.Groups["token"].Value.Split(JWT_PART_SEPARATOR);
        parts.Should().HaveCount(JWT_PART_COUNT);
        ReadJson(parts[0]).GetProperty(ALGORITHM_FIELD).GetString().Should().Be(JWT_ALGORITHM);
        var claims = ReadJson(parts[1]);
        claims.GetProperty(AUDIENCE_FIELD).GetString().Should().Be(new Uri(endpoint).GetLeftPart(UriPartial.Authority));
        claims.GetProperty(SUBJECT_FIELD).GetString().Should().Be(SUBJECT);

        using var verifier = ECDsa.Create(PublicKeyParameters(publicKey));
        var signedData = Encoding.ASCII.GetBytes(parts[0] + JWT_PART_SEPARATOR + parts[1]);
        verifier.VerifyData(signedData, Base64Url.DecodeFromChars(parts[2]), HashAlgorithmName.SHA256).Should().BeTrue();
    }

    private static ECParameters PublicKeyParameters(string publicKey)
    {
        var point = Base64Url.DecodeFromChars(publicKey);

        return new ECParameters
        {
            Curve = ECCurve.NamedCurves.nistP256,
            Q = new ECPoint
            {
                X = point[POINT_MARKER_BYTES..(POINT_MARKER_BYTES + COORDINATE_BYTES)],
                Y = point[(POINT_MARKER_BYTES + COORDINATE_BYTES)..],
            },
        };
    }

    private static JsonElement ReadJson(string base64Url)
    {
        using var document = JsonDocument.Parse(Base64Url.DecodeFromChars(base64Url));

        return document.RootElement.Clone();
    }

    // Real browser keys, so the payload can be encrypted: a P-256 public key and a random auth secret.
    private static PushSubscription CreateSubscription(string endpoint)
    {
        using var browserKey = ECDiffieHellman.Create(ECCurve.NamedCurves.nistP256);
        var parameters = browserKey.ExportParameters(includePrivateParameters: false);
        byte[] point = [UNCOMPRESSED_POINT_MARKER, .. parameters.Q.X!, .. parameters.Q.Y!];

        return new PushSubscription
        {
            Endpoint = endpoint,
            P256dh = Base64Url.EncodeToString(point),
            Auth = Base64Url.EncodeToString(RandomNumberGenerator.GetBytes(AUTH_SECRET_BYTES)),
        };
    }

    [GeneratedRegex("^t=(?<token>[^,]+), k=(?<key>.+)$")]
    private static partial Regex VapidParameter();

    private sealed record RecordedRequest(string Endpoint, AuthenticationHeaderValue? Authorization);

    // Records every request and holds each one until the expected number arrived, then answers 201 Created to all.
    private sealed class ParallelPushService(int expectedRequests) : HttpMessageHandler
    {
        private readonly ConcurrentQueue<RecordedRequest> requests = new();
        private readonly TaskCompletionSource allArrived = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int arrived;

        public IReadOnlyList<RecordedRequest> Requests => requests.ToList();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            requests.Enqueue(new RecordedRequest(request.RequestUri!.ToString(), request.Headers.Authorization));
            if (Interlocked.Increment(ref arrived) == expectedRequests)
            {
                allArrived.TrySetResult();
            }

            await allArrived.Task.WaitAsync(WaitLimit, cancellationToken);

            return new HttpResponseMessage(HttpStatusCode.Created);
        }
    }
}
