using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Text;

namespace FuXi.Api.Tests.Api.Notion;

/// <summary>
/// Stands in for api.notion.com behind the API's Notion HttpClient. It records every request
/// and answers each one with the status and body set last; by default a full successful token answer.
/// </summary>
public sealed class FakeNotionServer : HttpMessageHandler
{
    private const string JSON_MEDIA_TYPE = "application/json";

    private readonly ConcurrentQueue<NotionRequest> requests = new();
    private HttpStatusCode status = HttpStatusCode.OK;
    private string body = NotionTestData.FullTokenAnswer;
    private Exception? failure;

    /// <summary>Every request, in call order.</summary>
    public IReadOnlyList<NotionRequest> Requests => requests.ToList();

    /// <summary>From now on every request is answered with this status and JSON body.</summary>
    public void AnswerWith(HttpStatusCode answerStatus, string answerBody)
    {
        status = answerStatus;
        body = answerBody;
    }

    /// <summary>From now on every request throws this exception, the way an unreachable server does.</summary>
    public void FailWith(Exception exception) => failure = exception;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var content = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
        requests.Enqueue(new NotionRequest(request.Method, request.RequestUri!, request.Headers.Authorization, content));
        if (failure is not null)
        {
            throw failure;
        }

        return new HttpResponseMessage(status) { Content = new StringContent(body, Encoding.UTF8, JSON_MEDIA_TYPE) };
    }

    // IHttpClientFactory disposes its handler chains when they expire; this one lives as long as its ApiHost.
    protected override void Dispose(bool disposing)
    {
    }
}

/// <summary>One request <see cref="FakeNotionServer"/> received.</summary>
public sealed record NotionRequest(HttpMethod Method, Uri Address, AuthenticationHeaderValue? Authorization, string Body);
