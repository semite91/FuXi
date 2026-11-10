using FuXi.Api.Database;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Tests.Database;

/// <summary>Creates a context for model and migration metadata. It never opens a connection.</summary>
public static class ModelOnlyContext
{
    private const string CONNECTION_STRING = "Host=localhost;Database=fuxi_model_only";

    public static FuXiDbContext Create()
    {
        var options = new DbContextOptionsBuilder<FuXiDbContext>().UseNpgsql(CONNECTION_STRING).Options;

        return new FuXiDbContext(options);
    }
}
