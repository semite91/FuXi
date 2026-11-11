using FluentAssertions;
using FuXi.Api.Tests.Database;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section S: CORS and the checks that need no code reading.</summary>
[Collection(nameof(SmokeTests))]
public sealed class SecurityTests
{
    private const string ORIGIN_HEADER = "Origin";
    private const string ALLOW_ORIGIN_HEADER = "Access-Control-Allow-Origin";
    private const string FIRST_ORIGIN = "https://app.fuxi.test";
    private const string SECOND_ORIGIN = "https://other.fuxi.test";
    private const string UNLISTED_ORIGIN = "https://evil.example.com";
    private const string ENV_EXAMPLE_FILE = ".env.example";
    private const string ENV_TEST_EXAMPLE_FILE = ".env.test.example";
    private const string KEY_WITHOUT_VALUE = CorsSettings.ORIGINS_KEY + "=";
    private static readonly string TWO_ORIGINS = string.Join(CorsSettings.ORIGIN_SEPARATOR, FIRST_ORIGIN, SECOND_ORIGIN);

    [Fact]
    public async Task ConfiguredOriginIsAllowed()
    {
        // S1
        using var api = new NowApi(new NowApiSettings { CorsOrigins = FIRST_ORIGIN });

        using var response = await GetFromOriginAsync(api, FIRST_ORIGIN);

        AllowedOriginsOf(response).Should().Equal(FIRST_ORIGIN);
    }

    [Fact]
    public async Task SecondOfTwoConfiguredOriginsIsAllowed()
    {
        // S2
        using var api = new NowApi(new NowApiSettings { CorsOrigins = TWO_ORIGINS });

        using var response = await GetFromOriginAsync(api, SECOND_ORIGIN);

        AllowedOriginsOf(response).Should().Equal(SECOND_ORIGIN);
    }

    [Fact]
    public async Task OtherOriginIsNotAllowed()
    {
        // S3
        using var api = new NowApi(new NowApiSettings { CorsOrigins = TWO_ORIGINS });

        using var response = await GetFromOriginAsync(api, UNLISTED_ORIGIN);

        AllowedOriginsOf(response).Should().BeEmpty();
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void StartupStopsWhenOriginsAreMissingOrEmpty(string? origins)
    {
        // S4
        using var api = new NowApi(new NowApiSettings { CorsOrigins = origins });

        var start = api.Start;

        var failure = start.Should().Throw<Exception>().Which;
        StartupFailure.Chain(failure).Should().Contain(exception =>
            exception is InvalidOperationException && exception.Message.Contains(CorsSettings.ORIGINS_KEY));
    }

    [Theory]
    [InlineData(ENV_EXAMPLE_FILE)]
    [InlineData(ENV_TEST_EXAMPLE_FILE)]
    public void ExampleEnvFileListsOriginsKeyWithoutValue(string fileName)
    {
        // S5
        var lines = File.ReadAllLines(RepositoryRoot.Combine(fileName)).Select(line => line.Trim());

        lines.Should().Contain(KEY_WITHOUT_VALUE);
    }

    [Fact]
    public void NoAntiforgeryServiceIsUsed()
    {
        // S6
        using var api = new NowApi();

        var endpoints = api.Services.GetRequiredService<EndpointDataSource>().Endpoints;

        api.Services.GetService<IAntiforgery>().Should().BeNull();
        endpoints.Should().NotContain(endpoint => endpoint.Metadata.GetMetadata<IAntiforgeryMetadata>() != null);
    }

    private static async Task<HttpResponseMessage> GetFromOriginAsync(NowApi api, string origin)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, ApiRoutes.GET_VAPID_PUBLIC_KEY);
        request.Headers.Add(ORIGIN_HEADER, origin);

        return await api.Client.SendAsync(request, TestContext.Current.CancellationToken);
    }

    private static IEnumerable<string> AllowedOriginsOf(HttpResponseMessage response) =>
        response.Headers.TryGetValues(ALLOW_ORIGIN_HEADER, out var values) ? values : [];
}
