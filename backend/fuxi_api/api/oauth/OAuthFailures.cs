using System.Text.Json;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.OAuth;

/// <summary>What the sign-in callbacks of every source treat alike.</summary>
public static class OAuthFailures
{
    /// <summary>
    /// A network error, a timeout, an unreadable answer or a failed save; never the Learner closing the page.
    /// </summary>
    public static bool IsConnectFailure(Exception exception, CancellationToken cancellationToken) =>
        exception is HttpRequestException or JsonException or DbUpdateException
        || (exception is TaskCanceledException && !cancellationToken.IsCancellationRequested);
}
