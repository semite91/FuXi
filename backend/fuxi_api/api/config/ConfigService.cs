using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Configs;

/// <summary>The settings logic behind the config endpoints.</summary>
public sealed class ConfigService(FuXiDbContext database, INotificationTimer notificationTimer)
{
    private const string VALUE_MISSING = "value is missing or empty.";
    private const string VALUE_INVALID = "value does not fit the input type of the setting.";
    private const string CONFIG_NOT_FOUND = "The setting was not found.";
    private const string NOT_NOTIFICATION_PERIOD = "The setting is not the Notification Period.";
    private const string IS_NOTIFICATION_PERIOD = "The Notification Period is changed with UpdateNotificationPeriod.";

    /// <summary>Returns every setting.</summary>
    public async Task<IReadOnlyList<ConfigItem>> GetConfigsAsync(CancellationToken cancellationToken) =>
        await database.Configs.AsNoTracking()
            .OrderBy(config => config.Code)
            .Select(config => new ConfigItem(config.Id, config.Code, config.Name, config.Value, config.InputType))
            .ToListAsync(cancellationToken);

    /// <summary>Replaces the value of a setting when it fits the input type of the setting. The Notification Period is refused.</summary>
    public async Task UpdateConfigAsync(Guid id, string? value, CancellationToken cancellationToken)
    {
        var newValue = RequireValue(value);
        var config = await FindConfigAsync(id, cancellationToken);
        if (config.Code == ConfigCodes.NOTIFICATION_PERIOD)
        {
            throw ApiException.BadRequest(IS_NOTIFICATION_PERIOD);
        }

        if (!ConfigValue.IsValid(config.InputType, newValue))
        {
            throw ApiException.BadRequest(VALUE_INVALID);
        }

        config.Value = newValue;
        await database.SaveChangesAsync(cancellationToken);
    }

    /// <summary>Saves the Notification Period, then restarts the notification timer with it.</summary>
    public async Task UpdateNotificationPeriodAsync(Guid id, string? value, CancellationToken cancellationToken)
    {
        var newValue = RequireValue(value);
        var config = await FindConfigAsync(id, cancellationToken);
        if (config.Code != ConfigCodes.NOTIFICATION_PERIOD)
        {
            throw ApiException.BadRequest(NOT_NOTIFICATION_PERIOD);
        }

        // The period is always minutes, so it is checked as a number.
        if (!ConfigValue.TryParseNumber(newValue, out var minutes))
        {
            throw ApiException.BadRequest(VALUE_INVALID);
        }

        config.Value = newValue;
        await database.SaveChangesAsync(cancellationToken);

        // The value is stored, so a client that disconnects now must not cancel the restart.
        await notificationTimer.RestartAsync(TimeSpan.FromMinutes(minutes), CancellationToken.None);
    }

    private async Task<Config> FindConfigAsync(Guid id, CancellationToken cancellationToken) =>
        await database.Configs.SingleOrDefaultAsync(config => config.Id == id, cancellationToken)
            ?? throw ApiException.NotFound(CONFIG_NOT_FOUND);

    // An empty value is rejected before the database is used.
    private static string RequireValue(string? value) =>
        string.IsNullOrWhiteSpace(value) ? throw ApiException.BadRequest(VALUE_MISSING) : value;
}
