namespace FuXi.Api.Notion;

/// <summary>Maps the Notion endpoints to <see cref="NotionService"/>.</summary>
public static class NotionEndpoints
{
    public static IEndpointRouteBuilder MapNotionEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.NOTION_CONNECT, (NotionService service) => TypedResults.Redirect(service.StartSignIn()));

        // Notion sends the Learner's browser here with code and state, or with error and state.
        routes.MapGet(ApiRoutes.NOTION_CALLBACK, async (string? code, string? state, string? error, NotionService service, CancellationToken cancellationToken) =>
            TypedResults.Redirect(await service.HandleCallbackAsync(code, state, error, cancellationToken)));

        routes.MapGet(ApiRoutes.GET_NOTION_CONNECTION, (NotionService service, CancellationToken cancellationToken) =>
            service.GetConnectionAsync(cancellationToken));

        return routes;
    }
}
