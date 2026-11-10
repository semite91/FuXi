using DotNetEnv;

namespace FuXi.Api.Tests;

/// <summary>Remembers environment variables and restores them on dispose.</summary>
public sealed class EnvironmentScope : IDisposable
{
    private readonly Dictionary<string, string?> originalValues = [];

    public EnvironmentScope(IEnumerable<string> names) => Remember(names);

    /// <summary>Remembers every key the env file sets. The file is parsed without changing the environment.</summary>
    public void RememberKeysOf(string envFilePath) =>
        Remember(Env.NoEnvVars().Load(envFilePath).Select(pair => pair.Key));

    public void Dispose()
    {
        foreach (var (name, value) in originalValues)
        {
            Environment.SetEnvironmentVariable(name, value);
        }
    }

    // The first snapshot of a name wins, so a later call never captures an already changed value.
    private void Remember(IEnumerable<string> names)
    {
        foreach (var name in names)
        {
            originalValues.TryAdd(name, Environment.GetEnvironmentVariable(name));
        }
    }
}
