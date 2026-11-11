namespace FuXi.Api.Tests.Api;

/// <summary>Reads the exception a failed startup threw.</summary>
public static class StartupFailure
{
    /// <summary>The exception and every exception inside it.</summary>
    public static IEnumerable<Exception> Chain(Exception exception)
    {
        yield return exception;

        var inner = exception is AggregateException aggregate
            ? aggregate.InnerExceptions
            : exception.InnerException is null ? [] : [exception.InnerException];
        foreach (var nested in inner.SelectMany(Chain))
        {
            yield return nested;
        }
    }
}
