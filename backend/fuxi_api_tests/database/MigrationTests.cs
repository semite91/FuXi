using System.Text.Json;
using System.Xml.Linq;
using FluentAssertions;
using FuXi.Api.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Xunit;

namespace FuXi.Api.Tests.Database;

/// <summary>Reads the migrations and project files. No database is needed.</summary>
public sealed class MigrationTests : IDisposable
{
    private const string INITIAL_MIGRATION_SUFFIX = "_Initial";
    private const string MIGRATIONS_NAMESPACE = "FuXi.Api.Database.Migrations";
    private const string CREATE_TABLE_TEMPLATE = "CREATE TABLE \"{0}\"";
    private const string BACKEND_FOLDER = "backend";
    private const string API_FOLDER = "fuxi_api";
    private const string PROJECT_FILE = "FuXi.Api.csproj";
    private const string LOCK_FILE = "packages.lock.json";
    private const string DESIGN_PACKAGE = "Microsoft.EntityFrameworkCore.Design";
    private const string PACKAGE_REFERENCE = "PackageReference";
    private const string INCLUDE = "Include";
    private const string PRIVATE_ASSETS = "PrivateAssets";
    private const string ALL_ASSETS = "all";
    private const string TOOL_MANIFEST = "dotnet-tools.json";
    private const string TOOL_MANIFEST_FOLDER = ".config";
    private const string TOOLS = "tools";
    private const string EF_TOOL = "dotnet-ef";
    private const string VERSION = "version";
    private const string EXACT_VERSION_PATTERN = @"^\d+\.\d+\.\d+$";
    private static readonly string[] TABLE_NAMES =
        ["Words", "RotatedWords", "Config", "WordHistory", "Schedule", "PushSubscription"];

    private readonly FuXiDbContext context = ModelOnlyContext.Create();

    [Fact]
    public void OneInitialMigrationExists()
    {
        // B1
        var migrations = context.GetService<IMigrationsAssembly>().Migrations;

        var migration = migrations.Should().ContainSingle().Subject;
        migration.Key.Should().EndWith(INITIAL_MIGRATION_SUFFIX);
        migration.Value.Namespace.Should().Be(MIGRATIONS_NAMESPACE);
    }

    [Fact]
    public void NoModelChangeIsPending()
    {
        // B2
        context.Database.HasPendingModelChanges().Should().BeFalse();
    }

    [Fact]
    public void MigrationScriptCreatesSixTables()
    {
        // B6
        var script = context.GetService<IMigrator>().GenerateScript();

        foreach (var tableName in TABLE_NAMES)
        {
            script.Should().Contain(string.Format(CREATE_TABLE_TEMPLATE, tableName));
        }
    }

    [Fact]
    public void EfToolIsPinnedToExactVersion()
    {
        // A2
        var manifestPath = ToolManifestPath();
        using var manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));

        var version = manifest.RootElement.GetProperty(TOOLS).GetProperty(EF_TOOL).GetProperty(VERSION).GetString();

        version.Should().MatchRegex(EXACT_VERSION_PATTERN);
    }

    [Fact]
    public void DesignPackageIsLocked()
    {
        // A3
        var lockFile = File.ReadAllText(RepositoryRoot.Combine(BACKEND_FOLDER, API_FOLDER, LOCK_FILE));

        lockFile.Should().Contain($"\"{DESIGN_PACKAGE}\"");
    }

    [Fact]
    public void DesignPackageIsNotPartOfRuntimeOutput()
    {
        // A4
        var project = XDocument.Load(RepositoryRoot.Combine(BACKEND_FOLDER, API_FOLDER, PROJECT_FILE));

        var reference = project.Descendants(PACKAGE_REFERENCE)
            .Should().ContainSingle(element => (string?)element.Attribute(INCLUDE) == DESIGN_PACKAGE).Subject;

        PrivateAssetsOf(reference).Should().BeEquivalentTo(ALL_ASSETS);
    }

    public void Dispose() => context.Dispose();

    // The attribute and the child element are both valid MSBuild forms.
    private static string? PrivateAssetsOf(XElement reference) =>
        ((string?)reference.Attribute(PRIVATE_ASSETS) ?? reference.Element(PRIVATE_ASSETS)?.Value)?.Trim();

    private static string ToolManifestPath()
    {
        string[] candidates =
        [
            RepositoryRoot.Combine(BACKEND_FOLDER, TOOL_MANIFEST),
            RepositoryRoot.Combine(BACKEND_FOLDER, TOOL_MANIFEST_FOLDER, TOOL_MANIFEST),
        ];

        return candidates.FirstOrDefault(File.Exists)
            ?? throw new FileNotFoundException($"{TOOL_MANIFEST} was not found in the backend folder.");
    }
}
