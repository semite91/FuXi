namespace FuXi.Api.Notion;

/// <summary>Whether Notion is connected, and to which workspace. It never carries a token.</summary>
public sealed record NotionConnection(bool IsConnected, string? WorkspaceName);
