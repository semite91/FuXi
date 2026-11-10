using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="RotatedWord"/> to the RotatedWords table.</summary>
public sealed class RotatedWordConfiguration : IEntityTypeConfiguration<RotatedWord>
{
    public const string TABLE_NAME = "RotatedWords";
    private const int DEFAULT_COUNTER = 1;

    public void Configure(EntityTypeBuilder<RotatedWord> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(rotatedWord => rotatedWord.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
        builder.Property(rotatedWord => rotatedWord.Counter).HasDefaultValue(DEFAULT_COUNTER);
        builder.HasIndex(rotatedWord => rotatedWord.WordId).IsUnique();
        builder.HasOne<Word>()
            .WithMany()
            .HasForeignKey(rotatedWord => rotatedWord.WordId)
            .IsRequired()
            .OnDelete(DeleteBehavior.Cascade);
    }
}
