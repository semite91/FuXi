namespace FuXi.Api;

/// <summary>Reads the origins that may call the API.</summary>
public static class CorsSettings
{
    public const string ORIGINS_KEY = "FUXI_CORS_ORIGINS";
    public const char ORIGIN_SEPARATOR = ',';
}
