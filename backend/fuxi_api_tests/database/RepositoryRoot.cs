namespace FuXi.Api.Tests.Database;

/// <summary>Finds the repository root by walking up to the folder that holds backend/FuXi.slnx.</summary>
public static class RepositoryRoot
{
    private const string BACKEND_FOLDER = "backend";
    private const string SOLUTION_FILE = "FuXi.slnx";

    public static string Find()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !HasSolution(directory))
        {
            directory = directory.Parent;
        }

        return directory?.FullName
            ?? throw new InvalidOperationException($"{BACKEND_FOLDER}/{SOLUTION_FILE} was not found above the test output.");
    }

    public static string Combine(params string[] parts) => Path.Combine([Find(), .. parts]);

    private static bool HasSolution(DirectoryInfo directory) =>
        File.Exists(Path.Combine(directory.FullName, BACKEND_FOLDER, SOLUTION_FILE));
}
