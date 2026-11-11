namespace FuXi.Api.Configs;

/// <summary>Maps the config endpoints to <see cref="ConfigService"/>.</summary>
public static class ConfigEndpoints
{
    public static IEndpointRouteBuilder MapConfigEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GET_CONFIGS, (ConfigService service, CancellationToken cancellationToken) =>
            service.GetConfigsAsync(cancellationToken));

        routes.MapPost(ApiRoutes.UPDATE_CONFIG, async (UpdateConfigRequest request, ConfigService service, CancellationToken cancellationToken) =>
        {
            await service.UpdateConfigAsync(request.Id, request.Value, cancellationToken);
            return TypedResults.NoContent();
        });

        routes.MapPost(ApiRoutes.UPDATE_NOTIFICATION_PERIOD, async (UpdateConfigRequest request, ConfigService service, CancellationToken cancellationToken) =>
        {
            await service.UpdateNotificationPeriodAsync(request.Id, request.Value, cancellationToken);
            return TypedResults.NoContent();
        });

        return routes;
    }
}
