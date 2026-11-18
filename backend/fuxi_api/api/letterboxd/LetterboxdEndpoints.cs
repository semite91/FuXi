using Microsoft.AspNetCore.Mvc;

namespace FuXi.Api.Letterboxd;

/// <summary>Maps the Letterboxd endpoints to <see cref="LetterboxdService"/>.</summary>
public static class LetterboxdEndpoints
{
    /// <summary>The header the app sends with an upload. A form on another website cannot add it without a preflight.</summary>
    public const string APP_HEADER = "X-Requested-With";
    public const string APP_HEADER_VALUE = "FuXi";

    // A little above the 5 MB file limit (form fields and boundaries), so a bigger body is stopped before it is buffered.
    private const long MAX_REQUEST_BYTES = 6 * 1024 * 1024;
    private const string NOT_FROM_THE_APP = "The upload must be sent by the FuXi app.";

    public static IEndpointRouteBuilder MapLetterboxdEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GET_LETTERBOXD_LIKES, (LetterboxdService service, CancellationToken cancellationToken) =>
            service.GetLikesAsync(cancellationToken));

        // The file is the "file" part of a multipart form. That is a "simple" cross-site request with no preflight and
        // the API has no sign-in, so the app's header is required: only a preflighted (allowed) origin can send it.
        routes.MapPost(ApiRoutes.UPLOAD_LETTERBOXD_LIKES, (HttpRequest request, IFormFile? file, LetterboxdService service, CancellationToken cancellationToken) =>
            request.Headers[APP_HEADER] == APP_HEADER_VALUE
                ? service.SaveLikesAsync(file, cancellationToken)
                : throw ApiException.BadRequest(NOT_FROM_THE_APP))
            .DisableAntiforgery()
            .WithMetadata(new RequestSizeLimitAttribute(MAX_REQUEST_BYTES));

        return routes;
    }
}
