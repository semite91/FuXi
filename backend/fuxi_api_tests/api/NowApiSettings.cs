namespace FuXi.Api.Tests.Api;

/// <summary>The startup values of a host without a database. A null value leaves the variable out.</summary>
public sealed record NowApiSettings
{
    public const string DEFAULT_ORIGIN = "https://fuxi.test";
    public const string MIGRATION_OFF = "false";

    public string? CorsOrigins { get; init; } = DEFAULT_ORIGIN;

    public string? MigrateAtStartup { get; init; } = MIGRATION_OFF;

    public string? VapidPublicKey { get; init; }

    public string? VapidPrivateKey { get; init; }

    public string? NotionClientId { get; init; }

    public string? NotionClientSecret { get; init; }

    public string? NotionRedirectUri { get; init; }

    public string? GoogleClientId { get; init; }

    public string? GoogleClientSecret { get; init; }

    public string? GoogleRedirectUri { get; init; }

    public string? SpotifyClientId { get; init; }

    public string? SpotifyClientSecret { get; init; }

    public string? SpotifyRedirectUri { get; init; }

    public string? AppUrl { get; init; }

    /// <summary>False keeps the API's own TimeProvider and INotificationTimer.</summary>
    public bool ReplacesServices { get; init; } = true;
}
