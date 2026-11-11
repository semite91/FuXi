using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Database;

/// <summary>Registers the FuXi database in the service container.</summary>
public static class DatabaseRegistration
{
    /// <summary>Registers the database for a known connection string. Tests and tools use it; the API startup uses the overload below.</summary>
    public static IServiceCollection AddFuXiDatabase(this IServiceCollection services, string connectionString) =>
        services.AddDbContext<FuXiDbContext>(options => options.UseNpgsql(connectionString));

    /// <summary>Registers the database with the connection string built from the final configuration.</summary>
    public static IServiceCollection AddFuXiDatabase(this IServiceCollection services) =>
        services.AddDbContext<FuXiDbContext>(
            (provider, options) => options.UseNpgsql(
                DatabaseSettings.BuildConnectionString(provider.GetRequiredService<IConfiguration>())),
            optionsLifetime: ServiceLifetime.Singleton);
}
