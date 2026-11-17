using FluentAssertions;

namespace FuXi.Api.Tests.Database;

/// <summary>The migrations and tables the database tests expect, kept in one place.</summary>
public static class ExpectedSchema
{
    public const string INITIAL_MIGRATION_SUFFIX = "_Initial";
    public const string ADD_SETTINGS_MIGRATION_SUFFIX = "_AddSettings";
    public const string SETTINGS_TABLE = "Settings";

    /// <summary>Migration id suffixes in the order they are applied.</summary>
    public static readonly string[] MIGRATION_SUFFIXES = [INITIAL_MIGRATION_SUFFIX, ADD_SETTINGS_MIGRATION_SUFFIX];

    public static readonly string[] TABLE_NAMES =
        ["Words", "RotatedWords", "Config", "WordHistory", "Schedule", "PushSubscription", SETTINGS_TABLE];

    /// <summary>The tables the Initial migration created, before Settings was added.</summary>
    public static readonly string[] INITIAL_TABLE_NAMES = TABLE_NAMES.Where(table => table != SETTINGS_TABLE).ToArray();

    /// <summary>Sorts the migration ids ordinally and checks they end with the expected suffixes, in order.</summary>
    public static void ShouldMatchMigrationSuffixes(IEnumerable<string> migrationIds)
    {
        var orderedIds = migrationIds.Order(StringComparer.Ordinal).ToList();

        orderedIds.Should().HaveCount(MIGRATION_SUFFIXES.Length);
        orderedIds.Zip(MIGRATION_SUFFIXES).Should()
            .OnlyContain(pair => pair.First.EndsWith(pair.Second, StringComparison.Ordinal));
    }
}
