namespace FuXi.Api.Words;

/// <summary>Maps the words endpoints to <see cref="WordService"/>.</summary>
public static class WordEndpoints
{
    public static IEndpointRouteBuilder MapWordEndpoints(this IEndpointRouteBuilder routes)
    {
        routes.MapGet(ApiRoutes.GET_CARD_WORDS, (string? wordIds, WordService service, CancellationToken cancellationToken) =>
            service.GetCardWordsAsync(wordIds, cancellationToken));

        routes.MapGet(ApiRoutes.GET_WORDS_BY_ACTIVE, (WordService service, CancellationToken cancellationToken) =>
            service.GetWordsByActiveAsync(cancellationToken));

        routes.MapGet(ApiRoutes.GET_WORD_HISTORY, (Guid wordId, WordService service, CancellationToken cancellationToken) =>
            service.GetWordHistoryAsync(wordId, cancellationToken));

        routes.MapGet(ApiRoutes.GET_WORDS_BY_FILTER, ([AsParameters] WordFilterRequest request, WordService service, CancellationToken cancellationToken) =>
            service.GetWordsByFilterAsync(request, cancellationToken));

        routes.MapPost(ApiRoutes.UPDATE_WORD_CONTENT, async (UpdateWordContentRequest request, WordService service, CancellationToken cancellationToken) =>
        {
            await service.UpdateWordContentAsync(request.Id, request.Content, cancellationToken);
            return TypedResults.NoContent();
        });

        routes.MapPost(ApiRoutes.UPDATE_WORD_KNOWN_STATUS, async (UpdateWordKnownStatusRequest request, WordService service, CancellationToken cancellationToken) =>
        {
            await service.UpdateWordKnownStatusAsync(request.WordId, request.IsKnown, cancellationToken);
            return TypedResults.NoContent();
        });

        routes.MapPost(ApiRoutes.UPDATE_IS_REINFORCEMENT, async (UpdateIsReinforcementRequest request, WordService service, CancellationToken cancellationToken) =>
        {
            await service.UpdateIsReinforcementAsync(request.WordId, request.IsReinforcement, cancellationToken);
            return TypedResults.NoContent();
        });

        return routes;
    }
}
