using FluentAssertions;
using FuXi.Api;
using Microsoft.Extensions.Configuration;
using Npgsql;
using Xunit;

namespace FuXi.Api.Tests;

// The env file changes process-wide variables, so these tests must not run in parallel.
[Collection(nameof(SmokeTests))]
public sealed class SmokeTests : IDisposable
{
    private const string TEST_DATABASE_NAME = "fuxi_smoke_test";
    private const string DEVELOPMENT_DATABASE_NAME = "fuxi_smoke";
    private const string INVALID_PORT = "abc";
    private static readonly string[] CHANGED_VARIABLES =
    [
        EnvironmentFile.PATH_VARIABLE,
        DatabaseSettings.HOST_KEY,
        DatabaseSettings.PORT_KEY,
        DatabaseSettings.NAME_KEY,
        DatabaseSettings.USER_KEY,
        DatabaseSettings.PASSWORD_KEY,
    ];
    private const string ENV_FILE_TEMPLATE = """
        FUXI_DB_HOST=127.0.0.1
        FUXI_DB_PORT=5432
        FUXI_DB_NAME={0}
        FUXI_DB_USER=smoke
        FUXI_DB_PASSWORD=smoke
        """;

    private readonly string envFilePath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid()}.env");
    private readonly EnvironmentScope environment = new(CHANGED_VARIABLES);

    [Fact]
    public void TestProjectRuns()
    {
        typeof(Program).Assembly.GetName().Name.Should().Be("FuXi.Api");
    }

    [Fact]
    public void ConnectionStringUsesDatabaseOfSelectedEnvFile()
    {
        Environment.SetEnvironmentVariable(DatabaseSettings.NAME_KEY, DEVELOPMENT_DATABASE_NAME);
        File.WriteAllText(envFilePath, string.Format(ENV_FILE_TEMPLATE, TEST_DATABASE_NAME));
        Environment.SetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE, envFilePath);

        EnvironmentFile.Load();
        var configuration = new ConfigurationBuilder().AddEnvironmentVariables().Build();
        var connectionString = DatabaseSettings.BuildConnectionString(configuration);

        new NpgsqlConnectionStringBuilder(connectionString).Database.Should().Be(TEST_DATABASE_NAME);
    }

    [Fact]
    public void LoadFailsWhenSelectedEnvFileIsMissing()
    {
        Environment.SetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE, envFilePath);

        var load = EnvironmentFile.Load;

        load.Should().Throw<FileNotFoundException>();
    }

    [Fact]
    public void ConnectionStringFailsWhenPortIsNotNumber()
    {
        var values = CHANGED_VARIABLES.ToDictionary(name => name, _ => (string?)INVALID_PORT);
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(values).Build();

        var build = () => DatabaseSettings.BuildConnectionString(configuration);

        build.Should().Throw<InvalidOperationException>().WithMessage($"*{DatabaseSettings.PORT_KEY}*");
    }

    public void Dispose()
    {
        environment.Dispose();
        File.Delete(envFilePath);
    }
}
