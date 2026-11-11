using System.Net;
using FluentAssertions;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section B: the route table and the conventions every route follows.</summary>
[Collection(nameof(SmokeTests))]
public sealed class RouteTests : IDisposable
{
    private const string GET = "GET";
    private const string POST = "POST";
    private const string DELETE = "DELETE";
    private const string ANY_METHOD = "*";
    private const char ROUTE_SEPARATOR = '/';
    private const int ROUTE_COUNT = 15;
    private const string INTERNAL_FUNCTION_NAME = "GetNotificationWords";
    private const string INTERNAL_FUNCTION_ROUTE = ApiRoutes.PREFIX + "/" + INTERNAL_FUNCTION_NAME;
    private static readonly string[] GET_ROUTES =
    [
        ApiRoutes.GET_CARD_WORDS,
        ApiRoutes.GET_WORDS_BY_ACTIVE,
        ApiRoutes.GET_WORD_HISTORY,
        ApiRoutes.GET_WORDS_BY_FILTER,
        ApiRoutes.GET_CONFIGS,
        ApiRoutes.GET_SCHEDULE,
        ApiRoutes.GET_VAPID_PUBLIC_KEY,
    ];
    private static readonly string[] POST_ROUTES =
    [
        ApiRoutes.UPDATE_WORD_CONTENT,
        ApiRoutes.UPDATE_WORD_KNOWN_STATUS,
        ApiRoutes.UPDATE_IS_REINFORCEMENT,
        ApiRoutes.UPDATE_CONFIG,
        ApiRoutes.UPDATE_NOTIFICATION_PERIOD,
        ApiRoutes.UPDATE_SCHEDULE,
        ApiRoutes.SAVE_PUSH_SUBSCRIPTION,
    ];
    private static readonly string[] DELETE_ROUTES = [ApiRoutes.DELETE_SCHEDULE];

    private readonly NowApi api = new();

    [Fact]
    public void GetRoutesExist()
    {
        // B1
        ListRoutes().Should().Contain(GET_ROUTES.Select(route => (route, GET)));
    }

    [Fact]
    public void PostRoutesExist()
    {
        // B2
        ListRoutes().Should().Contain(POST_ROUTES.Select(route => (route, POST)));
    }

    [Fact]
    public void DeleteRouteExists()
    {
        // B3
        ListRoutes().Should().Contain(DELETE_ROUTES.Select(route => (route, DELETE)));
    }

    [Fact]
    public async Task NoRouteExistsForGetNotificationWords()
    {
        // B4
        ListRoutes().Should().NotContain(route => route.Route.Contains(INTERNAL_FUNCTION_NAME, StringComparison.OrdinalIgnoreCase));

        await api.Client.GetApiAsync(INTERNAL_FUNCTION_ROUTE).ShouldHaveStatusAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public void ApiHasExactlyFifteenRoutes()
    {
        // B5
        (string Route, string Method)[] expected =
        [
            .. GET_ROUTES.Select(route => (route, GET)),
            .. POST_ROUTES.Select(route => (route, POST)),
            .. DELETE_ROUTES.Select(route => (route, DELETE)),
        ];

        var routes = ListRoutes();

        routes.Should().HaveCount(ROUTE_COUNT);
        routes.Should().BeEquivalentTo(expected);
    }

    [Fact]
    public async Task JsonPropertyNamesAreCamelCase()
    {
        // B6: the database tests check the names of every other response in the same way.
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_VAPID_PUBLIC_KEY);

        var body = await response.ReadJsonAsync();

        body.FieldNames().Should().Equal(ApiFields.PUBLIC_KEY);
    }

    [Fact]
    public async Task BadRequestIsProblemDetails()
    {
        // B7
        await api.Client.GetApiAsync(ApiRoutes.GET_CARD_WORDS).ShouldBeProblemAsync(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task NotFoundIsProblemDetails()
    {
        // B7
        await api.Client.GetApiAsync(INTERNAL_FUNCTION_ROUTE).ShouldBeProblemAsync(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task MethodNotAllowedIsProblemDetails()
    {
        // B7
        await PostEmptyBodyAsync(ApiRoutes.GET_VAPID_PUBLIC_KEY).ShouldBeProblemAsync(HttpStatusCode.MethodNotAllowed);
    }

    [Theory]
    [InlineData(ApiRoutes.GET_CARD_WORDS)]
    [InlineData(ApiRoutes.GET_WORDS_BY_ACTIVE)]
    [InlineData(ApiRoutes.GET_WORD_HISTORY)]
    [InlineData(ApiRoutes.GET_WORDS_BY_FILTER)]
    [InlineData(ApiRoutes.GET_CONFIGS)]
    [InlineData(ApiRoutes.GET_SCHEDULE)]
    [InlineData(ApiRoutes.GET_VAPID_PUBLIC_KEY)]
    public async Task GetRouteCalledWithPostIsNotAllowed(string route)
    {
        // B8
        await PostEmptyBodyAsync(route).ShouldHaveStatusAsync(HttpStatusCode.MethodNotAllowed);
    }

    public void Dispose() => api.Dispose();

    private Task<HttpResponseMessage> PostEmptyBodyAsync(string route) => api.Client.PostApiAsync(route, new { });

    // One item per route and HTTP method, read from the routing table instead of by calling the route.
    private List<(string Route, string Method)> ListRoutes() =>
        api.Services.GetRequiredService<EndpointDataSource>().Endpoints
            .OfType<RouteEndpoint>()
            .SelectMany(MethodsOf, (endpoint, method) => (PathOf(endpoint), method))
            .ToList();

    private static IEnumerable<string> MethodsOf(RouteEndpoint endpoint) =>
        endpoint.Metadata.GetMetadata<IHttpMethodMetadata>()?.HttpMethods ?? [ANY_METHOD];

    private static string PathOf(RouteEndpoint endpoint) =>
        ROUTE_SEPARATOR + (endpoint.RoutePattern.RawText ?? string.Empty).Trim(ROUTE_SEPARATOR);
}
