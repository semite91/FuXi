namespace FuXi.Api.Spotify;

/// <summary>Whether Spotify is connected, to which account, and which playlist is chosen. It never carries a token or a user id.</summary>
public sealed record SpotifyConnection(bool IsConnected, string? Name, string? PlaylistId);

/// <summary>The body of UpdateSpotifyPlaylist: an open.spotify.com playlist link, a spotify:playlist: address or a bare ID.</summary>
public sealed record UpdateSpotifyPlaylistRequest(string? PlaylistLink);

/// <summary>The answer of UpdateSpotifyPlaylist.</summary>
public sealed record SpotifyPlaylistSaved(string PlaylistId);
