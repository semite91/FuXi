using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace FuXi.Api.Database.Configurations;

/// <summary>Maps <see cref="Config"/> to the Config table and seeds the default settings.</summary>
public sealed class ConfigConfiguration : IEntityTypeConfiguration<Config>
{
    public const string TABLE_NAME = "Config";
    private const string TEXT_COLUMN_TYPE = "text";

    // Fixed ids keep the seed stable across migrations.
    private const string ROTATION_COUNT_ID = "6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e01";
    private const string ROTATION_PERIOD_ID = "6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e02";
    private const string REINFORCEMENT_PERIOD_ID = "6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e03";
    private const string NOTIFICATION_PERIOD_ID = "6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e04";

    private const string ROTATION_COUNT_NAME = "Rotation Count";
    private const string ROTATION_PERIOD_NAME = "Rotation period";
    private const string REINFORCEMENT_PERIOD_NAME = "Reinforcement period";
    private const string NOTIFICATION_PERIOD_NAME = "Notification period";

    private const string ROTATION_COUNT_VALUE = "20";
    private const string ROTATION_PERIOD_VALUE = "15";
    private const string REINFORCEMENT_PERIOD_VALUE = "10800";
    private const string NOTIFICATION_PERIOD_VALUE = "15";

    public void Configure(EntityTypeBuilder<Config> builder)
    {
        builder.ToTable(TABLE_NAME);
        builder.Property(config => config.Id).HasDefaultValueSql(ColumnDefaults.UUID_DEFAULT_SQL);
        builder.Property(config => config.InputType).HasConversion<string>().HasColumnType(TEXT_COLUMN_TYPE);
        builder.HasIndex(config => config.Code).IsUnique();
        builder.HasData(SeedRows());
    }

    private static Config[] SeedRows() =>
    [
        NumberSetting(ROTATION_COUNT_ID, ROTATION_COUNT_NAME, ConfigCodes.ROTATION_COUNT, ROTATION_COUNT_VALUE),
        NumberSetting(ROTATION_PERIOD_ID, ROTATION_PERIOD_NAME, ConfigCodes.ROTATION_PERIOD, ROTATION_PERIOD_VALUE),
        NumberSetting(REINFORCEMENT_PERIOD_ID, REINFORCEMENT_PERIOD_NAME, ConfigCodes.REINFORCEMENT_PERIOD, REINFORCEMENT_PERIOD_VALUE),
        NumberSetting(NOTIFICATION_PERIOD_ID, NOTIFICATION_PERIOD_NAME, ConfigCodes.NOTIFICATION_PERIOD, NOTIFICATION_PERIOD_VALUE),
    ];

    private static Config NumberSetting(string id, string name, string code, string value) =>
        new() { Id = Guid.Parse(id), Name = name, Code = code, Value = value, InputType = InputType.Number };
}
