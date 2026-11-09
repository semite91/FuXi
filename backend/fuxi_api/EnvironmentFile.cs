using DotNetEnv;

namespace FuXi.Api;

/// <summary>Loads the git-ignored env file into the process environment.</summary>
public static class EnvironmentFile
{
    public const string PATH_VARIABLE = "FUXI_ENV_FILE";
    public const string DEFAULT_FILE_NAME = ".env";

    /// <summary>
    /// Loads the file named by FUXI_ENV_FILE, or the nearest .env file above the
    /// current directory. Values from the file win over existing variables.
    /// </summary>
    public static void Load()
    {
        var path = Environment.GetEnvironmentVariable(PATH_VARIABLE);
        if (string.IsNullOrWhiteSpace(path))
        {
            Env.TraversePath().Load(DEFAULT_FILE_NAME);
            return;
        }

        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"{PATH_VARIABLE} points to a missing file.", path);
        }

        Env.Load(path);
    }
}
