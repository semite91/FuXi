using FuXi.Api.Database;
using FuXi.Api.Tests.Database;
using FuXi.Api.Words;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Time.Testing;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>
/// Starts the API on the database of .env.test. The first use recreates and migrates that database,
/// or skips the calling test when .env.test is missing.
/// </summary>
public sealed class DatabaseApi : IDisposable
{
    private const string MISSING_ORIGINS_REASON =
        $"{TestDatabase.ENV_FILE_NAME} must give {CorsSettings.ORIGINS_KEY} a value; the API does not start without it.";

    private readonly ApiHost host = new();
    private TestDatabase? database;
    private HttpClient? client;

    public FakeTimeProvider Clock => host.Clock;

    public RecordingNotificationTimer Timer => host.Timer;

    public HttpClient Client => client ??= CreateClient();

    private TestDatabase Database => database ??= Recreate();

    /// <summary>Changes the stored state through a context of its own.</summary>
    public void Arrange(Action<FuXiDbContext> arrange)
    {
        using var context = Database.CreateContext();
        arrange(context);
    }

    /// <summary>Changes the stored state and hands back what the test needs from it.</summary>
    public T Arrange<T>(Func<FuXiDbContext, T> arrange)
    {
        using var context = Database.CreateContext();

        return arrange(context);
    }

    /// <summary>Reads the stored state through a new context, so nothing comes from a change tracker.</summary>
    public T Read<T>(Func<FuXiDbContext, T> read) => Arrange(read);

    /// <summary>Calls the internal function the way Phase 4's timed task will.</summary>
    public async Task<IReadOnlyList<NotificationWord>> GetNotificationWordsAsync(DateTimeOffset date)
    {
        using var scope = StartedServices().CreateScope();
        var wordService = scope.ServiceProvider.GetRequiredService<WordService>();

        return await wordService.GetNotificationWordsAsync(date, TestContext.Current.CancellationToken);
    }

    public void Dispose()
    {
        client?.Dispose();
        host.Dispose();
        database?.Dispose();
    }

    private static TestDatabase Recreate()
    {
        var created = new TestDatabase();
        try
        {
            created.RecreateMigrated().Dispose();
        }
        catch
        {
            created.Dispose();
            throw;
        }

        return created;
    }

    // The origins are never guessed: a test database setup without them is a setup mistake.
    private static void RequireCorsOrigins()
    {
        var configuration = new ConfigurationBuilder().AddEnvironmentVariables().Build();

        Assert.False(string.IsNullOrWhiteSpace(configuration[CorsSettings.ORIGINS_KEY]), MISSING_ORIGINS_REASON);
    }

    private HttpClient CreateClient()
    {
        StartedServices();

        return host.CreateApiClient();
    }

    private IServiceProvider StartedServices()
    {
        _ = Database;
        RequireCorsOrigins();

        return host.Services;
    }
}
