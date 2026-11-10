using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace FuXi.Api.Database;

/// <summary>
/// Used only by "dotnet ef". With an env file it targets the configured database, so database update,
/// migrations list and migrations remove work. Without one it uses a placeholder, so migrations add
/// needs no .env; commands that connect will fail against the placeholder.
/// </summary>
public sealed class FuXiDbContextFactory : IDesignTimeDbContextFactory<FuXiDbContext>
{
    private const string PLACEHOLDER_CONNECTION_STRING = "Host=localhost;Database=fuxi_design_time";

    public FuXiDbContext CreateDbContext(string[] args)
    {
        var options = new DbContextOptionsBuilder<FuXiDbContext>().UseNpgsql(ConnectionString()).Options;

        return new FuXiDbContext(options);
    }

    private static string ConnectionString()
    {
        if (!EnvironmentFile.IsAvailable())
        {
            return PLACEHOLDER_CONNECTION_STRING;
        }

        EnvironmentFile.Load();
        var configuration = new ConfigurationBuilder().AddEnvironmentVariables().Build();

        return DatabaseSettings.BuildConnectionString(configuration);
    }
}
