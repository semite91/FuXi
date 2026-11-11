using System.Globalization;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Tests.Api;

/// <summary>Builds the stored state the API tests start from.</summary>
public static class TestData
{
    public const string ROTATION_COUNT_CODE = ConfigCodes.ROTATION_COUNT;
    public const string ROTATION_PERIOD_CODE = ConfigCodes.ROTATION_PERIOD;
    public const string REINFORCEMENT_PERIOD_CODE = ConfigCodes.REINFORCEMENT_PERIOD;
    public const string NOTIFICATION_PERIOD_CODE = ConfigCodes.NOTIFICATION_PERIOD;
    public const int SEEDED_CONFIG_COUNT = 4;
    public const int SEEDED_ROTATION_COUNT = 20;
    public const int SEEDED_ROTATION_PERIOD = 15;
    public const int SEEDED_REINFORCEMENT_PERIOD = 10800;
    public const int FIRST_COUNTER = 1;
    public const string WORD_NAME = "apple";
    public const string OTHER_WORD_NAME = "banana";
    public const string TRANSLATION = "elma";

    // Months before the real date, so a rule that reads the real clock gives another result.
    private const string NOW_TEXT = "2026-01-15T10:00:00+00:00";
    private const string SCHEDULE_DAY_TEXT = "2026-11-10T00:00:00+00:00";
    private const string ROUND_TRIP_FORMAT = "O";
    private const string NUMBERED_NAME_FORMAT = "{0}{1:D3}";
    private const string DEFAULT_NAME_PREFIX = "word";

    private const string FAILING_FUNCTION_SQL = """
        CREATE OR REPLACE FUNCTION fail_statement() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Failure injected by a test';
        END;
        $$ LANGUAGE plpgsql
        """;
    private const string FAIL_WORD_HISTORY_INSERT_SQL =
        "CREATE TRIGGER fail_word_history_insert BEFORE INSERT ON \"WordHistory\" FOR EACH ROW EXECUTE FUNCTION fail_statement()";
    private const string FAIL_ROTATED_WORD_DELETE_SQL =
        "CREATE TRIGGER fail_rotated_word_delete BEFORE DELETE ON \"RotatedWords\" FOR EACH ROW EXECUTE FUNCTION fail_statement()";

    public static readonly DateTimeOffset Now = ParseDate(NOW_TEXT);

    private static readonly DateTimeOffset ScheduleDay = ParseDate(SCHEDULE_DAY_TEXT);

    /// <summary>A UTC time on the day the Notification Window tests use.</summary>
    public static DateTimeOffset TimeOfDay(int hour, int minute = 0) => ScheduleDay.AddHours(hour).AddMinutes(minute);

    public static DateTimeOffset ParseDate(string value) => DateTimeOffset.Parse(value, CultureInfo.InvariantCulture);

    /// <summary>The ISO 8601 text of a date-time, as a query value carries it.</summary>
    public static string Iso(DateTimeOffset date) => date.ToString(ROUND_TRIP_FORMAT, CultureInfo.InvariantCulture);

    public static Word AddWord(
        FuXiDbContext context,
        string name = WORD_NAME,
        bool isKnown = false,
        bool isReinforcement = false,
        int shownCount = 0,
        int knownCount = 0,
        string? content = null)
    {
        var word = new Word
        {
            Name = name,
            Translation = TRANSLATION,
            IsKnown = isKnown,
            IsReinforcement = isReinforcement,
            ShownCount = shownCount,
            KnownCount = knownCount,
            Content = content,
        };
        context.Words.Add(word);
        context.SaveChanges();

        return word;
    }

    /// <summary>Adds Words named prefix001, prefix002 and so on. Each can be drawn into the Rotation.</summary>
    public static IReadOnlyList<Word> AddWords(FuXiDbContext context, int count, string namePrefix = DEFAULT_NAME_PREFIX)
    {
        var words = Enumerable.Range(1, count)
            .Select(number => new Word { Name = NumberedName(namePrefix, number), Translation = TRANSLATION })
            .ToList();
        context.Words.AddRange(words);
        context.SaveChanges();

        return words;
    }

    public static RotatedWord AddRotatedWord(
        FuXiDbContext context, Word word, int counter = FIRST_COUNTER, DateTimeOffset? lastShownDate = null)
    {
        var rotatedWord = new RotatedWord { WordId = word.Id, Counter = counter, LastShownDate = lastShownDate };
        context.RotatedWords.Add(rotatedWord);
        context.SaveChanges();

        return rotatedWord;
    }

    /// <summary>Adds Words that are all in the Rotation and were never shown.</summary>
    public static IReadOnlyList<Word> AddRotatedWords(FuXiDbContext context, int count, string namePrefix = DEFAULT_NAME_PREFIX)
    {
        var words = AddWords(context, count, namePrefix);
        context.RotatedWords.AddRange(words.Select(word => new RotatedWord { WordId = word.Id, Counter = FIRST_COUNTER }));
        context.SaveChanges();

        return words;
    }

    public static WordHistory AddHistory(FuXiDbContext context, Word word, bool isKnown, DateTimeOffset date)
    {
        var history = new WordHistory { WordId = word.Id, IsKnown = isKnown, Date = date };
        context.WordHistories.Add(history);
        context.SaveChanges();

        return history;
    }

    public static Schedule AddSchedule(FuXiDbContext context, DateTimeOffset startDate, DateTimeOffset endDate)
    {
        var schedule = new Schedule { StartDate = startDate, EndDate = endDate };
        context.Schedules.Add(schedule);
        context.SaveChanges();

        return schedule;
    }

    public static Config ConfigOf(FuXiDbContext context, string code) =>
        context.Configs.AsNoTracking().Single(config => config.Code == code);

    public static void SetConfig(FuXiDbContext context, string code, int value)
    {
        var text = value.ToString(CultureInfo.InvariantCulture);
        context.Configs.Where(config => config.Code == code)
            .ExecuteUpdate(setters => setters.SetProperty(config => config.Value, text));
    }

    /// <summary>From now on every INSERT into WordHistory fails in the database.</summary>
    public static void FailWordHistoryInsert(FuXiDbContext context)
    {
        context.Database.ExecuteSqlRaw(FAILING_FUNCTION_SQL);
        context.Database.ExecuteSqlRaw(FAIL_WORD_HISTORY_INSERT_SQL);
    }

    /// <summary>From now on every DELETE from RotatedWords fails in the database.</summary>
    public static void FailRotatedWordDelete(FuXiDbContext context)
    {
        context.Database.ExecuteSqlRaw(FAILING_FUNCTION_SQL);
        context.Database.ExecuteSqlRaw(FAIL_ROTATED_WORD_DELETE_SQL);
    }

    private static string NumberedName(string prefix, int number) =>
        string.Format(CultureInfo.InvariantCulture, NUMBERED_NAME_FORMAT, prefix, number);
}
