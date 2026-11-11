using System.Buffers.Text;
using System.Net;
using FluentAssertions;
using FuXi.Api.Push;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section Q: GetVapidPublicKey.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetVapidPublicKeyTests
{
    private const string CONFIGURED_PUBLIC_KEY = "configured-public-key-of-a-test";
    private const string CONFIGURED_PRIVATE_KEY = "configured-private-key-of-a-test";
    private const int P256_PUBLIC_KEY_LENGTH = 65;
    private const byte UNCOMPRESSED_POINT_MARKER = 4;

    [Fact]
    public async Task EmptyPublicKeyGivesPlaceholder()
    {
        // Q1
        using var api = new NowApi(new NowApiSettings { VapidPublicKey = string.Empty });

        var publicKey = await GetPublicKeyAsync(api);

        publicKey.Should().Be(VapidSettings.PLACEHOLDER_PUBLIC_KEY);
    }

    [Fact]
    public async Task MissingPublicKeyGivesPlaceholder()
    {
        // Q1
        using var api = new NowApi();

        var publicKey = await GetPublicKeyAsync(api);

        publicKey.Should().Be(VapidSettings.PLACEHOLDER_PUBLIC_KEY);
    }

    [Fact]
    public void PlaceholderHasFormatOfP256PublicKey()
    {
        // Q2
        var key = Base64Url.DecodeFromChars(VapidSettings.PLACEHOLDER_PUBLIC_KEY);

        key.Should().HaveCount(P256_PUBLIC_KEY_LENGTH);
        key[0].Should().Be(UNCOMPRESSED_POINT_MARKER);
    }

    [Fact]
    public async Task ConfiguredPublicKeyIsReturned()
    {
        // Q3
        using var api = new NowApi(new NowApiSettings { VapidPublicKey = CONFIGURED_PUBLIC_KEY });

        var publicKey = await GetPublicKeyAsync(api);

        publicKey.Should().Be(CONFIGURED_PUBLIC_KEY);
    }

    [Fact]
    public async Task PrivateKeyIsNotPartOfResponse()
    {
        // Q4
        using var api = new NowApi(new NowApiSettings
        {
            VapidPublicKey = CONFIGURED_PUBLIC_KEY,
            VapidPrivateKey = CONFIGURED_PRIVATE_KEY,
        });
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_VAPID_PUBLIC_KEY);

        var body = await response.ReadTextAsync();

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        body.Should().NotContain(CONFIGURED_PRIVATE_KEY);
        (await response.ReadJsonAsync()).FieldNames().Should().Equal(ApiFields.PUBLIC_KEY);
    }

    private static async Task<string?> GetPublicKeyAsync(NowApi api)
    {
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_VAPID_PUBLIC_KEY);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return (await response.ReadJsonAsync()).Text(ApiFields.PUBLIC_KEY);
    }
}
