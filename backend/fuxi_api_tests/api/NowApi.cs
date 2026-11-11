using FuXi.Api.Database;
using FuXi.Api.Push;

namespace FuXi.Api.Tests.Api;

/// <summary>
/// Starts the API without a database. The startup values come from a temporary env file,
/// so a developer's real .env is never loaded. Every changed variable is restored on dispose.
/// </summary>
public sealed class NowApi(NowApiSettings? settings = null) : IDisposable
{
    // Nothing listens on this port, so a query that reaches the database fails fast.
    private const string UNREACHABLE_HOST = "127.0.0.1";
    private const string UNREACHABLE_PORT = "1";
    private const string DATABASE_NAME = "fuxi_now_test";
    private const string DATABASE_USER = "fuxi_now";
    private const string DATABASE_PASSWORD = "not-a-secret";
    private const string ENV_FILE_EXTENSION = ".env";
    private const char ASSIGNMENT = '=';
    private static readonly string[] MANAGED_VARIABLES =
    [
        EnvironmentFile.PATH_VARIABLE,
        DatabaseSettings.HOST_KEY,
        DatabaseSettings.PORT_KEY,
        DatabaseSettings.NAME_KEY,
        DatabaseSettings.USER_KEY,
        DatabaseSettings.PASSWORD_KEY,
        CorsSettings.ORIGINS_KEY,
        DatabaseMigration.ENABLED_KEY,
        VapidSettings.PUBLIC_KEY_KEY,
        VapidSettings.PRIVATE_KEY_KEY,
    ];

    private readonly NowApiSettings settings = settings ?? new NowApiSettings();
    private readonly string envFilePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid()}{ENV_FILE_EXTENSION}");
    private EnvironmentScope? environment;
    private ApiHost? host;
    private HttpClient? client;

    public ApiHost Host => host ??= Start();

    public HttpClient Client => client ??= Host.CreateApiClient();

    public IServiceProvider Services => Host.Services;

    /// <summary>Starts the API. Throws what the startup throws.</summary>
    public ApiHost Start()
    {
        PrepareEnvironment();
        var created = new ApiHost(settings.ReplacesServices);
        try
        {
            // Reading the services runs Program up to the built application.
            _ = created.Services;
        }
        catch
        {
            created.Dispose();
            throw;
        }

        return created;
    }

    public void Dispose()
    {
        client?.Dispose();
        host?.Dispose();
        environment?.Dispose();
        File.Delete(envFilePath);
    }

    private void PrepareEnvironment()
    {
        environment ??= new EnvironmentScope(MANAGED_VARIABLES);
        foreach (var name in MANAGED_VARIABLES)
        {
            Environment.SetEnvironmentVariable(name, null);
        }

        File.WriteAllLines(envFilePath, EnvFileLines());
        Environment.SetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE, envFilePath);
    }

    private IEnumerable<string> EnvFileLines() =>
        StartupValues()
            .Where(pair => pair.Value is not null)
            .Select(pair => $"{pair.Key}{ASSIGNMENT}{pair.Value}");

    private Dictionary<string, string?> StartupValues() => new()
    {
        [DatabaseSettings.HOST_KEY] = UNREACHABLE_HOST,
        [DatabaseSettings.PORT_KEY] = UNREACHABLE_PORT,
        [DatabaseSettings.NAME_KEY] = DATABASE_NAME,
        [DatabaseSettings.USER_KEY] = DATABASE_USER,
        [DatabaseSettings.PASSWORD_KEY] = DATABASE_PASSWORD,
        [CorsSettings.ORIGINS_KEY] = settings.CorsOrigins,
        [DatabaseMigration.ENABLED_KEY] = settings.MigrateAtStartup,
        [VapidSettings.PUBLIC_KEY_KEY] = settings.VapidPublicKey,
        [VapidSettings.PRIVATE_KEY_KEY] = settings.VapidPrivateKey,
    };
}
