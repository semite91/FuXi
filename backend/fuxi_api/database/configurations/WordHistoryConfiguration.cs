using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="WordHistory"/> to the WordHistory table.</summary>
public sealed class WordHistoryConfiguration : IEntityTypeConfiguration<WordHistory>
{
    public const string TABLE_NAME = "WordHistory";

    public void Configure(EntityTypeBuilder<WordHistory> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(history => history.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
        builder.HasOne<Word>()
            .WithMany()
            .HasForeignKey(history => history.WordId)
            .IsRequired()
            .OnDelete(DeleteBehavior.Cascade);
    }
}
