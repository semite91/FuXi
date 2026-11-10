using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="PushSubscription"/> to the PushSubscription table.</summary>
public sealed class PushSubscriptionConfiguration : IEntityTypeConfiguration<PushSubscription>
{
    public const string TABLE_NAME = "PushSubscription";

    public void Configure(EntityTypeBuilder<PushSubscription> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(subscription => subscription.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
    }
}
