namespace FuXi.Api.Tests.Api;

/// <summary>The query and JSON names of the API contract.</summary>
public static class ApiFields
{
    public const string ID = "id";
    public const string NAME = "name";
    public const string TRANSLATION = "translation";
    public const string COUNTER = "counter";
    public const string IS_REINFORCEMENT = "isReinforcement";
    public const string LAST_SHOWN_DATE = "lastShownDate";
    public const string CONTENT = "content";
    public const string IS_KNOWN = "isKnown";
    public const string IS_ROTATED = "isRotated";
    public const string DATE = "date";
    public const string SHOWN_COUNT = "shownCount";
    public const string KNOWN_COUNT = "knownCount";
    public const string CONFIG_ID = "configId";
    public const string CODE = "code";
    public const string VALUE = "value";
    public const string INPUT_TYPE = "inputType";
    public const string START_DATE = "startDate";
    public const string END_DATE = "endDate";
    public const string PUBLIC_KEY = "publicKey";
    public const string STATUS = "status";

    public const string WORD_IDS = "wordIds";
    public const string WORD_ID = "wordId";
    public const string PERIOD = "period";

    /// <summary>The fields of a GetCardWords and GetWordsByActive item.</summary>
    public static readonly string[] CARD_WORD_FIELDS =
        [ID, NAME, TRANSLATION, COUNTER, IS_REINFORCEMENT, LAST_SHOWN_DATE, CONTENT];
}
