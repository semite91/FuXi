namespace FuXi.Api.Words;

/// <summary>The Word and Rotation logic behind the words endpoints.</summary>
public sealed class WordService
{
    /// <summary>Tops up the Rotation, then returns the Words that are Due at the given date.</summary>
    public Task<IReadOnlyList<NotificationWord>> GetNotificationWordsAsync(DateTimeOffset date, CancellationToken cancellationToken) =>
        throw new NotImplementedException();
}
