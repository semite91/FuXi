using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Text;

namespace FuXi.Api.Tests.Api.GoogleDrive;

/// <summary>
/// Stands in for Google behind the API's Google HttpClient. It records every request and answers the token endpoint
/// and Drive's about call each with the status and body set last; by default a full successful sign-in.
/// </summary>
public sealed class FakeGoogleServer : HttpMessageHandler
{
    private const string JSON_MEDIA_TYPE = "application/json";

    private readonly ConcurrentQueue<GoogleRequest> requests = new();
    private Answer tokenAnswer = new(HttpStatusCode.OK, GoogleDriveTestData.FullTokenAnswer, null);
    private Answer aboutAnswer = new(HttpStatusCode.OK, GoogleDriveTestData.AboutAnswer(GoogleDriveTestData.EMAIL), null);

    /// <summary>Every request, in call order.</summary>
    public IReadOnlyList<GoogleRequest> Requests => requests.ToList();

    /// <summary>From now on the token endpoint answers with this status and JSON body.</summary>
    public void AnswerTokenWith(HttpStatusCode status, string body) => tokenAnswer = new Answer(status, body, null);

    /// <summary>From now on the about call answers with this status and JSON body.</summary>
    public void AnswerAboutWith(HttpStatusCode status, string body) => aboutAnswer = new Answer(status, body, null);

    /// <summary>From now on the token endpoint throws this exception, the way an unreachable server does.</summary>
    public void FailTokenWith(Exception exception) => tokenAnswer = tokenAnswer with { Failure = exception };

    /// <summary>From now on the about call throws this exception.</summary>
    public void FailAboutWith(Exception exception) => aboutAnswer = aboutAnswer with { Failure = exception };

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var content = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
        requests.Enqueue(new GoogleRequest(request.Method, request.RequestUri!, request.Headers.Authorization, content));
        var answer = request.RequestUri!.Host == GoogleDriveTestData.TOKEN_HOST ? tokenAnswer : aboutAnswer;
        if (answer.Failure is not null)
        {
            throw answer.Failure;
        }

        return new HttpResponseMessage(answer.Status) { Content = new StringContent(answer.Body, Encoding.UTF8, JSON_MEDIA_TYPE) };
    }

    // IHttpClientFactory disposes its handler chains when they expire; this one lives as long as its ApiHost.
    protected override void Dispose(bool disposing)
    {
    }

    private sealed record Answer(HttpStatusCode Status, string Body, Exception? Failure);
}

/// <summary>One request <see cref="FakeGoogleServer"/> received.</summary>
public sealed record GoogleRequest(HttpMethod Method, Uri Address, AuthenticationHeaderValue? Authorization, string Body);
