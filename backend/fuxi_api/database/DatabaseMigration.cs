using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Database;

/// <summary>Brings the database up to the latest migration at startup.</summary>
public static class DatabaseMigration
{
    /// <summary>Set this configuration value to false to start without migrating. Tests without a database use it.</summary>
    public const string ENABLED_KEY = "FUXI_DB_MIGRATE_AT_STARTUP";

    /// <summary>True unless the configuration switches the startup migration off.</summary>
    public static bool IsEnabled(IConfiguration configuration) =>
        !string.Equals(configuration[ENABLED_KEY], bool.FalseString, StringComparison.OrdinalIgnoreCase);

    public static void Apply(IServiceProvider services)
    {
        using var scope = services.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<FuXiDbContext>();
        context.Database.Migrate();
    }
}
