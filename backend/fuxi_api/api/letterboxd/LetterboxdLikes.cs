namespace FuXi.Api.Letterboxd;

/// <summary>Whether a liked movies file is saved, and how many movies it holds. It never carries the file's text.</summary>
public sealed record LetterboxdLikes(bool HasUpload, int MovieCount);

/// <summary>The answer of UploadLetterboxdLikes.</summary>
public sealed record LetterboxdLikesSaved(int MovieCount);
