using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Text;

namespace FuXi.Api.Tests.Api.Spotify;

/// <summary>
/// Stands in for Spotify behind the API's Spotify HttpClient. It records every request and answers the token endpoint,
/// the /v1/me call and the playlist items call each with the status and body set last; by default a full successful sign-in.
/// </summary>
public sealed class FakeSpotifyServer : HttpMessageHandler
{
    private const string JSON_MEDIA_TYPE = "application/json";

    private readonly ConcurrentQueue<SpotifyRequest> requests = new();
    private Answer tokenAnswer = new(HttpStatusCode.OK, SpotifyTestData.FullTokenAnswer, null);
    private Answer playlistAnswer = new(HttpStatusCode.OK, SpotifyTestData.EmptyItemsAnswer, null);
    private Answer meAnswer = new(HttpStatusCode.OK, SpotifyTestData.MeAnswer(SpotifyTestData.USER_ID, SpotifyTestData.DISPLAY_NAME), null);

    /// <summary>Every request, in call order.</summary>
    public IReadOnlyList<SpotifyRequest> Requests => requests.ToList();

    public void AnswerTokenWith(HttpStatusCode status, string body) => tokenAnswer = new Answer(status, body, null);

    public void AnswerMeWith(HttpStatusCode status, string body) => meAnswer = new Answer(status, body, null);

    public void AnswerPlaylistWith(HttpStatusCode status, string body) => playlistAnswer = new Answer(status, body, null);

    public void FailPlaylistWith(Exception exception) => playlistAnswer = playlistAnswer with { Failure = exception };

    public void FailTokenWith(Exception exception) => tokenAnswer = tokenAnswer with { Failure = exception };

    public void FailMeWith(Exception exception) => meAnswer = meAnswer with { Failure = exception };

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var content = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
        requests.Enqueue(new SpotifyRequest(request.Method, request.RequestUri!, request.Headers.Authorization, content));
        var answer = request.RequestUri!.Host == SpotifyTestData.TOKEN_HOST ? tokenAnswer
            : request.RequestUri.AbsolutePath.StartsWith("/v1/playlists/", StringComparison.Ordinal) ? playlistAnswer
            : meAnswer;
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

/// <summary>One request <see cref="FakeSpotifyServer"/> received.</summary>
public sealed record SpotifyRequest(HttpMethod Method, Uri Address, AuthenticationHeaderValue? Authorization, string Body);
