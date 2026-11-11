using System.Net;
using System.Xml.Linq;
using FluentAssertions;
using FuXi.Api.Tests.Database;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section A: the test libraries and the test host.</summary>
[Collection(nameof(SmokeTests))]
public sealed class SetupTests
{
    private const string BACKEND_FOLDER = "backend";
    private const string API_FOLDER = "fuxi_api";
    private const string TESTS_FOLDER = "fuxi_api_tests";
    private const string API_PROJECT_FILE = "FuXi.Api.csproj";
    private const string LOCK_FILE = "packages.lock.json";
    private const string PACKAGE_REFERENCE = "PackageReference";
    private const string INCLUDE = "Include";
    private const string MIGRATION_ON = "true";
    private static readonly string[] TEST_LIBRARIES =
        ["Microsoft.AspNetCore.Mvc.Testing", "Microsoft.Extensions.TimeProvider.Testing"];

    [Fact]
    public void BothTestLibrariesAreLocked()
    {
        // A2
        var lockFile = File.ReadAllText(RepositoryRoot.Combine(BACKEND_FOLDER, TESTS_FOLDER, LOCK_FILE));

        foreach (var library in TEST_LIBRARIES)
        {
            lockFile.Should().Contain(Quoted(library));
        }
    }

    [Fact]
    public void ApiProjectReferencesNoTestLibrary()
    {
        // A3
        var project = XDocument.Load(RepositoryRoot.Combine(BACKEND_FOLDER, API_FOLDER, API_PROJECT_FILE));
        var lockFile = File.ReadAllText(RepositoryRoot.Combine(BACKEND_FOLDER, API_FOLDER, LOCK_FILE));

        var references = project.Descendants(PACKAGE_REFERENCE).Select(element => (string?)element.Attribute(INCLUDE));

        references.Should().NotContain(TEST_LIBRARIES);
        foreach (var library in TEST_LIBRARIES)
        {
            lockFile.Should().NotContain(Quoted(library));
        }
    }

    [Fact]
    public async Task ApiStartsWithoutDatabaseWhenMigrationIsOff()
    {
        // A4
        using var api = new NowApi();

        await api.Client.GetApiAsync(ApiRoutes.GET_VAPID_PUBLIC_KEY).ShouldHaveStatusAsync(HttpStatusCode.OK);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(MIGRATION_ON)]
    public void StartupMigrationRunsUnlessSwitchedOff(string? migrateAtStartup)
    {
        // A5: the migration is the only startup step that opens a connection, and no database is listening.
        using var api = new NowApi(new NowApiSettings { MigrateAtStartup = migrateAtStartup });

        var start = api.Start;

        var failure = start.Should().Throw<Exception>().Which;
        StartupFailure.Chain(failure).Should().Contain(exception => exception is NpgsqlException);
    }

    [Fact]
    public void ClockIsRegisteredAsSystemTimeProvider()
    {
        // A6
        using var api = new NowApi(new NowApiSettings { ReplacesServices = false });

        api.Services.GetRequiredService<TimeProvider>().Should().BeSameAs(TimeProvider.System);
    }

    private static string Quoted(string value) => $"\"{value}\"";
}
