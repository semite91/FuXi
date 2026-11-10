namespace FuXi.Api.Database.Configurations;

/// <summary>Database default values shared by the entity configurations.</summary>
public static class ColumnDefaults
{
    public const string UUID_DEFAULT_SQL = "gen_random_uuid()";
}
