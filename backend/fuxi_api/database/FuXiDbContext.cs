using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Database;

/// <summary>The FuXi PostgreSQL database.</summary>
public sealed class FuXiDbContext(DbContextOptions<FuXiDbContext> options) : DbContext(options)
{
    public DbSet<Word> Words => Set<Word>();

    public DbSet<RotatedWord> RotatedWords => Set<RotatedWord>();

    public DbSet<Config> Configs => Set<Config>();

    public DbSet<WordHistory> WordHistories => Set<WordHistory>();

    public DbSet<Schedule> Schedules => Set<Schedule>();

    public DbSet<PushSubscription> PushSubscriptions => Set<PushSubscription>();

    protected override void OnModelCreating(ModelBuilder modelBuilder) =>
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(FuXiDbContext).Assembly);

    // Every DateTimeOffset is saved in UTC so a non-zero offset keeps the same instant.
    protected override void ConfigureConventions(ModelConfigurationBuilder configurationBuilder) =>
        configurationBuilder.Properties<DateTimeOffset>().HaveConversion<UtcDateTimeOffsetConverter>();
}
