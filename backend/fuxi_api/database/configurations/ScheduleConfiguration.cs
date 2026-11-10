using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="Schedule"/> to the Schedule table.</summary>
public sealed class ScheduleConfiguration : IEntityTypeConfiguration<Schedule>
{
    public const string TABLE_NAME = "Schedule";
    public const string END_DATE_AFTER_START_DATE_CHECK = "CK_Schedule_EndDate_After_StartDate";
    private const string END_DATE_AFTER_START_DATE_SQL = "\"EndDate\" > \"StartDate\"";

    public void Configure(EntityTypeBuilder<Schedule> builder)
    {
        builder.ToTable(TABLE_NAME, table =>
            table.HasCheckConstraint(END_DATE_AFTER_START_DATE_CHECK, END_DATE_AFTER_START_DATE_SQL));
        builder.Property(schedule => schedule.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
    }
}
