using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="Setting"/> to the Settings table. It has no seed row.</summary>
public sealed class SettingConfiguration : IEntityTypeConfiguration<Setting>
{
    public const string TABLE_NAME = "Settings";

    public void Configure(EntityTypeBuilder<Setting> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(setting => setting.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
        builder.HasIndex(setting => setting.Code).IsUnique();
    }
}
