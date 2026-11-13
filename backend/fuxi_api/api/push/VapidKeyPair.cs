namespace FuXi.Api.Push;

/// <summary>A VAPID public key (65-byte uncompressed P-256 point) and private key (32 bytes), both URL-safe Base64 without padding.</summary>
public sealed record VapidKeyPair(string PublicKey, string PrivateKey);
