using System.Buffers.Text;
using System.Security.Cryptography;

namespace FuXi.Api.Push;

/// <summary>Creates a VAPID key pair: a P-256 key in the URL-safe Base64 form, without padding, that browsers and push services read.</summary>
public static class VapidKeyGenerator
{
    /// <summary>The command-line argument that prints a new key pair instead of starting the API.</summary>
    public const string COMMAND = "generate-vapid-keys";

    // The first byte of an uncompressed elliptic curve point (SEC 1).
    private const byte UNCOMPRESSED_POINT_MARKER = 4;
    private const char ASSIGNMENT = '=';

    /// <summary>A new, random key pair.</summary>
    public static VapidKeyPair Generate()
    {
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var parameters = key.ExportParameters(includePrivateParameters: true);
        try
        {
            byte[] publicKey = [UNCOMPRESSED_POINT_MARKER, .. parameters.Q.X!, .. parameters.Q.Y!];

            return new VapidKeyPair(Base64Url.EncodeToString(publicKey), Base64Url.EncodeToString(parameters.D));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(parameters.D);
        }
    }

    /// <summary>Prints a new key pair, one KEY=value line each, when the arguments are the command. Returns false for any other arguments.</summary>
    public static bool TryRunCommand(string[] args, TextWriter output)
    {
        if (args is not [COMMAND])
        {
            return false;
        }

        var keyPair = Generate();
        output.WriteLine($"{VapidSettings.PUBLIC_KEY_KEY}{ASSIGNMENT}{keyPair.PublicKey}");
        output.WriteLine($"{VapidSettings.PRIVATE_KEY_KEY}{ASSIGNMENT}{keyPair.PrivateKey}");

        return true;
    }
}
