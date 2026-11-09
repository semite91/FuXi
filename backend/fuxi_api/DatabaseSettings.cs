using Npgsql;

namespace FuXi.Api;

/// <summary>Builds the PostgreSQL connection string from configuration.</summary>
public static class DatabaseSettings
{
    public const string HOST_KEY = "FUXI_DB_HOST";
    public const string PORT_KEY = "FUXI_DB_PORT";
    public const string NAME_KEY = "FUXI_DB_NAME";
    public const string USER_KEY = "FUXI_DB_USER";
    public const string PASSWORD_KEY = "FUXI_DB_PASSWORD";

    public static string BuildConnectionString(IConfiguration configuration)
    {
        var builder = new NpgsqlConnectionStringBuilder
        {
            Host = Require(configuration, HOST_KEY),
            Port = RequirePort(configuration),
            Database = Require(configuration, NAME_KEY),
            Username = Require(configuration, USER_KEY),
            Password = Require(configuration, PASSWORD_KEY),
        };

        return builder.ConnectionString;
    }

    private static int RequirePort(IConfiguration configuration)
    {
        var value = Require(configuration, PORT_KEY);

        return int.TryParse(value, out var port)
            ? port
            : throw new InvalidOperationException($"Configuration value {PORT_KEY} is not a number.");
    }

    private static string Require(IConfiguration configuration, string key)
    {
        var value = configuration[key];

        return string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"Configuration value {key} is missing.")
            : value;
    }
}
