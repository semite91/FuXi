using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Database;

/// <summary>Registers the FuXi database in the service container.</summary>
public static class DatabaseRegistration
{
    public static IServiceCollection AddFuXiDatabase(this IServiceCollection services, string connectionString) =>
        services.AddDbContext<FuXiDbContext>(options => options.UseNpgsql(connectionString));
}
