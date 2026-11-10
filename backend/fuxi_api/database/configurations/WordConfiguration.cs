using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="Word"/> to the Words table.</summary>
public sealed class WordConfiguration : IEntityTypeConfiguration<Word>
{
    public const string TABLE_NAME = "Words";
    private const bool DEFAULT_FLAG = false;
    private const int DEFAULT_COUNT = 0;

    public void Configure(EntityTypeBuilder<Word> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(word => word.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
        builder.Property(word => word.Name).IsRequired();
        builder.Property(word => word.Translation).IsRequired();
        builder.Property(word => word.IsKnown).HasDefaultValue(DEFAULT_FLAG);
        builder.Property(word => word.IsReinforcement).HasDefaultValue(DEFAULT_FLAG);
        builder.Property(word => word.ShownCount).HasDefaultValue(DEFAULT_COUNT);
        builder.Property(word => word.KnownCount).HasDefaultValue(DEFAULT_COUNT);
    }
}
