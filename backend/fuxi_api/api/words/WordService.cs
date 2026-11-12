using System.Globalization;
using System.Linq.Expressions;
using FuXi.Api.Configs;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.EntityFrameworkCore;

namespace FuXi.Api.Words;

/// <summary>The Word and Rotation logic behind the words endpoints.</summary>
public sealed class WordService(FuXiDbContext database, TimeProvider timeProvider)
{
    private const char WORD_ID_SEPARATOR = ',';
    private const int FIRST_COUNTER = 1;
    private const string LIKE_ESCAPE = "\\";
    private const string LIKE_ANY_TEXT = "%";

    // The escape character comes first, so the escapes added for the other two are not escaped again.
    private static readonly string[] LIKE_SPECIAL_TEXTS = [LIKE_ESCAPE, LIKE_ANY_TEXT, "_"];
    private static readonly string[] ROTATION_CODES =
        [ConfigCodes.ROTATION_COUNT, ConfigCodes.ROTATION_PERIOD, ConfigCodes.REINFORCEMENT_PERIOD];

    // The PostgreSQL advisory lock that makes the Rotation top-up run one call at a time. Any fixed number works.
    private const long ROTATION_TOP_UP_LOCK_KEY = 7305001;

    private static readonly Expression<Func<RotationRow, CardWord>> TO_CARD_WORD = row => new CardWord(
        row.Word.Id,
        row.Word.Name,
        row.Word.Translation,
        row.Rotated.Counter,
        row.Word.IsReinforcement,
        row.Rotated.LastShownDate,
        row.Word.Content);

    private const string WORD_IDS_MISSING = "wordIds is missing.";
    private const string WORD_IDS_INVALID = "wordIds must be Guids joined with a comma.";
    private const string CONTENT_MISSING = "content is missing or empty.";
    private const string WORD_NOT_FOUND = "The Word was not found.";
    private const string WORD_NOT_IN_ROTATION = "The Word was not found in the Rotation.";

    /// <summary>Tops up the Rotation, then returns the Words that are Due at the given date.</summary>
    public async Task<IReadOnlyList<NotificationWord>> GetNotificationWordsAsync(DateTimeOffset date, CancellationToken cancellationToken)
    {
        var settings = await ReadRotationSettingsAsync(cancellationToken);
        await TopUpRotationAsync(settings.RotationCount, cancellationToken);

        return await DueWords(settings, date.ToUniversalTime())
            .Select(row => new NotificationWord(row.Word.Id, row.Word.Name))
            .ToListAsync(cancellationToken);
    }

    /// <summary>Returns the Words of the given comma-joined ids that are in the Rotation, in the order of the ids.</summary>
    public Task<IReadOnlyList<CardWord>> GetCardWordsAsync(string? wordIds, CancellationToken cancellationToken) =>
        GetCardWordsAsync(ParseWordIds(wordIds), cancellationToken);

    /// <summary>Tops up the Rotation, then returns the Words that are Due now, as Flashcard data.</summary>
    public async Task<IReadOnlyList<CardWord>> GetWordsByActiveAsync(CancellationToken cancellationToken)
    {
        var settings = await ReadRotationSettingsAsync(cancellationToken);
        await TopUpRotationAsync(settings.RotationCount, cancellationToken);

        return await DueWords(settings, timeProvider.GetUtcNow()).Select(TO_CARD_WORD).ToListAsync(cancellationToken);
    }

    /// <summary>Returns the Word History of a Word, newest first.</summary>
    public async Task<IReadOnlyList<WordHistoryItem>> GetWordHistoryAsync(Guid wordId, CancellationToken cancellationToken)
    {
        if (!await database.Words.AnyAsync(word => word.Id == wordId, cancellationToken))
        {
            throw ApiException.NotFound(WORD_NOT_FOUND);
        }

        return await database.WordHistories.AsNoTracking()
            .Where(history => history.WordId == wordId)
            .OrderByDescending(history => history.Date)
            .Select(history => new WordHistoryItem(history.IsKnown, history.Date))
            .ToListAsync(cancellationToken);
    }

    /// <summary>Returns the Words that match every filled field of the filter, ordered by name.</summary>
    public async Task<IReadOnlyList<FilteredWord>> GetWordsByFilterAsync(WordFilterRequest request, CancellationToken cancellationToken)
    {
        var filter = WordFilter.Parse(request);

        return filter.IsEmpty ? [] : await FilteredWords(filter).ToListAsync(cancellationToken);
    }

    /// <summary>Replaces the Word Content of a Word.</summary>
    public async Task UpdateWordContentAsync(Guid id, string? content, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(content))
        {
            throw ApiException.BadRequest(CONTENT_MISSING);
        }

        var updatedCount = await database.Words
            .Where(word => word.Id == id)
            .ExecuteUpdateAsync(setters => setters.SetProperty(word => word.Content, content), cancellationToken);
        if (updatedCount == 0)
        {
            throw ApiException.NotFound(WORD_NOT_FOUND);
        }
    }

    /// <summary>Records one answer of the Learner: Rotation entry, Word counters and Word History, in one transaction.</summary>
    public async Task UpdateWordKnownStatusAsync(Guid wordId, bool isKnown, CancellationToken cancellationToken)
    {
        var now = timeProvider.GetUtcNow();
        var rotatedWord = await database.RotatedWords.SingleOrDefaultAsync(rotated => rotated.WordId == wordId, cancellationToken)
            ?? throw ApiException.NotFound(WORD_NOT_IN_ROTATION);
        var word = await database.Words.SingleAsync(word => word.Id == wordId, cancellationToken);

        ApplyAnswer(rotatedWord, word, isKnown, now);
        database.WordHistories.Add(new WordHistory { WordId = wordId, IsKnown = isKnown, Date = now });

        // One SaveChanges writes all three changes in one transaction.
        await database.SaveChangesAsync(cancellationToken);
    }

    /// <summary>Sets the reinforcement flag and takes the Word out of the Rotation, in one transaction.</summary>
    public async Task UpdateIsReinforcementAsync(Guid wordId, bool isReinforcement, CancellationToken cancellationToken)
    {
        var word = await database.Words.SingleOrDefaultAsync(word => word.Id == wordId, cancellationToken)
            ?? throw ApiException.NotFound(WORD_NOT_FOUND);
        var rotatedWord = await database.RotatedWords.SingleOrDefaultAsync(rotated => rotated.WordId == wordId, cancellationToken);

        word.IsReinforcement = isReinforcement;
        if (rotatedWord is not null)
        {
            database.RotatedWords.Remove(rotatedWord);
        }

        // One SaveChanges writes the flag and the removal in one transaction.
        await database.SaveChangesAsync(cancellationToken);
    }

    private static void ApplyAnswer(RotatedWord rotatedWord, Word word, bool isKnown, DateTimeOffset now)
    {
        rotatedWord.LastShownDate = now;
        word.ShownCount++;

        if (!isKnown)
        {
            rotatedWord.Counter = FIRST_COUNTER;
            return;
        }

        rotatedWord.Counter++;
        word.KnownCount++;
        word.IsKnown = true;
    }

    private async Task<RotationSettings> ReadRotationSettingsAsync(CancellationToken cancellationToken)
    {
        var values = await database.Configs.AsNoTracking()
            .Where(config => ROTATION_CODES.Contains(config.Code))
            .ToDictionaryAsync(config => config.Code, config => config.Value, cancellationToken);

        return new RotationSettings(
            ReadNumber(values, ConfigCodes.ROTATION_COUNT),
            ReadNumber(values, ConfigCodes.ROTATION_PERIOD),
            ReadNumber(values, ConfigCodes.REINFORCEMENT_PERIOD));
    }

    private static int ReadNumber(Dictionary<string, string> values, string code) =>
        values.TryGetValue(code, out var value) && ConfigValue.TryParseNumber(value, out var number)
            ? number
            : throw new InvalidOperationException($"Config value {code} is missing or is not a whole number.");

    // The lock is held until the transaction ends, so two calls never count and fill the Rotation at the same time.
    private async Task TopUpRotationAsync(int rotationCount, CancellationToken cancellationToken)
    {
        await using var transaction = await database.Database.BeginTransactionAsync(cancellationToken);
        await database.Database.ExecuteSqlAsync($"SELECT pg_advisory_xact_lock({ROTATION_TOP_UP_LOCK_KEY})", cancellationToken);

        await AddMissingRotatedWordsAsync(rotationCount, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    // Adds randomly chosen Words until the Rotation holds RotationCount entries.
    private async Task AddMissingRotatedWordsAsync(int rotationCount, CancellationToken cancellationToken)
    {
        var missingCount = rotationCount - await database.RotatedWords.CountAsync(cancellationToken);
        if (missingCount <= 0)
        {
            return;
        }

        var wordIds = await TopUpCandidates(missingCount).ToListAsync(cancellationToken);
        database.RotatedWords.AddRange(wordIds.Select(wordId => new RotatedWord { WordId = wordId, Counter = FIRST_COUNTER }));
        await database.SaveChangesAsync(cancellationToken);
    }

    private IQueryable<Guid> TopUpCandidates(int count) =>
        database.Words.AsNoTracking()
            .Where(word => !word.IsKnown || word.IsReinforcement)
            .Where(word => !database.RotatedWords.Any(rotated => rotated.WordId == word.Id))
            .OrderBy(word => EF.Functions.Random())
            .Take(count)
            .Select(word => word.Id);

    // A Reinforced Word waits ReinforcementPeriod; any other Word waits Counter * RotationPeriod.
    private IQueryable<RotationRow> DueWords(RotationSettings settings, DateTimeOffset date)
    {
        var rotationPeriod = settings.RotationPeriod;
        var reinforcedDueBefore = date.AddMinutes(-settings.ReinforcementPeriod);

        return RotationRows().Where(row => row.Rotated.LastShownDate == null
            || (row.Word.IsReinforcement
                ? row.Rotated.LastShownDate <= reinforcedDueBefore
                : row.Rotated.LastShownDate.Value.AddMinutes(row.Rotated.Counter * rotationPeriod) <= date));
    }

    // Every Word in the Rotation, next to its Rotation entry.
    private IQueryable<RotationRow> RotationRows() =>
        from word in database.Words.AsNoTracking()
        join rotated in database.RotatedWords on word.Id equals rotated.WordId
        select new RotationRow { Word = word, Rotated = rotated };

    private async Task<IReadOnlyList<CardWord>> GetCardWordsAsync(Guid[] wordIds, CancellationToken cancellationToken)
    {
        if (wordIds.Length == 0)
        {
            return [];
        }

        var words = await CardWords(wordIds).ToDictionaryAsync(word => word.Id, cancellationToken);

        return wordIds.Where(words.ContainsKey).Select(wordId => words[wordId]).ToList();
    }

    private IQueryable<CardWord> CardWords(Guid[] wordIds) =>
        RotationRows().Where(row => wordIds.Contains(row.Word.Id)).Select(TO_CARD_WORD);

    // Returns each id once, in the order it was given.
    private static Guid[] ParseWordIds(string? wordIds)
    {
        if (string.IsNullOrWhiteSpace(wordIds))
        {
            throw ApiException.BadRequest(WORD_IDS_MISSING);
        }

        var texts = wordIds.Split(WORD_ID_SEPARATOR);
        var ids = new List<Guid>(texts.Length);
        foreach (var text in texts)
        {
            ids.Add(Guid.TryParse(text, CultureInfo.InvariantCulture, out var id) ? id : throw ApiException.BadRequest(WORD_IDS_INVALID));
        }

        return ids.Distinct().ToArray();
    }

    private IQueryable<FilteredWord> FilteredWords(WordFilter filter)
    {
        var query =
            from word in database.Words.AsNoTracking()
            join rotated in database.RotatedWords on word.Id equals rotated.WordId into rotation
            from rotated in rotation.DefaultIfEmpty()
            select new { Word = word, Rotated = rotated };

        if (filter.Name is not null)
        {
            var escapedName = EscapeLike(filter.Name);
            var startsWith = escapedName + LIKE_ANY_TEXT;
            var endsWith = LIKE_ANY_TEXT + escapedName;
            query = query.Where(row => EF.Functions.ILike(row.Word.Name, startsWith, LIKE_ESCAPE)
                || EF.Functions.ILike(row.Word.Name, endsWith, LIKE_ESCAPE));
        }

        if (filter.IsReinforcement is bool isReinforcement)
        {
            query = query.Where(row => row.Word.IsReinforcement == isReinforcement);
        }

        if (filter.IsKnown is bool isKnown)
        {
            query = query.Where(row => row.Word.IsKnown == isKnown);
        }

        if (filter.IsRotated is bool isRotated)
        {
            query = query.Where(row => (row.Rotated != null) == isRotated);
        }

        return query
            .OrderBy(row => row.Word.Name)
            .Select(row => new FilteredWord(
                row.Word.Id,
                row.Word.Name,
                row.Word.IsReinforcement,
                row.Word.IsKnown,
                row.Rotated!.LastShownDate,
                row.Word.ShownCount,
                row.Word.KnownCount,
                row.Rotated != null,
                (int?)row.Rotated!.Counter));
    }

    // Makes %, _ and \ match themselves in a LIKE pattern.
    private static string EscapeLike(string text) =>
        LIKE_SPECIAL_TEXTS.Aggregate(text, (escaped, special) => escaped.Replace(special, LIKE_ESCAPE + special, StringComparison.Ordinal));

    private sealed record RotationSettings(int RotationCount, int RotationPeriod, int ReinforcementPeriod);

    // A query row only: it is never loaded, the queries project from it.
    private sealed class RotationRow
    {
        public required Word Word { get; init; }

        public required RotatedWord Rotated { get; init; }
    }
}
