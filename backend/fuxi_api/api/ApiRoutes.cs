namespace FuXi.Api;

/// <summary>The route of every API endpoint. Each name matches project.md.</summary>
public static class ApiRoutes
{
    public const string PREFIX = "/api";

    public const string GET_CARD_WORDS = PREFIX + "/GetCardWords";
    public const string GET_WORDS_BY_ACTIVE = PREFIX + "/GetWordsByActive";
    public const string GET_WORD_HISTORY = PREFIX + "/GetWordHistory";
    public const string GET_WORDS_BY_FILTER = PREFIX + "/GetWordsByFilter";
    public const string UPDATE_WORD_CONTENT = PREFIX + "/UpdateWordContent";
    public const string UPDATE_WORD_KNOWN_STATUS = PREFIX + "/UpdateWordKnownStatus";
    public const string UPDATE_IS_REINFORCEMENT = PREFIX + "/UpdateIsReinforcement";

    public const string GET_CONFIGS = PREFIX + "/GetConfigs";
    public const string UPDATE_CONFIG = PREFIX + "/UpdateConfig";
    public const string UPDATE_NOTIFICATION_PERIOD = PREFIX + "/UpdateNotificationPeriod";

    public const string GET_SCHEDULE = PREFIX + "/GetSchedule";
    public const string UPDATE_SCHEDULE = PREFIX + "/UpdateSchedule";
    public const string DELETE_SCHEDULE = PREFIX + "/DeleteSchedule";

    public const string GET_VAPID_PUBLIC_KEY = PREFIX + "/GetVapidPublicKey";
    public const string SAVE_PUSH_SUBSCRIPTION = PREFIX + "/SavePushSubscription";
}
