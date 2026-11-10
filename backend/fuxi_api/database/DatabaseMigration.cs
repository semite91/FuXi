using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Database;

/// <summary>Brings the database up to the latest migration at startup.</summary>
public static class DatabaseMigration
{
    public static void Apply(IServiceProvider services)
    {
        using var scope = services.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<FuXiDbContext>();
        context.Database.Migrate();
    }
}
