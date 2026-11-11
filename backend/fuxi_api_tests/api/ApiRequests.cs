using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Sends requests to the API and reads its answers.</summary>
public static class ApiRequests
{
    public const string NOT_A_GUID = "not-a-guid";
    public const string PROBLEM_MEDIA_TYPE = "application/problem+json";
    private const char QUERY_START = '?';
    private const char QUERY_SEPARATOR = '&';
    private const char ASSIGNMENT = '=';
    private static readonly JsonSerializerOptions JSON_OPTIONS = new(JsonSerializerDefaults.Web);

    public static Task<HttpResponseMessage> GetApiAsync(
        this HttpClient client, string route, params (string Name, string? Value)[] query) =>
        client.GetAsync(WithQuery(route, query), TestContext.Current.CancellationToken);

    public static Task<HttpResponseMessage> DeleteApiAsync(
        this HttpClient client, string route, params (string Name, string? Value)[] query) =>
        client.DeleteAsync(WithQuery(route, query), TestContext.Current.CancellationToken);

    /// <summary>Posts the body as camelCase JSON. A property the body does not have is not sent.</summary>
    public static async Task<HttpResponseMessage> PostApiAsync(this HttpClient client, string route, object body)
    {
        using var content = JsonContent.Create(body, body.GetType(), options: JSON_OPTIONS);

        return await client.PostAsync(route, content, TestContext.Current.CancellationToken);
    }

    /// <summary>Calls a GET route, expects 200 and returns the items of its JSON list.</summary>
    public static async Task<IReadOnlyList<JsonElement>> GetItemsAsync(
        this HttpClient client, string route, params (string Name, string? Value)[] query)
    {
        using var response = await client.GetApiAsync(route, query);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return (await response.ReadJsonAsync()).Items();
    }

    public static async Task<string> ReadTextAsync(this HttpResponseMessage response) =>
        await response.Content.ReadAsStringAsync(TestContext.Current.CancellationToken);

    public static async Task<JsonElement> ReadJsonAsync(this HttpResponseMessage response)
    {
        using var document = JsonDocument.Parse(await response.ReadTextAsync());

        return document.RootElement.Clone();
    }

    public static async Task ShouldHaveStatusAsync(this Task<HttpResponseMessage> call, HttpStatusCode status)
    {
        using var response = await call;

        response.StatusCode.Should().Be(status);
    }

    /// <summary>Expects the status and a ProblemDetails body that repeats it.</summary>
    public static async Task ShouldBeProblemAsync(this Task<HttpResponseMessage> call, HttpStatusCode status)
    {
        using var response = await call;

        response.StatusCode.Should().Be(status);
        response.Content.Headers.ContentType?.MediaType.Should().Be(PROBLEM_MEDIA_TYPE);
        (await response.ReadJsonAsync()).Number(ApiFields.STATUS).Should().Be((int)status);
    }

    private static string WithQuery(string route, (string Name, string? Value)[] query) =>
        query.Length == 0
            ? route
            : route + QUERY_START + string.Join(QUERY_SEPARATOR, query.Select(ToQueryPart));

    private static string ToQueryPart((string Name, string? Value) pair) =>
        $"{pair.Name}{ASSIGNMENT}{Uri.EscapeDataString(pair.Value ?? string.Empty)}";
}
