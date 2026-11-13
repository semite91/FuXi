using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata;
using Quartz;
using Xunit;

namespace FuXi.Api.Tests.Database;

/// <summary>Reads the design-time EF Core model. No database is needed.</summary>
public sealed class ModelTests : IDisposable
{
    private const string ID = "Id";
    private const string WORD_ID = "WordId";
    private const string UUID_TYPE = "uuid";
    private const string TEXT_TYPE = "text";
    private const string BOOLEAN_TYPE = "boolean";
    private const string INTEGER_TYPE = "integer";
    private const string UUID_DEFAULT_SQL = "gen_random_uuid()";
    private const int DEFAULT_COUNT = 0;
    private const int DEFAULT_COUNTER = 1;
    private const string CHECK_CONSTRAINT_NAME = "CK_Schedule_EndDate_After_StartDate";
    private const string CHECK_CONSTRAINT_SQL = "\"EndDate\" > \"StartDate\"";
    private const string REPOSITORY_SUFFIX = "Repository";
    private static readonly string[] TIMESTAMPTZ_TYPES = ["timestamp with time zone", "timestamptz"];

    private readonly FuXiDbContext context = ModelOnlyContext.Create();

    private IModel Model => context.GetService<IDesignTimeModel>().Model;

    [Fact]
    public void WordsTableHasExpectedColumns()
    {
        // C1
        ColumnsOf<Word>().Should().BeEquivalentTo(
            "Id", "Name", "Translation", "Content", "IsKnown", "IsReinforcement", "ShownCount", "KnownCount");
        TableOf<Word>().Should().Be("Words");
    }

    [Fact]
    public void WordsIdIsUuidPrimaryKey()
    {
        // C2
        ShouldBeUuidPrimaryKey<Word>();
    }

    [Fact]
    public void WordsTextColumnsAreText()
    {
        // C3
        ColumnTypeOf<Word>(nameof(Word.Name)).Should().Be(TEXT_TYPE);
        ColumnTypeOf<Word>(nameof(Word.Translation)).Should().Be(TEXT_TYPE);
        ColumnTypeOf<Word>(nameof(Word.Content)).Should().Be(TEXT_TYPE);
    }

    [Fact]
    public void WordsFlagColumnsAreBoolean()
    {
        // C4
        ColumnTypeOf<Word>(nameof(Word.IsKnown)).Should().Be(BOOLEAN_TYPE);
        ColumnTypeOf<Word>(nameof(Word.IsReinforcement)).Should().Be(BOOLEAN_TYPE);
    }

    [Fact]
    public void WordsCountColumnsAreInteger()
    {
        // C5
        ColumnTypeOf<Word>(nameof(Word.ShownCount)).Should().Be(INTEGER_TYPE);
        ColumnTypeOf<Word>(nameof(Word.KnownCount)).Should().Be(INTEGER_TYPE);
    }

    [Fact]
    public void WordsContentIsNullable()
    {
        // C6, C12
        var content = PropertyOf<Word>(nameof(Word.Content));

        content.IsNullable.Should().BeTrue();
        content.GetDefaultValue().Should().BeNull();
    }

    [Fact]
    public void WordsNameAndTranslationAreRequired()
    {
        // C7
        PropertyOf<Word>(nameof(Word.Name)).IsNullable.Should().BeFalse();
        PropertyOf<Word>(nameof(Word.Translation)).IsNullable.Should().BeFalse();
    }

    [Fact]
    public void WordsFlagsDefaultToFalse()
    {
        // C10
        PropertyOf<Word>(nameof(Word.IsKnown)).GetDefaultValue().Should().Be(false);
        PropertyOf<Word>(nameof(Word.IsReinforcement)).GetDefaultValue().Should().Be(false);
    }

    [Fact]
    public void WordsCountsDefaultToZero()
    {
        // C11
        PropertyOf<Word>(nameof(Word.ShownCount)).GetDefaultValue().Should().Be(DEFAULT_COUNT);
        PropertyOf<Word>(nameof(Word.KnownCount)).GetDefaultValue().Should().Be(DEFAULT_COUNT);
    }

    [Fact]
    public void WordsNameIsNotUnique()
    {
        // C13
        EntityOf<Word>().GetIndexes().Where(index => index.IsUnique).Should().BeEmpty();
        EntityOf<Word>().GetKeys().Should().ContainSingle().Which.Properties.Single().Name.Should().Be(ID);
    }

    [Fact]
    public void RotatedWordsTableHasExpectedColumns()
    {
        // D1
        ColumnsOf<RotatedWord>().Should().BeEquivalentTo("Id", "WordId", "LastShownDate", "Counter");
        TableOf<RotatedWord>().Should().Be("RotatedWords");
    }

    [Fact]
    public void RotatedWordsIdIsUuidPrimaryKey()
    {
        // D2
        ShouldBeUuidPrimaryKey<RotatedWord>();
    }

    [Fact]
    public void RotatedWordsLastShownDateIsNullableTimestamptz()
    {
        // D3
        ColumnTypeOf<RotatedWord>(nameof(RotatedWord.LastShownDate)).Should().BeOneOf(TIMESTAMPTZ_TYPES);
        PropertyOf<RotatedWord>(nameof(RotatedWord.LastShownDate)).IsNullable.Should().BeTrue();
    }

    [Fact]
    public void RotatedWordsCounterIsIntegerWithDefaultOne()
    {
        // D4, D5
        ColumnTypeOf<RotatedWord>(nameof(RotatedWord.Counter)).Should().Be(INTEGER_TYPE);
        PropertyOf<RotatedWord>(nameof(RotatedWord.Counter)).GetDefaultValue().Should().Be(DEFAULT_COUNTER);
    }

    [Fact]
    public void RotatedWordsWordIdIsUnique()
    {
        // D7
        UniqueIndexColumnsOf<RotatedWord>().Should().ContainSingle().Which.Should().Equal(WORD_ID);
    }

    [Fact]
    public void RotatedWordsCascadeWhenWordIsDeleted()
    {
        // D6, D8
        ShouldCascadeFromWord<RotatedWord>();
    }

    [Fact]
    public void ConfigTableHasExpectedColumns()
    {
        // E1
        ColumnsOf<Config>().Should().BeEquivalentTo("Id", "Name", "Code", "Value", "InputType");
        TableOf<Config>().Should().Be("Config");
    }

    [Fact]
    public void ConfigIdIsUuidPrimaryKey()
    {
        // E2
        ShouldBeUuidPrimaryKey<Config>();
    }

    [Fact]
    public void ConfigInputTypeIsStoredAsText()
    {
        // E3
        var inputType = PropertyOf<Config>(nameof(Config.InputType));

        inputType.GetColumnType().Should().Be(TEXT_TYPE);
        inputType.GetTypeMapping().Converter.Should().NotBeNull();
        inputType.GetTypeMapping().Converter!.ProviderClrType.Should().Be<string>();
    }

    [Fact]
    public void ConfigSeedHasFourRows()
    {
        // E4
        var seedRows = EntityOf<Config>().GetSeedData().ToList();

        seedRows.Should().HaveCount(ExpectedSeed.Length);
        seedRows.Select(row => row[ID]).Should().OnlyHaveUniqueItems().And.NotContain(Guid.Empty);
    }

    [Theory]
    [InlineData("RotationCount")] // E5
    [InlineData("RotationPeriod")] // E6
    [InlineData("ReinforcementPeriod")] // E7
    [InlineData("NotificationPeriod")] // E8
    public void ConfigSeedRowHasExpectedValues(string code)
    {
        // E5, E6, E7, E8
        var expected = ExpectedSeed.Single(row => row.Code == code);

        var seedRow = EntityOf<Config>().GetSeedData().Single(row => (string?)row[nameof(Config.Code)] == code);

        seedRow[nameof(Config.Name)].Should().Be(expected.Name);
        seedRow[nameof(Config.Value)].Should().Be(expected.Value);
        seedRow[nameof(Config.InputType)].Should().Be(expected.InputType);
    }

    [Fact]
    public void ConfigCodeIsUnique()
    {
        // E9
        UniqueIndexColumnsOf<Config>().Should().ContainSingle().Which.Should().Equal(nameof(Config.Code));
    }

    [Fact]
    public void InputTypeHasExpectedMembers()
    {
        // E10
        Enum.GetNames<InputType>().Should().Equal("CheckboxList", "Radiobutton", "String", "Number", "Date");
    }

    [Fact]
    public void WordHistoryTableHasExpectedColumns()
    {
        // F1
        ColumnsOf<WordHistory>().Should().BeEquivalentTo("Id", "WordId", "IsKnown", "Date");
        TableOf<WordHistory>().Should().Be("WordHistory");
    }

    [Fact]
    public void WordHistoryIdIsUuidPrimaryKey()
    {
        // F2
        ShouldBeUuidPrimaryKey<WordHistory>();
    }

    [Fact]
    public void WordHistoryDateIsTimestamptz()
    {
        // F3
        ColumnTypeOf<WordHistory>(nameof(WordHistory.Date)).Should().BeOneOf(TIMESTAMPTZ_TYPES);
    }

    [Fact]
    public void WordHistoryCascadesWhenWordIsDeleted()
    {
        // F4, F5
        ShouldCascadeFromWord<WordHistory>();
    }

    [Fact]
    public void ScheduleTableHasExpectedColumns()
    {
        // G1
        ColumnsOf<Schedule>().Should().BeEquivalentTo("Id", "StartDate", "EndDate");
        TableOf<Schedule>().Should().Be("Schedule");
        ShouldBeUuidPrimaryKey<Schedule>();
    }

    [Fact]
    public void ScheduleDatesAreRequiredTimestamptz()
    {
        // G2
        foreach (var name in new[] { nameof(Schedule.StartDate), nameof(Schedule.EndDate) })
        {
            ColumnTypeOf<Schedule>(name).Should().BeOneOf(TIMESTAMPTZ_TYPES);
            PropertyOf<Schedule>(name).IsNullable.Should().BeFalse();
        }
    }

    [Fact]
    public void ScheduleHasEndDateAfterStartDateCheck()
    {
        // G4, G5
        var checkConstraint = EntityOf<Schedule>().GetCheckConstraints().Should().ContainSingle().Subject;

        checkConstraint.Name.Should().Be(CHECK_CONSTRAINT_NAME);
        checkConstraint.Sql.Should().Be(CHECK_CONSTRAINT_SQL);
    }

    [Fact]
    public void PushSubscriptionTableHasExpectedColumns()
    {
        // H1
        ColumnsOf<PushSubscription>().Should().BeEquivalentTo("Id", "Endpoint", "P256dh", "Auth", "CreatedDate");
        TableOf<PushSubscription>().Should().Be("PushSubscription");
        ShouldBeUuidPrimaryKey<PushSubscription>();
    }

    [Fact]
    public void PushSubscriptionKeysAreText()
    {
        // H2
        ColumnTypeOf<PushSubscription>(nameof(PushSubscription.Endpoint)).Should().Be(TEXT_TYPE);
        ColumnTypeOf<PushSubscription>(nameof(PushSubscription.P256dh)).Should().Be(TEXT_TYPE);
        ColumnTypeOf<PushSubscription>(nameof(PushSubscription.Auth)).Should().Be(TEXT_TYPE);
    }

    [Fact]
    public void PushSubscriptionCreatedDateIsTimestamptz()
    {
        // H3
        ColumnTypeOf<PushSubscription>(nameof(PushSubscription.CreatedDate)).Should().BeOneOf(TIMESTAMPTZ_TYPES);
    }

    [Fact]
    public void OnlyRotatedWordsWordIdAndConfigCodeAreUnique()
    {
        // C13, D7, E9
        var uniqueColumns = Model.GetEntityTypes()
            .SelectMany(entity => entity.GetIndexes().Where(index => index.IsUnique))
            .Select(index => $"{index.DeclaringEntityType.GetTableName()}.{string.Join(',', index.Properties.Select(property => property.GetColumnName()))}");

        uniqueColumns.Should().BeEquivalentTo("RotatedWords.WordId", "Config.Code");
    }

    [Fact]
    public void ModelHasOnlySixTables()
    {
        // B6
        Model.GetEntityTypes().Select(entity => entity.GetTableName()).Should().BeEquivalentTo(
            "Words", "RotatedWords", "Config", "WordHistory", "Schedule", "PushSubscription");
    }

    [Fact]
    public void NoControllerExists()
    {
        // K1 until Phase 2: no endpoint at all. Since Phase 2 the endpoints are minimal APIs, so only controllers stay out.
        ApiTypes().Where(type => typeof(ControllerBase).IsAssignableFrom(type)).Should().BeEmpty();
    }

    [Fact]
    public void OnlyNotificationJobIsQuartzJob()
    {
        // K2 until Phase 3. Since Phase 4 the timed task is the one Quartz.NET job.
        ApiTypes().Where(type => typeof(IJob).IsAssignableFrom(type)).Should().Equal(typeof(FuXi.Api.Push.NotificationJob));
    }

    [Fact]
    public void NoRepositoryClassExists()
    {
        // K3 until Phase 2, now Phase 2 scenario T3: the services use FuXiDbContext directly.
        ApiTypes().Where(type => type.Name.EndsWith(REPOSITORY_SUFFIX, StringComparison.Ordinal)).Should().BeEmpty();
    }

    public void Dispose() => context.Dispose();

    private static readonly SeedRow[] ExpectedSeed =
    [
        new("Rotation Count", "RotationCount", "20", InputType.Number),
        new("Rotation period", "RotationPeriod", "15", InputType.Number),
        new("Reinforcement period", "ReinforcementPeriod", "10800", InputType.Number),
        new("Notification period", "NotificationPeriod", "15", InputType.Number),
    ];

    private sealed record SeedRow(string Name, string Code, string Value, InputType InputType);

    private IEntityType EntityOf<TEntity>() =>
        Model.FindEntityType(typeof(TEntity)) ?? throw new InvalidOperationException($"{typeof(TEntity).Name} is not mapped.");

    private IProperty PropertyOf<TEntity>(string name) =>
        EntityOf<TEntity>().FindProperty(name) ?? throw new InvalidOperationException($"{name} is not mapped.");

    private string? TableOf<TEntity>() => EntityOf<TEntity>().GetTableName();

    private IEnumerable<string> ColumnsOf<TEntity>() =>
        EntityOf<TEntity>().GetProperties().Select(property => property.GetColumnName());

    private string? ColumnTypeOf<TEntity>(string name) => PropertyOf<TEntity>(name).GetColumnType();

    private IEnumerable<IEnumerable<string>> UniqueIndexColumnsOf<TEntity>() =>
        EntityOf<TEntity>().GetIndexes()
            .Where(index => index.IsUnique)
            .Select(index => index.Properties.Select(property => property.GetColumnName()));

    private void ShouldBeUuidPrimaryKey<TEntity>()
    {
        var key = EntityOf<TEntity>().FindPrimaryKey();
        key.Should().NotBeNull();
        key!.Properties.Should().ContainSingle().Which.Name.Should().Be(ID);

        var id = PropertyOf<TEntity>(ID);
        id.GetColumnType().Should().Be(UUID_TYPE);
        id.GetDefaultValueSql().Should().Be(UUID_DEFAULT_SQL);
    }

    private void ShouldCascadeFromWord<TEntity>()
    {
        var foreignKey = EntityOf<TEntity>().GetForeignKeys().Should().ContainSingle().Subject;

        foreignKey.PrincipalEntityType.ClrType.Should().Be<Word>();
        foreignKey.Properties.Should().ContainSingle().Which.Name.Should().Be(WORD_ID);
        foreignKey.PrincipalKey.Properties.Should().ContainSingle().Which.Name.Should().Be(ID);
        foreignKey.DeleteBehavior.Should().Be(DeleteBehavior.Cascade);
        foreignKey.IsRequired.Should().BeTrue();
    }

    private static IEnumerable<Type> ApiTypes() => typeof(Program).Assembly.GetTypes();
}
