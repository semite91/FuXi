using System.Globalization;
using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using Xunit;

namespace FuXi.Api.Tests.Database;

// Shares the smoke tests' collection: both change process-wide environment variables.
[Collection(nameof(SmokeTests))]
public sealed class DatabaseTests : IDisposable
{
    private const string FOREIGN_KEY_VIOLATION = "23503";
    private const string UNIQUE_VIOLATION = "23505";
    private const string CHECK_VIOLATION = "23514";
    private const string INITIAL_MIGRATION_SUFFIX = "_Initial";
    private const string WORD_NAME = "apple";
    private const string WORD_TRANSLATION = "elma";
    private const string SEEDED_CODE = "RotationCount";
    private const string CHANGED_VALUE = "35";
    private const string TEST_CODE_PREFIX = "Test";
    private const string TEST_VALUE = "1";
    private const int SEED_ROW_COUNT = 4;
    private const int DEFAULT_COUNTER = 1;
    private const int DEFAULT_COUNT = 0;
    private const int OVERLAPPING_WINDOW_COUNT = 2;
    private const int DUPLICATE_WORD_COUNT = 2;
    private const int INSERTED_ROW_COUNT = 1;
    private const string UTC_DATE = "2026-11-10T08:18:00+00:00";
    private const string LATER_UTC_DATE = "2026-11-10T09:18:00+00:00";
    private const string EVEN_LATER_UTC_DATE = "2026-11-10T10:18:00+00:00";
    private const string SAME_INSTANT_WITH_OFFSET = "2026-11-10T11:18:00+03:00";

    private const string INSERT_WORD_SQL = "INSERT INTO \"Words\" (\"Name\", \"Translation\") VALUES ({0}, {1})";
    private const string INSERT_ROTATED_WORD_SQL = "INSERT INTO \"RotatedWords\" (\"WordId\") VALUES ({0})";
    private const string MIGRATION_HISTORY_SQL = "SELECT \"MigrationId\" AS \"Value\" FROM \"__EFMigrationsHistory\"";
    private const string STORED_DATE_SQL = "SELECT \"Date\" AS \"Value\" FROM \"WordHistory\"";

    private static readonly DateTimeOffset UtcDate = ParseDate(UTC_DATE);
    private static readonly DateTimeOffset LaterUtcDate = ParseDate(LATER_UTC_DATE);
    private static readonly DateTimeOffset EvenLaterUtcDate = ParseDate(EVEN_LATER_UTC_DATE);

    private readonly TestDatabase database = new();

    [Fact]
    public void TestsUseDatabaseOfEnvTestFile()
    {
        // J1, J2
        var connectionString = database.ConnectionString;

        Environment.GetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE).Should().Be(database.EnvFilePath);
        var databaseName = new NpgsqlConnectionStringBuilder(connectionString).Database;
        databaseName.Should().Be(Environment.GetEnvironmentVariable(DatabaseSettings.NAME_KEY));
        databaseName.Should().EndWith(TestDatabase.TEST_DATABASE_SUFFIX);
    }

    [Fact]
    public void RecreatedDatabaseStartsEmpty()
    {
        // J3
        using var context = database.RecreateMigrated();

        context.Words.Should().BeEmpty();
        context.RotatedWords.Should().BeEmpty();
        context.WordHistories.Should().BeEmpty();
        context.Schedules.Should().BeEmpty();
        context.PushSubscriptions.Should().BeEmpty();
    }

    [Fact]
    public void StartupAppliesAllMigrationsToEmptyDatabase()
    {
        // B3
        database.RecreateEmpty();
        using var services = database.CreateServices();

        DatabaseMigration.Apply(services);

        using var context = database.CreateContext();
        context.Database.GetPendingMigrations().Should().BeEmpty();
        context.Database.GetAppliedMigrations().Should().ContainSingle();
    }

    [Fact]
    public void SecondStartupAppliesNothingAgain()
    {
        // B4
        database.RecreateEmpty();
        using var services = database.CreateServices();
        DatabaseMigration.Apply(services);

        var applyAgain = () => DatabaseMigration.Apply(services);

        applyAgain.Should().NotThrow();
        using var context = database.CreateContext();
        context.Database.GetAppliedMigrations().Should().ContainSingle();
    }

    [Fact]
    public void MigrationHistoryListsInitialMigration()
    {
        // B5
        using var context = database.RecreateMigrated();

        var migrationIds = context.Database.SqlQueryRaw<string>(MIGRATION_HISTORY_SQL).ToList();

        migrationIds.Should().ContainSingle().Which.Should().EndWith(INITIAL_MIGRATION_SUFFIX);
    }

    [Fact]
    public void InsertWithOnlyNameAndTranslationSucceeds()
    {
        // C8
        using var context = database.RecreateMigrated();

        var affectedRows = InsertWordWithSql(context);

        affectedRows.Should().Be(INSERTED_ROW_COUNT);
    }

    [Fact]
    public void InsertedWordGetsDatabaseDefaults()
    {
        // C9, C10, C11, C12
        using var context = database.RecreateMigrated();
        InsertWordWithSql(context);

        var word = context.Words.AsNoTracking().Single(stored => stored.Name == WORD_NAME);

        word.Id.Should().NotBe(Guid.Empty);
        word.Translation.Should().Be(WORD_TRANSLATION);
        word.IsKnown.Should().BeFalse();
        word.IsReinforcement.Should().BeFalse();
        word.ShownCount.Should().Be(DEFAULT_COUNT);
        word.KnownCount.Should().Be(DEFAULT_COUNT);
        word.Content.Should().BeNull();
    }

    [Fact]
    public void WordsWithSameNameAreAccepted()
    {
        // C13
        using var context = database.RecreateMigrated();
        InsertWordWithSql(context);

        InsertWordWithSql(context);

        context.Words.Count(stored => stored.Name == WORD_NAME).Should().Be(DUPLICATE_WORD_COUNT);
    }

    [Fact]
    public void RotatedWordCounterDefaultsToOne()
    {
        // D5
        using var context = database.RecreateMigrated();
        var word = AddWord(context);

        context.Database.ExecuteSqlRaw(INSERT_ROTATED_WORD_SQL, word.Id);

        context.RotatedWords.AsNoTracking().Single().Counter.Should().Be(DEFAULT_COUNTER);
    }

    [Fact]
    public void RotatedWordWithUnknownWordIsRejected()
    {
        // D6
        using var context = database.RecreateMigrated();
        context.RotatedWords.Add(new RotatedWord { WordId = Guid.NewGuid() });

        SaveShouldBeRejected(context, FOREIGN_KEY_VIOLATION);
    }

    [Fact]
    public void SecondRotatedWordForSameWordIsRejected()
    {
        // D7
        using var context = database.RecreateMigrated();
        var word = AddWord(context);
        context.RotatedWords.Add(new RotatedWord { WordId = word.Id });
        context.SaveChanges();
        context.RotatedWords.Add(new RotatedWord { WordId = word.Id });

        SaveShouldBeRejected(context, UNIQUE_VIOLATION);
    }

    [Fact]
    public void DeletingWordDeletesItsRotatedWord()
    {
        // D8
        using var context = database.RecreateMigrated();
        var word = AddWord(context);
        context.RotatedWords.Add(new RotatedWord { WordId = word.Id });
        context.SaveChanges();

        DeleteWordInDatabase(context, word);

        context.RotatedWords.Should().BeEmpty();
    }

    [Fact]
    public void ConfigHasFourSeedRows()
    {
        // E4
        using var context = database.RecreateMigrated();

        context.Configs.Count().Should().Be(SEED_ROW_COUNT);
    }

    [Theory]
    [InlineData("RotationCount", "Rotation Count", "20")] // E5
    [InlineData("RotationPeriod", "Rotation period", "15")] // E6
    [InlineData("ReinforcementPeriod", "Reinforcement period", "10800")] // E7
    [InlineData("NotificationPeriod", "Notification period", "15")] // E8
    public void SeedRowHasExpectedValues(string code, string name, string value)
    {
        // E5, E6, E7, E8
        using var context = database.RecreateMigrated();

        var config = context.Configs.AsNoTracking().Single(stored => stored.Code == code);

        config.Name.Should().Be(name);
        config.Value.Should().Be(value);
        config.InputType.Should().Be(InputType.Number);
    }

    [Fact]
    public void ConfigWithExistingCodeIsRejected()
    {
        // E9
        using var context = database.RecreateMigrated();
        context.Configs.Add(NewConfig(SEEDED_CODE, InputType.Number));

        SaveShouldBeRejected(context, UNIQUE_VIOLATION);
    }

    [Fact]
    public void EveryInputTypeRoundTrips()
    {
        // E11
        using (var writeContext = database.RecreateMigrated())
        {
            writeContext.Configs.AddRange(Enum.GetValues<InputType>().Select(inputType => NewConfig(CodeOf(inputType), inputType)));
            writeContext.SaveChanges();
        }

        using var readContext = database.CreateContext();
        foreach (var inputType in Enum.GetValues<InputType>())
        {
            var code = CodeOf(inputType);
            readContext.Configs.AsNoTracking().Single(config => config.Code == code).InputType.Should().Be(inputType);
            StoredInputTypeOf(readContext, code).Should().Be(inputType.ToString());
        }
    }

    [Fact]
    public void ChangedSeedValueIsKeptAfterRestart()
    {
        // E12
        using (var context = database.RecreateMigrated())
        {
            context.Configs.Where(config => config.Code == SEEDED_CODE)
                .ExecuteUpdate(setters => setters.SetProperty(config => config.Value, CHANGED_VALUE));
        }

        using (var services = database.CreateServices())
        {
            DatabaseMigration.Apply(services);
        }

        using var readContext = database.CreateContext();
        readContext.Configs.AsNoTracking().Single(config => config.Code == SEEDED_CODE).Value.Should().Be(CHANGED_VALUE);
    }

    [Fact]
    public void WordHistoryWithUnknownWordIsRejected()
    {
        // F4
        using var context = database.RecreateMigrated();
        context.WordHistories.Add(new WordHistory { WordId = Guid.NewGuid(), Date = UtcDate });

        SaveShouldBeRejected(context, FOREIGN_KEY_VIOLATION);
    }

    [Fact]
    public void DeletingWordDeletesItsHistory()
    {
        // F5
        using var context = database.RecreateMigrated();
        var word = AddWord(context);
        context.WordHistories.AddRange(
            new WordHistory { WordId = word.Id, IsKnown = true, Date = UtcDate },
            new WordHistory { WordId = word.Id, IsKnown = false, Date = LaterUtcDate });
        context.SaveChanges();

        DeleteWordInDatabase(context, word);

        context.WordHistories.Should().BeEmpty();
    }

    [Fact]
    public void ScheduleWithEndDateAfterStartDateIsAccepted()
    {
        // G3
        using var context = database.RecreateMigrated();
        context.Schedules.Add(new Schedule { StartDate = UtcDate, EndDate = LaterUtcDate });

        context.SaveChanges();

        context.Schedules.Should().ContainSingle();
    }

    [Fact]
    public void ScheduleWithEndDateEqualToStartDateIsRejected()
    {
        // G4
        using var context = database.RecreateMigrated();
        context.Schedules.Add(new Schedule { StartDate = UtcDate, EndDate = UtcDate });

        SaveShouldBeRejected(context, CHECK_VIOLATION);
    }

    [Fact]
    public void ScheduleWithEndDateBeforeStartDateIsRejected()
    {
        // G5
        using var context = database.RecreateMigrated();
        context.Schedules.Add(new Schedule { StartDate = LaterUtcDate, EndDate = UtcDate });

        SaveShouldBeRejected(context, CHECK_VIOLATION);
    }

    [Fact]
    public void OverlappingSchedulesAreAccepted()
    {
        // G6
        using var context = database.RecreateMigrated();
        context.Schedules.AddRange(
            new Schedule { StartDate = UtcDate, EndDate = EvenLaterUtcDate },
            new Schedule { StartDate = LaterUtcDate, EndDate = EvenLaterUtcDate });

        context.SaveChanges();

        context.Schedules.Count().Should().Be(OVERLAPPING_WINDOW_COUNT);
    }

    [Fact]
    public void UtcDateRoundTripsWithZeroOffset()
    {
        // I1
        SaveHistoryDate(UtcDate);

        var stored = ReadHistoryDate();

        stored.Should().Be(UtcDate);
        stored.Offset.Should().Be(TimeSpan.Zero);
    }

    [Fact]
    public void DateWithOffsetIsStoredAsSameUtcInstant()
    {
        // I2
        var dateWithOffset = ParseDate(SAME_INSTANT_WITH_OFFSET);
        SaveHistoryDate(dateWithOffset);

        using var context = database.CreateContext();
        var storedValue = context.Database.SqlQueryRaw<DateTime>(STORED_DATE_SQL).ToList().Single();

        storedValue.Kind.Should().Be(DateTimeKind.Utc);
        storedValue.Should().Be(UtcDate.UtcDateTime);
        ReadHistoryDate().Offset.Should().Be(TimeSpan.Zero);
    }

    public void Dispose() => database.Dispose();

    private static DateTimeOffset ParseDate(string value) => DateTimeOffset.Parse(value, CultureInfo.InvariantCulture);

    private static int InsertWordWithSql(FuXiDbContext context) =>
        context.Database.ExecuteSqlRaw(INSERT_WORD_SQL, WORD_NAME, WORD_TRANSLATION);

    private static Word AddWord(FuXiDbContext context)
    {
        var word = new Word { Name = WORD_NAME, Translation = WORD_TRANSLATION };
        context.Words.Add(word);
        context.SaveChanges();

        return word;
    }

    // Deletes in the database so the cascade comes from PostgreSQL, not from EF Core tracking.
    private static void DeleteWordInDatabase(FuXiDbContext context, Word word)
    {
        context.ChangeTracker.Clear();
        context.Words.Where(stored => stored.Id == word.Id).ExecuteDelete();
    }

    private static string CodeOf(InputType inputType) => $"{TEST_CODE_PREFIX}{inputType}";

    private static Config NewConfig(string code, InputType inputType) =>
        new() { Name = code, Code = code, Value = TEST_VALUE, InputType = inputType };

    private static string StoredInputTypeOf(FuXiDbContext context, string code) =>
        context.Database.SqlQuery<string>($"SELECT \"InputType\" AS \"Value\" FROM \"Config\" WHERE \"Code\" = {code}")
            .ToList()
            .Single();

    private static void SaveShouldBeRejected(FuXiDbContext context, string sqlState)
    {
        var save = () => context.SaveChanges();

        save.Should().Throw<DbUpdateException>()
            .WithInnerException<PostgresException>()
            .Which.SqlState.Should().Be(sqlState);
    }

    private void SaveHistoryDate(DateTimeOffset date)
    {
        using var context = database.RecreateMigrated();
        var word = AddWord(context);
        context.WordHistories.Add(new WordHistory { WordId = word.Id, IsKnown = true, Date = date });
        context.SaveChanges();
    }

    private DateTimeOffset ReadHistoryDate()
    {
        using var context = database.CreateContext();

        return context.WordHistories.AsNoTracking().Single().Date;
    }
}
