namespace FuXi.Api.GoogleDrive;

/// <summary>Maps the Google Drive endpoints to <see cref="GoogleDriveService"/>.</summary>
public static class GoogleDriveEndpoints
{
    public static IEndpointRouteBuilder MapGoogleDriveEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GOOGLE_DRIVE_CONNECT, (GoogleDriveService service) => TypedResults.Redirect(service.StartSignIn()));

        // Google sends the Learner's browser here with code and state, or with error and state.
        routes.MapGet(ApiRoutes.GOOGLE_DRIVE_CALLBACK, async (string? code, string? state, string? error, GoogleDriveService service, CancellationToken cancellationToken) =>
            TypedResults.Redirect(await service.HandleCallbackAsync(code, state, error, cancellationToken)));

        routes.MapGet(ApiRoutes.GET_GOOGLE_DRIVE_CONNECTION, (GoogleDriveService service, CancellationToken cancellationToken) =>
            service.GetConnectionAsync(cancellationToken));

        routes.MapPost(ApiRoutes.UPDATE_GOOGLE_DRIVE_FOLDER, (UpdateGoogleDriveFolderRequest request, GoogleDriveService service, CancellationToken cancellationToken) =>
            service.UpdateFolderAsync(request.FolderLink, cancellationToken));

        return routes;
    }
}
