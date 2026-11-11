using FuXi.Api.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using Xunit;

namespace FuXi.Api.Tests.Database;

/// <summary>
/// Points the tests at the database named in the repository-root .env.test.
/// Skips the calling test when that file is missing and restores every changed variable on dispose.
/// </summary>
public sealed class TestDatabase : IDisposable
{
    public const string ENV_FILE_NAME = ".env.test";
    public const string TEST_DATABASE_SUFFIX = "_test";
    private const string MISSING_ENV_FILE_REASON =
        "Repository-root .env.test is missing, so PostgreSQL tests are skipped (PostgreSQL todo on issue #3).";

    private readonly EnvironmentScope environment = new([EnvironmentFile.PATH_VARIABLE]);
    private readonly string envFilePath = RepositoryRoot.Combine(ENV_FILE_NAME);
    private readonly string? connectionString;

    public TestDatabase()
    {
        if (!File.Exists(envFilePath))
        {
            return;
        }

        environment.RememberKeysOf(envFilePath);
        try
        {
            connectionString = LoadTestConnectionString();
        }
        catch
        {
            // xUnit never disposes an instance whose constructor threw.
            environment.Dispose();
            throw;
        }
    }

    public string EnvFilePath => envFilePath;

    public string ConnectionString
    {
        get
        {
            Assert.SkipWhen(connectionString is null, MISSING_ENV_FILE_REASON);
            return connectionString!;
        }
    }

    /// <summary>Drops the database so the next migration starts from nothing (J3).</summary>
    public void RecreateEmpty()
    {
        using var context = CreateContext();
        context.Database.EnsureDeleted();
    }

    /// <summary>Drops the database and applies every migration (J3).</summary>
    public FuXiDbContext RecreateMigrated()
    {
        RecreateEmpty();
        var context = CreateContext();
        try
        {
            context.Database.Migrate();
        }
        catch
        {
            context.Dispose();
            throw;
        }

        return context;
    }

    public FuXiDbContext CreateContext()
    {
        var options = new DbContextOptionsBuilder<FuXiDbContext>().UseNpgsql(ConnectionString).Options;

        return new FuXiDbContext(options);
    }

    /// <summary>
    /// Builds a container that holds only the database, registered for the test connection string.
    /// The API startup registers more and builds its connection string from the configuration.
    /// </summary>
    public ServiceProvider CreateServices()
    {
        var services = new ServiceCollection();
        services.AddFuXiDatabase(ConnectionString);

        return services.BuildServiceProvider();
    }

    public void Dispose() => environment.Dispose();

    private string LoadTestConnectionString()
    {
        // J2
        Environment.SetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE, envFilePath);
        EnvironmentFile.Load();
        var configuration = new ConfigurationBuilder().AddEnvironmentVariables().Build();

        return RequireTestDatabase(DatabaseSettings.BuildConnectionString(configuration));
    }

    // J1: never touch a database that is not explicitly a test database.
    private static string RequireTestDatabase(string databaseConnection)
    {
        var databaseName = new NpgsqlConnectionStringBuilder(databaseConnection).Database;

        return databaseName is not null && databaseName.EndsWith(TEST_DATABASE_SUFFIX, StringComparison.Ordinal)
            ? databaseConnection
            : throw new InvalidOperationException(
                $"{DatabaseSettings.NAME_KEY} must end with {TEST_DATABASE_SUFFIX}; refusing to use '{databaseName}'.");
    }
}
