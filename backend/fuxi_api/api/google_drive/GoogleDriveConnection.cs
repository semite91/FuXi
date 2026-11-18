namespace FuXi.Api.GoogleDrive;

/// <summary>Whether Google Drive is connected, to which account, and which folder is chosen. It never carries a token.</summary>
public sealed record GoogleDriveConnection(bool IsConnected, string? Email, string? FolderId);

/// <summary>The body of UpdateGoogleDriveFolder: a drive.google.com folder link or a bare folder ID.</summary>
public sealed record UpdateGoogleDriveFolderRequest(string? FolderLink);

/// <summary>The answer of UpdateGoogleDriveFolder.</summary>
public sealed record GoogleDriveFolderSaved(string FolderId);
