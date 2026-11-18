using System.Text.RegularExpressions;

namespace FuXi.Api.GoogleDrive;

/// <summary>Takes the folder ID from a Google Drive folder link, or accepts a bare folder ID. Google is not called.</summary>
public static partial class GoogleDriveFolderLink
{
    private const string DRIVE_HOST = "drive.google.com";

    /// <summary>The folder ID, or null when the text is neither a drive.google.com folder link nor a bare ID.</summary>
    public static string? TryReadFolderId(string? text)
    {
        var trimmed = text?.Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return null;
        }

        if (FolderIdPattern().IsMatch(trimmed))
        {
            return trimmed;
        }

        if (!Uri.TryCreate(trimmed, UriKind.Absolute, out var link) || link.Scheme != Uri.UriSchemeHttps || link.Host != DRIVE_HOST)
        {
            return null;
        }

        var match = FolderPathPattern().Match(link.AbsolutePath);

        return match.Success ? match.Groups["id"].Value : null;
    }

    // Drive IDs are letters, digits, - and _, and at least 20 long, so a word or a typo is not taken for an ID.
    [GeneratedRegex("^[A-Za-z0-9_-]{20,}$")]
    private static partial Regex FolderIdPattern();

    // /drive/folders/<id> or /drive/u/<n>/folders/<id>, with an optional closing slash.
    [GeneratedRegex("^/drive/(?:u/[0-9]+/)?folders/(?<id>[A-Za-z0-9_-]{20,})/?$")]
    private static partial Regex FolderPathPattern();
}
