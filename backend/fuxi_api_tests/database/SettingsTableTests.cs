using System.Globalization;
using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql;
using Xunit;

namespace FuXi.Api.Tests.Database;

/// <summary>Checks the app-wide Settings table against the PostgreSQL test database.</summary>
// Shares the smoke tests' collection: both change process-wide environment variables.
[Collection(nameof(SmokeTests))]
public sealed class SettingsTableTests : IDisposable
{
    private const string UNIQUE_VIOLATION = "23505";
    private const string ID_COLUMN = "Id";
    private const string UUID_TYPE = "uuid";
    private const string TEXT_TYPE = "text";
    private const string NOT_NULLABLE = "NO";
    private const string SETTING_CODE = "TestCode";
    private const string SETTING_VALUE = "TestValue";
    private const string OTHER_VALUE = "OtherValue";
    private const string WORD_NAME = "apple";
    private const string WORD_TRANSLATION = "elma";
    private const string CHANGED_CONFIG_VALUE = "35";
    private const string PUSH_ENDPOINT = "https://push.example.test/endpoint";
    private const string PUSH_P256DH = "p256dh-key";
    private const string PUSH_AUTH = "auth-key";
    private const string UTC_DATE = "2026-11-16T06:20:00+00:00";
    private const string LATER_UTC_DATE = "2026-11-16T07:20:00+00:00";

    private const string COLUMNS_SQL =
        "SELECT column_name AS \"Name\", data_type AS \"Type\", is_nullable AS \"IsNullable\" " +
        "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = {0}";
    private const string PRIMARY_KEY_COLUMNS_SQL =
        "SELECT kcu.column_name AS \"Value\" FROM information_schema.table_constraints tc " +
        "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema " +
        "WHERE tc.table_schema = 'public' AND tc.table_name = {0} AND tc.constraint_type = 'PRIMARY KEY'";
    private const string ROWS_AS_JSON_SQL = "SELECT row_to_json(t)::text AS \"Value\" FROM \"{0}\" t ORDER BY t.\"Id\"";

    private readonly TestDatabase database = new();

    [Fact]
    public void SettingsTableHasExpectedColumns()
    {
        // F1
        using var context = database.RecreateMigrated();

        ColumnsOf(context, ExpectedSchema.SETTINGS_TABLE).Should().BeEquivalentTo(
        [
            new TableColumn { Name = ID_COLUMN, Type = UUID_TYPE, IsNullable = NOT_NULLABLE },
            new TableColumn { Name = nameof(Setting.Code), Type = TEXT_TYPE, IsNullable = NOT_NULLABLE },
            new TableColumn { Name = nameof(Setting.Value), Type = TEXT_TYPE, IsNullable = NOT_NULLABLE },
        ]);
        context.Database.SqlQueryRaw<string>(PRIMARY_KEY_COLUMNS_SQL, ExpectedSchema.SETTINGS_TABLE).ToList()
            .Should().ContainSingle().Which.Should().Be(ID_COLUMN);
    }

    [Fact]
    public void AddedSettingIsReadBackByCode()
    {
        // F2
        using (var writeContext = database.RecreateMigrated())
        {
            writeContext.Settings.Add(new Setting { Code = SETTING_CODE, Value = SETTING_VALUE });
            writeContext.SaveChanges();
        }

        using var readContext = database.CreateContext();
        var setting = readContext.Settings.AsNoTracking().Single(stored => stored.Code == SETTING_CODE);

        setting.Id.Should().NotBe(Guid.Empty);
        setting.Value.Should().Be(SETTING_VALUE);
    }

    [Fact]
    public void SettingWithExistingCodeIsRejected()
    {
        // F3
        using var context = database.RecreateMigrated();
        context.Settings.Add(new Setting { Code = SETTING_CODE, Value = SETTING_VALUE });
        context.SaveChanges();
        context.Settings.Add(new Setting { Code = SETTING_CODE, Value = OTHER_VALUE });

        var save = () => context.SaveChanges();

        save.Should().Throw<DbUpdateException>()
            .WithInnerException<PostgresException>()
            .Which.SqlState.Should().Be(UNIQUE_VIOLATION);
    }

    [Fact]
    public void NewDatabaseHasNoSetting()
    {
        // F4
        using var context = database.RecreateMigrated();

        context.Settings.Should().BeEmpty();
    }

    [Fact]
    public void ExistingTablesKeepTheirColumnsAcrossMigration()
    {
        // F5
        using var context = MigrateToInitial();
        var columnsBefore = ExpectedSchema.INITIAL_TABLE_NAMES.ToDictionary(table => table, table => ColumnsOf(context, table));

        context.Database.Migrate();

        foreach (var table in ExpectedSchema.INITIAL_TABLE_NAMES)
        {
            columnsBefore[table].Should().NotBeEmpty();
            ColumnsOf(context, table).Should().BeEquivalentTo(columnsBefore[table]);
        }
    }

    [Fact]
    public void ExistingTablesKeepTheirDataAcrossMigration()
    {
        // F5
        using var context = MigrateToInitial();
        AddRowToEveryExistingTable(context);
        var rowsBefore = ExpectedSchema.INITIAL_TABLE_NAMES.ToDictionary(table => table, table => RowsOf(context, table));

        context.Database.Migrate();

        foreach (var table in ExpectedSchema.INITIAL_TABLE_NAMES)
        {
            rowsBefore[table].Should().NotBeEmpty();
            RowsOf(context, table).Should().Equal(rowsBefore[table]);
        }
    }

    public void Dispose() => database.Dispose();

    private FuXiDbContext MigrateToInitial()
    {
        database.RecreateEmpty();
        var context = database.CreateContext();
        var initialMigration = context.GetService<IMigrationsAssembly>().Migrations.Keys
            .Single(id => id.EndsWith(ExpectedSchema.INITIAL_MIGRATION_SUFFIX, StringComparison.Ordinal));
        context.GetService<IMigrator>().Migrate(initialMigration);

        return context;
    }

    private static void AddRowToEveryExistingTable(FuXiDbContext context)
    {
        var word = new Word { Name = WORD_NAME, Translation = WORD_TRANSLATION };
        context.Words.Add(word);
        context.SaveChanges();

        var date = ParseDate(UTC_DATE);
        context.RotatedWords.Add(new RotatedWord { WordId = word.Id, LastShownDate = date });
        context.WordHistories.Add(new WordHistory { WordId = word.Id, IsKnown = true, Date = date });
        context.Schedules.Add(new Schedule { StartDate = date, EndDate = ParseDate(LATER_UTC_DATE) });
        context.PushSubscriptions.Add(
            new PushSubscription { Endpoint = PUSH_ENDPOINT, P256dh = PUSH_P256DH, Auth = PUSH_AUTH, CreatedDate = date });
        context.SaveChanges();

        context.Configs.ExecuteUpdate(setters => setters.SetProperty(config => config.Value, CHANGED_CONFIG_VALUE));
    }

    private static DateTimeOffset ParseDate(string value) => DateTimeOffset.Parse(value, CultureInfo.InvariantCulture);

    private static List<TableColumn> ColumnsOf(FuXiDbContext context, string table) =>
        context.Database.SqlQueryRaw<TableColumn>(COLUMNS_SQL, table).ToList();

    // The table name comes from the constant list above, never from input.
    private static List<string> RowsOf(FuXiDbContext context, string table) =>
        context.Database.SqlQueryRaw<string>(string.Format(CultureInfo.InvariantCulture, ROWS_AS_JSON_SQL, table)).ToList();

    private sealed record TableColumn
    {
        public required string Name { get; init; }

        public required string Type { get; init; }

        public required string IsNullable { get; init; }
    }
}
