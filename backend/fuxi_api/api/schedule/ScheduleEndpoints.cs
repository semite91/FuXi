namespace FuXi.Api.Schedules;

/// <summary>Maps the schedule endpoints to <see cref="ScheduleService"/>.</summary>
public static class ScheduleEndpoints
{
    public static IEndpointRouteBuilder MapScheduleEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GET_SCHEDULE, (string[]? period, ScheduleService service, CancellationToken cancellationToken) =>
            service.GetScheduleAsync(period, cancellationToken));

        routes.MapPost(ApiRoutes.UPDATE_SCHEDULE, (UpdateScheduleRequest request, ScheduleService service, CancellationToken cancellationToken) =>
            service.UpdateScheduleAsync(request, cancellationToken));

        routes.MapDelete(ApiRoutes.DELETE_SCHEDULE, async (Guid id, ScheduleService service, CancellationToken cancellationToken) =>
        {
            await service.DeleteScheduleAsync(id, cancellationToken);
            return TypedResults.NoContent();
        });

        return routes;
    }
}
