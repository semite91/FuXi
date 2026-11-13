using System.Buffers.Text;
using FluentAssertions;
using FuXi.Api.Push;
using Xunit;

namespace FuXi.Api.Tests.Api.Push;

/// <summary>Phase 4 section B (test_scenarios_2026_11_12_22_06): the generate-vapid-keys command.</summary>
[Collection(nameof(SmokeTests))]
public sealed class VapidKeyGeneratorTests : IDisposable
{
    private const int P256_PUBLIC_KEY_LENGTH = 65;
    private const int P256_PRIVATE_KEY_LENGTH = 32;
    private const byte UNCOMPRESSED_POINT_MARKER = 4;
    private const string MISSING_ENV_FILE = "/nonexistent/fuxi-vapid-command.env";
    private const char ASSIGNMENT = '=';
    private const string URL_SAFE_BASE64_PATTERN = "^[A-Za-z0-9_-]+$";
    private static readonly TimeSpan CommandTimeout = TimeSpan.FromSeconds(30);

    private readonly EnvironmentScope environment = new([EnvironmentFile.PATH_VARIABLE]);

    [Fact]
    public void CommandPrintsPublicAndPrivateKeyInUrlSafeBase64()
    {
        // B1
        var lines = RunCommand();

        lines.Should().HaveCount(2);
        lines[0].Should().StartWith(VapidSettings.PUBLIC_KEY_KEY + ASSIGNMENT);
        lines[1].Should().StartWith(VapidSettings.PRIVATE_KEY_KEY + ASSIGNMENT);
        ValueOf(lines[0]).Should().MatchRegex(URL_SAFE_BASE64_PATTERN);
        ValueOf(lines[1]).Should().MatchRegex(URL_SAFE_BASE64_PATTERN);
    }

    [Fact]
    public void PublicKeyIsUncompressedP256Point()
    {
        // B2
        var publicKey = Base64Url.DecodeFromChars(VapidKeyGenerator.Generate().PublicKey);

        publicKey.Should().HaveCount(P256_PUBLIC_KEY_LENGTH);
        publicKey[0].Should().Be(UNCOMPRESSED_POINT_MARKER);
    }

    [Fact]
    public void PrivateKeyIs32Bytes()
    {
        // B3
        var privateKey = Base64Url.DecodeFromChars(VapidKeyGenerator.Generate().PrivateKey);

        privateKey.Should().HaveCount(P256_PRIVATE_KEY_LENGTH);
    }

    [Fact]
    public void TwoRunsGiveDifferentKeyPairs()
    {
        // B4
        var first = RunCommand();
        var second = RunCommand();

        ValueOf(first[0]).Should().NotBe(ValueOf(second[0]));
        ValueOf(first[1]).Should().NotBe(ValueOf(second[1]));
    }

    [Fact]
    public async Task CommandNeedsNoEnvFileNoDatabaseAndStartsNoApi()
    {
        // B5: the env file path points to a missing file, so loading it, building the API or calling a database would throw or block.
        Environment.SetEnvironmentVariable(EnvironmentFile.PATH_VARIABLE, MISSING_ENV_FILE);
        using var output = new StringWriter();

        await Task.Run(() => RunEntryPoint(output), TestContext.Current.CancellationToken).WaitAsync(CommandTimeout, TestContext.Current.CancellationToken);

        Lines(output).Should().HaveCount(2);
    }

    [Fact]
    public void OtherArgumentsAreNotCommand()
    {
        // B5: any other start runs the API as before.
        using var output = new StringWriter();

        VapidKeyGenerator.TryRunCommand([], output).Should().BeFalse();
        output.ToString().Should().BeEmpty();
    }

    public void Dispose() => environment.Dispose();

    private static string[] RunCommand()
    {
        using var output = new StringWriter();
        VapidKeyGenerator.TryRunCommand([VapidKeyGenerator.COMMAND], output).Should().BeTrue();

        return Lines(output);
    }

    // Runs Program the way "dotnet run -- generate-vapid-keys" does. Console output is captured for the call only.
    private static void RunEntryPoint(TextWriter output)
    {
        var original = Console.Out;
        Console.SetOut(output);
        try
        {
            typeof(Program).Assembly.EntryPoint!.Invoke(null, [new[] { VapidKeyGenerator.COMMAND }]);
        }
        finally
        {
            Console.SetOut(original);
        }
    }

    private static string[] Lines(StringWriter output) =>
        output.ToString().Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries);

    private static string ValueOf(string line) => line[(line.IndexOf(ASSIGNMENT, StringComparison.Ordinal) + 1)..];
}
