namespace FuXi.Api.Push;

/// <summary>Maps the push endpoints to <see cref="PushService"/>.</summary>
public static class PushEndpoints
{
    public static IEndpointRouteBuilder MapPushEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GET_VAPID_PUBLIC_KEY, (PushService service) => service.GetVapidPublicKey());

        routes.MapPost(ApiRoutes.SAVE_PUSH_SUBSCRIPTION, async (SavePushSubscriptionRequest request, PushService service, CancellationToken cancellationToken) =>
        {
            await service.SavePushSubscriptionAsync(request, cancellationToken);
            return TypedResults.Ok();
        });

        return routes;
    }
}
