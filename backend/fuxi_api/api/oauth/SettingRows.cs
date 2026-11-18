using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.OAuth;

/// <summary>Reads and writes Settings rows by their Code.</summary>
public static class SettingRows
{
    /// <summary>The values of these codes; a code without a row is missing from the result.</summary>
    public static Task<Dictionary<string, string>> ReadAsync(FuXiDbContext database, IReadOnlyCollection<string> codes, CancellationToken cancellationToken) =>
        database.Settings.AsNoTracking()
            .Where(setting => codes.Contains(setting.Code))
            .ToDictionaryAsync(setting => setting.Code, setting => setting.Value, cancellationToken);

    /// <summary>
    /// Updates each row in place, or adds it. One SaveChanges is one transaction: the rows are written together or
    /// not at all. When another request adds the same row first, the unique code stops the save, and the save is
    /// tried once more, now updating that row.
    /// </summary>
    public static async Task SaveAsync(FuXiDbContext database, IReadOnlyDictionary<string, string> values, CancellationToken cancellationToken)
    {
        try
        {
            await SaveOnceAsync(database, values, cancellationToken);
        }
        catch (DbUpdateException)
        {
            database.ChangeTracker.Clear();
            await SaveOnceAsync(database, values, cancellationToken);
        }
    }

    private static async Task SaveOnceAsync(FuXiDbContext database, IReadOnlyDictionary<string, string> values, CancellationToken cancellationToken)
    {
        var codes = values.Keys.ToList();
        var existing = await database.Settings
            .Where(setting => codes.Contains(setting.Code))
            .ToDictionaryAsync(setting => setting.Code, cancellationToken);

        foreach (var (code, value) in values)
        {
            if (existing.TryGetValue(code, out var setting))
            {
                setting.Value = value;
            }
            else
            {
                database.Settings.Add(new Setting { Code = code, Value = value });
            }
        }

        await database.SaveChangesAsync(cancellationToken);
    }
}
