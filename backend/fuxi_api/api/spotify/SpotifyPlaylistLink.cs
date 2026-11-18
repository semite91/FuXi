using System.Text.RegularExpressions;

namespace FuXi.Api.Spotify;

/// <summary>
/// Takes the playlist ID from a Spotify playlist link (also the older /user/&lt;name&gt;/playlist/ form), or accepts a
/// spotify:playlist: address (also the older spotify:user:&lt;name&gt;:playlist: form) or a bare ID. Spotify is not called.
/// </summary>
public static partial class SpotifyPlaylistLink
{
    private const string SPOTIFY_HOST = "open.spotify.com";

    /// <summary>The playlist ID, or null when the text is none of the accepted forms.</summary>
    public static string? TryReadPlaylistId(string? text)
    {
        var trimmed = text?.Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return null;
        }

        if (PlaylistIdPattern().IsMatch(trimmed))
        {
            return trimmed;
        }

        var uri = PlaylistUriPattern().Match(trimmed);
        if (uri.Success)
        {
            return uri.Groups["id"].Value;
        }

        if (!Uri.TryCreate(trimmed, UriKind.Absolute, out var link)
            || (link.Scheme != Uri.UriSchemeHttps && link.Scheme != Uri.UriSchemeHttp)
            || link.Host != SPOTIFY_HOST)
        {
            return null;
        }

        var match = PlaylistPathPattern().Match(link.AbsolutePath);

        return match.Success ? match.Groups["id"].Value : null;
    }

    // Spotify IDs are 22 letters and digits, so a word or a typo is not taken for an ID.
    [GeneratedRegex("^[A-Za-z0-9]{22}$")]
    private static partial Regex PlaylistIdPattern();

    // spotify:playlist:<id> or the older spotify:user:<name>:playlist:<id>.
    [GeneratedRegex("^spotify:(?:user:[^:]+:)?playlist:(?<id>[A-Za-z0-9]{22})$")]
    private static partial Regex PlaylistUriPattern();

    // /playlist/<id>, /intl-xx/playlist/<id> or the older /user/<name>/playlist/<id>, with an optional closing slash.
    [GeneratedRegex("^/(?:intl-[A-Za-z-]+/)?(?:user/[^/]+/)?playlist/(?<id>[A-Za-z0-9]{22})/?$")]
    private static partial Regex PlaylistPathPattern();
}
