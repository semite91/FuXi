namespace FuXi.Api.Spotify;

/// <summary>Maps the Spotify endpoints to <see cref="SpotifyService"/>.</summary>
public static class SpotifyEndpoints
{
    public static IEndpointRouteBuilder MapSpotifyEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.SPOTIFY_CONNECT, (SpotifyService service) => TypedResults.Redirect(service.StartSignIn()));

        // Spotify sends the Learner's browser here with code and state, or with error and state.
        routes.MapGet(ApiRoutes.SPOTIFY_CALLBACK, async (string? code, string? state, string? error, SpotifyService service, CancellationToken cancellationToken) =>
            TypedResults.Redirect(await service.HandleCallbackAsync(code, state, error, cancellationToken)));

        routes.MapGet(ApiRoutes.GET_SPOTIFY_CONNECTION, (SpotifyService service, CancellationToken cancellationToken) =>
            service.GetConnectionAsync(cancellationToken));

        routes.MapPost(ApiRoutes.UPDATE_SPOTIFY_PLAYLIST, (UpdateSpotifyPlaylistRequest request, SpotifyService service, CancellationToken cancellationToken) =>
            service.UpdatePlaylistAsync(request.PlaylistLink, cancellationToken));

        return routes;
    }
}
