using System.Net;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.Push;
using PushServiceClientException = Lib.Net.Http.WebPush.PushServiceClientException;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 sections D, E and F (test_scenarios_2026_11_12_22_06): one run of the timed task on the test database.</summary>
[Collection(nameof(SmokeTests))]
public sealed class NotificationServiceTests : IDisposable
{
    private const string PUBLIC_KEY = "public-key-of-a-test";
    private const string PRIVATE_KEY = "private-key-of-a-test";
    private const string SUBJECT = "mailto:learner@fuxi.test";
    private const string FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send/first";
    private const string MOZILLA_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/second";
    private const string UNKNOWN_HOST_ENDPOINT = "https://push.example.com/third";
    private const string APPLE = "apple";
    private const string RIVER = "river";
    private const string TITLE_SEPARATOR = ", ";
    private const char WORD_ID_SEPARATOR = ',';
    private const string TITLE_FIELD = "title";
    private const string WORD_IDS_FIELD = "wordIds";
    private const string GONE = "Push subscription has expired.";
    private const string SERVER_ERROR = "Push service failed.";
    private const string EF_COMMAND_CATEGORY = "Microsoft.EntityFrameworkCore.Database.Command";
    private const string SCHEDULE_TABLE_SQL = "FROM \"Schedule\"";
    private const string START_DATE_FILTER_SQL = "\"StartDate\" <=";
    private const string END_DATE_FILTER_SQL = "\"EndDate\" >";
    private const string DELETE_SUBSCRIPTION_SQL = "DELETE FROM \"PushSubscription\"";
    private const int WINDOW_HOURS = 1;
    private const int ROTATION_PERIOD_MINUTES = TestData.SEEDED_ROTATION_PERIOD;
    private const int ONE_MINUTE = 1;
    private const int LONG_NAME_LENGTH = 300;
    private const int LONG_WORD_COUNT = 20;
    private const char LONG_NAME_LETTER = 'x';

    private static readonly DateTimeOffset Now = TestData.Now;

    // Only reached when a test fails: a held push that is never called.
    private static readonly TimeSpan WaitLimit = TimeSpan.FromSeconds(10);

    private readonly DatabaseApi api = new();

    public NotificationServiceTests()
    {
        api.Settings[VapidSettings.PUBLIC_KEY_KEY] = PUBLIC_KEY;
        api.Settings[VapidSettings.PRIVATE_KEY_KEY] = PRIVATE_KEY;
        api.Settings[VapidSettings.SUBJECT_KEY] = SUBJECT;
    }

    [Fact]
    public async Task NoWindowSendsNothingAndDoesNotReadWords()
    {
        // D1: GetNotificationWords would top up the Rotation, so an empty Rotation proves it was not called.
        api.Arrange(context =>
        {
            TestData.AddWord(context, APPLE);
            TestData.AddPushSubscription(context, FCM_ENDPOINT);
        });

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
        api.Read(context => context.RotatedWords.Count()).Should().Be(0);
    }

    [Fact]
    public async Task WindowThatHoldsNowContinuesToWords()
    {
        // D2
        ArrangeDueWordAndSubscription();
        AddWindow(Now.AddHours(-WINDOW_HOURS), Now.AddHours(WINDOW_HOURS));

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().ContainSingle();
    }

    [Fact]
    public async Task WindowThatEndedBeforeNowSendsNothing()
    {
        // D3
        ArrangeDueWordAndSubscription();
        AddWindow(Now.AddHours(-WINDOW_HOURS * 2), Now.AddHours(-WINDOW_HOURS));

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
    }

    [Fact]
    public async Task WindowThatStartsAfterNowSendsNothing()
    {
        // D4
        ArrangeDueWordAndSubscription();
        AddWindow(Now.AddHours(WINDOW_HOURS), Now.AddHours(WINDOW_HOURS * 2));

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
    }

    [Fact]
    public async Task WindowThatStartsAtNowContinues()
    {
        // D5
        ArrangeDueWordAndSubscription();
        AddWindow(Now, Now.AddHours(WINDOW_HOURS));

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().ContainSingle();
    }

    [Fact]
    public async Task WindowThatEndsAtNowSendsNothing()
    {
        // D6
        ArrangeDueWordAndSubscription();
        AddWindow(Now.AddHours(-WINDOW_HOURS), Now);

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
    }

    [Fact]
    public async Task WindowCheckIsFilteredInSql()
    {
        // D7: the executed SQL carries both date conditions, so no Schedule row is filtered in memory.
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.Logs.Of(EF_COMMAND_CATEGORY).Select(entry => entry.Message)
            .Should().Contain(sql => sql.Contains(SCHEDULE_TABLE_SQL) && sql.Contains(START_DATE_FILTER_SQL) && sql.Contains(END_DATE_FILTER_SQL));
    }

    [Fact]
    public async Task WordsAreReadWithClockNow()
    {
        // E1: one Word is Due exactly at now and one a minute later; the real clock would make both Due.
        var dueNow = api.Arrange(context => AddShownWord(context, APPLE, Now.AddMinutes(-ROTATION_PERIOD_MINUTES)));
        api.Arrange(context => AddShownWord(context, RIVER, Now.AddMinutes(-ROTATION_PERIOD_MINUTES + ONE_MINUTE)));
        api.Arrange(context => TestData.AddPushSubscription(context, FCM_ENDPOINT));
        AddOpenWindow();

        await api.SendDueWordsAsync();

        WordIdsOf(api.PushSender.Sent.Single().Payload).Should().Equal(dueNow.Id);
    }

    [Fact]
    public async Task NoDueWordSendsNothing()
    {
        // E2: the only Word was shown a minute ago, so it is not Due.
        api.Arrange(context =>
        {
            AddShownWord(context, APPLE, Now.AddMinutes(-ONE_MINUTE));
            TestData.AddPushSubscription(context, FCM_ENDPOINT);
        });
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
    }

    [Fact]
    public async Task TitleIsWordNamesJoinedWithComma()
    {
        // E3
        ArrangeAppleAndRiver();

        await api.SendDueWordsAsync();

        var title = TitleOf(api.PushSender.Sent.Single().Payload);
        title.Split(TITLE_SEPARATOR).Should().BeEquivalentTo(APPLE, RIVER);
        title.Should().BeOneOf(APPLE + TITLE_SEPARATOR + RIVER, RIVER + TITLE_SEPARATOR + APPLE);
    }

    [Fact]
    public async Task WordIdsAreJoinedWithCommaInOrderOfNames()
    {
        // E4
        var words = ArrangeAppleAndRiver();

        await api.SendDueWordsAsync();

        var payload = api.PushSender.Sent.Single().Payload;
        var namesById = words.ToDictionary(word => word.Id, word => word.Name);
        WordIdsOf(payload).Select(id => namesById[id]).Should().Equal(TitleOf(payload).Split(TITLE_SEPARATOR));
    }

    [Fact]
    public async Task IgnoredNotificationIsSentAgainWithSameWords()
    {
        // E6
        ArrangeAppleAndRiver();

        await api.SendDueWordsAsync();
        await api.SendDueWordsAsync();

        var payloads = api.PushSender.Sent.Select(sent => sent.Payload).ToList();
        payloads.Should().HaveCount(2);
        payloads[1].Should().Be(payloads[0]);
    }

    [Fact]
    public async Task RunChangesNoRotationOrShownCount()
    {
        // E7
        ArrangeAppleAndRiver();
        api.Arrange(context => AddShownWord(context, "shown", Now.AddMinutes(-ROTATION_PERIOD_MINUTES)));
        var before = ReadRotationState();

        await api.SendDueWordsAsync();

        ReadRotationState().Should().BeEquivalentTo(before);
    }

    [Fact]
    public async Task FullPayloadHoldsFirstWordsThatFit()
    {
        // E8: twenty Words of 300 letters do not fit in one push message.
        var words = ArrangeLongDueWords();

        await api.SendDueWordsAsync();

        var payload = api.PushSender.Sent.Single().Payload;
        Encoding.UTF8.GetByteCount(payload).Should().BeLessThanOrEqualTo(NotificationPayload.MAX_PAYLOAD_BYTES);
        var namesById = words.ToDictionary(word => word.Id, word => word.Name);
        var sentIds = WordIdsOf(payload);
        sentIds.Length.Should().BeInRange(1, LONG_WORD_COUNT - 1);
        sentIds.Select(id => namesById[id]).Should().Equal(TitleOf(payload).Split(TITLE_SEPARATOR));
    }

    [Fact]
    public async Task WordsLeftOutOfFullPayloadStayDue()
    {
        // E9: the run changes no data, so the left-out Words are still Due for a later run.
        var words = ArrangeLongDueWords();
        var before = ReadRotationState();

        await api.SendDueWordsAsync();

        var leftOut = words.Select(word => word.Id).Except(WordIdsOf(api.PushSender.Sent.Single().Payload)).ToList();
        leftOut.Should().NotBeEmpty();
        ReadRotationState().Should().BeEquivalentTo(before);
        (await api.GetNotificationWordsAsync(Now)).Select(word => word.Id).Should().Contain(leftOut);
    }

    [Fact]
    public async Task WordTooLongForOnePushSendsNothingAndLogsWarning()
    {
        // E8: not even the first Word fits, so nothing is sent this run.
        api.Arrange(context =>
        {
            var word = TestData.AddWord(context, new string(LONG_NAME_LETTER, NotificationPayload.MAX_PAYLOAD_BYTES));
            TestData.AddRotatedWord(context, word);
            TestData.AddPushSubscription(context, FCM_ENDPOINT);
        });
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().BeEmpty();
        api.Logs.Of(typeof(NotificationService).FullName!).Should().ContainSingle(entry => entry.Level == LogLevel.Warning);
    }

    [Fact]
    public async Task NoSubscriptionSendsNothingAndFailsNothing()
    {
        // F1
        api.Arrange(context => TestData.AddRotatedWords(context, 1));
        AddOpenWindow();

        var run = api.SendDueWordsAsync;

        await run.Should().NotThrowAsync();
        api.PushSender.Sent.Should().BeEmpty();
        ErrorLogs().Should().BeEmpty();
    }

    [Fact]
    public async Task EverySubscriptionIsCalledOnce()
    {
        // F2
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Select(sent => sent.Subscription.Endpoint).Should().BeEquivalentTo(FCM_ENDPOINT, MOZILLA_ENDPOINT);
    }

    [Fact]
    public async Task SendUsesSubscriptionKeysAndConfiguredVapidDetails()
    {
        // F3
        var subscription = ArrangeDueWordAndSubscription();
        AddOpenWindow();

        await api.SendDueWordsAsync();

        var sent = api.PushSender.Sent.Single();
        sent.Subscription.Endpoint.Should().Be(subscription.Endpoint);
        sent.Subscription.P256dh.Should().Be(subscription.P256dh);
        sent.Subscription.Auth.Should().Be(subscription.Auth);
        sent.Vapid.Should().Be(new VapidDetails(PUBLIC_KEY, PRIVATE_KEY, SUBJECT));
    }

    [Theory]
    [InlineData(HttpStatusCode.Gone)]
    [InlineData(HttpStatusCode.NotFound)]
    public async Task GoneOrNotFoundSubscriptionIsDeleted(HttpStatusCode statusCode)
    {
        // F4: 410 Gone and 404 Not Found both mean the push service no longer knows the subscription.
        ArrangeDueWordAndSubscription();
        AddOpenWindow();
        api.PushSender.FailFor(FCM_ENDPOINT, new PushServiceClientException(GONE, statusCode));

        await api.SendDueWordsAsync();

        StoredEndpoints().Should().BeEmpty();
    }

    [Fact]
    public async Task GoneAndNotFoundSubscriptionsAreDeletedWithOneStatement()
    {
        // F4: the deletes wait until every push of the run answered, then go to the database at once.
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();
        api.PushSender.FailFor(FCM_ENDPOINT, new PushServiceClientException(GONE, HttpStatusCode.Gone));
        api.PushSender.FailFor(MOZILLA_ENDPOINT, new PushServiceClientException(GONE, HttpStatusCode.NotFound));

        await api.SendDueWordsAsync();

        StoredEndpoints().Should().BeEmpty();
        api.Logs.Of(EF_COMMAND_CATEGORY).Count(entry => entry.Message.Contains(DELETE_SUBSCRIPTION_SQL)).Should().Be(1);
    }

    [Fact]
    public async Task OnlyGoneSubscriptionIsDeletedAndOtherStillReceivesPush()
    {
        // F5: the gone endpoint comes first or last; either way the other one is sent to and kept.
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();
        api.PushSender.FailFor(FCM_ENDPOINT, new PushServiceClientException(GONE, HttpStatusCode.Gone));

        await api.SendDueWordsAsync();

        StoredEndpoints().Should().Equal(MOZILLA_ENDPOINT);
        api.PushSender.Sent.Select(sent => sent.Subscription.Endpoint).Should().Contain(MOZILLA_ENDPOINT);
    }

    [Theory]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.Forbidden)]
    [InlineData(HttpStatusCode.RequestEntityTooLarge)]
    public async Task OtherFailureIsLoggedAndSubscriptionIsKept(HttpStatusCode statusCode)
    {
        // F6
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();
        api.PushSender.FailFor(FCM_ENDPOINT, new PushServiceClientException(SERVER_ERROR, statusCode));

        await api.SendDueWordsAsync();

        StoredEndpoints().Should().BeEquivalentTo(FCM_ENDPOINT, MOZILLA_ENDPOINT);
        api.PushSender.Sent.Select(sent => sent.Subscription.Endpoint).Should().Contain(MOZILLA_ENDPOINT);
        ErrorLogs().Should().ContainSingle().Which.Exception.Should().BeOfType<PushServiceClientException>();
    }

    [Fact]
    public async Task NetworkFailureIsLoggedAndSubscriptionIsKept()
    {
        // F6: a failure that is not an answer of the push service, such as a timeout.
        ArrangeDueWordAndSubscription();
        AddOpenWindow();
        api.PushSender.FailFor(FCM_ENDPOINT, new HttpRequestException(SERVER_ERROR));

        await api.SendDueWordsAsync();

        StoredEndpoints().Should().Equal(FCM_ENDPOINT);
        ErrorLogs().Should().ContainSingle();
    }

    [Fact]
    public async Task VapidAuthenticationIsBuiltOncePerRun()
    {
        // F11: one run for both subscriptions, disposed after the pushes.
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Should().HaveCount(2);
        api.PushSender.RunsStarted.Should().Be(1);
        api.PushSender.RunsDisposed.Should().Be(1);
    }

    [Fact]
    public async Task SlowEndpointDoesNotHoldOtherEndpoint()
    {
        // F12: both pushes are held; each is called while the other has not answered, so they are not sent one after another.
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, MOZILLA_ENDPOINT));
        AddOpenWindow();
        var fcmAnswer = api.PushSender.HoldFor(FCM_ENDPOINT);
        var mozillaAnswer = api.PushSender.HoldFor(MOZILLA_ENDPOINT);

        var run = api.SendDueWordsAsync();
        await Task.WhenAll(api.PushSender.CalledAsync(FCM_ENDPOINT), api.PushSender.CalledAsync(MOZILLA_ENDPOINT))
            .WaitAsync(WaitLimit, TestContext.Current.CancellationToken);

        run.IsCompleted.Should().BeFalse();
        fcmAnswer.SetResult();
        mozillaAnswer.SetResult();
        await run;
        api.PushSender.Sent.Should().HaveCount(2);
    }

    [Fact]
    public async Task EndpointOfUnknownHostIsNotCalled()
    {
        // F9: the row is written straight to the database, past the SavePushSubscription check.
        ArrangeDueWordAndSubscription();
        api.Arrange(context => TestData.AddPushSubscription(context, UNKNOWN_HOST_ENDPOINT));
        AddOpenWindow();

        await api.SendDueWordsAsync();

        api.PushSender.Sent.Select(sent => sent.Subscription.Endpoint).Should().Equal(FCM_ENDPOINT);
    }

    public void Dispose() => api.Dispose();

    private PushSubscription ArrangeDueWordAndSubscription() =>
        api.Arrange(context =>
        {
            TestData.AddRotatedWords(context, 1);

            return TestData.AddPushSubscription(context, FCM_ENDPOINT);
        });

    private IReadOnlyList<Word> ArrangeAppleAndRiver()
    {
        var words = api.Arrange(context =>
        {
            var apple = TestData.AddWord(context, APPLE);
            var river = TestData.AddWord(context, RIVER);
            TestData.AddRotatedWord(context, apple);
            TestData.AddRotatedWord(context, river);
            TestData.AddPushSubscription(context, FCM_ENDPOINT);

            return new[] { apple, river };
        });
        AddOpenWindow();

        return words;
    }

    private IReadOnlyList<Word> ArrangeLongDueWords()
    {
        var words = api.Arrange(context =>
        {
            TestData.AddPushSubscription(context, FCM_ENDPOINT);

            return TestData.AddRotatedWords(context, LONG_WORD_COUNT, new string(LONG_NAME_LETTER, LONG_NAME_LENGTH));
        });
        AddOpenWindow();

        return words;
    }

    private static Word AddShownWord(FuXiDbContext context, string name, DateTimeOffset lastShownDate)
    {
        var word = TestData.AddWord(context, name, shownCount: 1);
        TestData.AddRotatedWord(context, word, lastShownDate: lastShownDate);

        return word;
    }

    private void AddOpenWindow() => AddWindow(Now.AddHours(-WINDOW_HOURS), Now.AddHours(WINDOW_HOURS));

    private void AddWindow(DateTimeOffset startDate, DateTimeOffset endDate) =>
        api.Arrange(context => TestData.AddSchedule(context, startDate, endDate));

    private List<string> StoredEndpoints() =>
        api.Read(context => context.PushSubscriptions.AsNoTracking().Select(subscription => subscription.Endpoint).ToList());

    private object ReadRotationState() =>
        api.Read(context => new
        {
            Rotated = context.RotatedWords.AsNoTracking().OrderBy(rotated => rotated.WordId)
                .Select(rotated => new { rotated.WordId, rotated.Counter, rotated.LastShownDate }).ToList(),
            ShownCounts = context.Words.AsNoTracking().OrderBy(word => word.Id).Select(word => new { word.Id, word.ShownCount }).ToList(),
        });

    private IReadOnlyList<LogEntry> ErrorLogs() =>
        api.Logs.Of(typeof(NotificationService).FullName!).Where(entry => entry.Level >= LogLevel.Error).ToList();

    private static string TitleOf(string payload) => ReadField(payload, TITLE_FIELD);

    private static Guid[] WordIdsOf(string payload) =>
        ReadField(payload, WORD_IDS_FIELD).Split(WORD_ID_SEPARATOR).Select(Guid.Parse).ToArray();

    private static string ReadField(string payload, string field)
    {
        using var document = JsonDocument.Parse(payload);

        return document.RootElement.GetProperty(field).GetString()!;
    }
}
