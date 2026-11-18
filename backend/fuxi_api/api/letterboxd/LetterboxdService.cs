using System.Text;
using FuXi.Api.Database;
using FuXi.Api.Database.Entities;
using FuXi.Api.OAuth;

namespace FuXi.Api.Letterboxd;

/// <summary>The liked movies upload logic behind the Letterboxd endpoints.</summary>
public sealed class LetterboxdService(FuXiDbContext database)
{
    private const long MAX_FILE_BYTES = 5 * 1024 * 1024;
    private const string NOT_A_LIKES_FILE = "The file must be a CSV with the Date, Name and Year columns.";

    private static readonly UTF8Encoding STRICT_UTF8 = new(false, true);

    /// <summary>Whether a file is saved and its movie count. The text itself never leaves the API.</summary>
    public async Task<LetterboxdLikes> GetLikesAsync(CancellationToken cancellationToken)
    {
        var values = await SettingRows.ReadAsync(database, [SettingCodes.LETTERBOXD_LIKED_FILMS_CSV], cancellationToken);
        var text = values.GetValueOrDefault(SettingCodes.LETTERBOXD_LIKED_FILMS_CSV);

        return string.IsNullOrEmpty(text)
            ? new LetterboxdLikes(false, 0)
            : new LetterboxdLikes(true, LikedFilmsCsv.CountMovies(text) ?? 0);
    }

    /// <summary>
    /// Saves the file's text, replacing the old one. A file that is too large, not UTF-8, or without the Date,
    /// Name and Year columns and a movie row is refused and changes nothing.
    /// </summary>
    public async Task<LetterboxdLikesSaved> SaveLikesAsync(IFormFile? file, CancellationToken cancellationToken)
    {
        if (file is null || file.Length is 0 or > MAX_FILE_BYTES)
        {
            throw ApiException.BadRequest(NOT_A_LIKES_FILE);
        }

        var text = await ReadTextAsync(file, cancellationToken);
        var movieCount = LikedFilmsCsv.CountMovies(text) ?? throw ApiException.BadRequest(NOT_A_LIKES_FILE);

        await SettingRows.SaveAsync(database, new Dictionary<string, string> { [SettingCodes.LETTERBOXD_LIKED_FILMS_CSV] = text }, cancellationToken);

        return new LetterboxdLikesSaved(movieCount);
    }

    private static async Task<string> ReadTextAsync(IFormFile file, CancellationToken cancellationToken)
    {
        using var stream = new MemoryStream();
        await file.CopyToAsync(stream, cancellationToken);

        try
        {
            var text = STRICT_UTF8.GetString(stream.ToArray());

            // PostgreSQL text cannot hold U+0000; a real CSV never does.
            return text.Contains('\0') ? throw ApiException.BadRequest(NOT_A_LIKES_FILE) : text;
        }
        catch (DecoderFallbackException)
        {
            throw ApiException.BadRequest(NOT_A_LIKES_FILE);
        }
    }
}
