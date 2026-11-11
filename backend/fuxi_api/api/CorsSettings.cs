namespace FuXi.Api;

/// <summary>Reads the origins that may call the API.</summary>
public static class CorsSettings
{
    public const string ORIGINS_KEY = "FUXI_CORS_ORIGINS";
    public const char ORIGIN_SEPARATOR = ',';

    /// <summary>The HTTP methods the API endpoints use.</summary>
    public static readonly string[] ALLOWED_METHODS = [HttpMethods.Get, HttpMethods.Post, HttpMethods.Delete];

    /// <summary>Returns the configured origins, or throws when none is configured.</summary>
    public static string[] ReadOrigins(IConfiguration configuration)
    {
        var origins = (configuration[ORIGINS_KEY] ?? string.Empty).Split(
            ORIGIN_SEPARATOR, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        return origins.Length == 0
            ? throw new InvalidOperationException($"Configuration value {ORIGINS_KEY} is missing.")
            : origins;
    }
}
