using System.Buffers.Text;
using System.Collections.Concurrent;
using System.Security.Cryptography;

namespace FuXi.Api.OAuth;

/// <summary>
/// Keeps the one-time state values that tie a sign-in callback to a sign-in this API started, so a forged
/// callback is refused. A state belongs to one source (Notion or Google Drive) and is accepted only by that source's
/// callback. They live in memory only: a restart forgets them, and the Learner simply connects again.
/// </summary>
public sealed class OAuthStateStore(TimeProvider timeProvider)
{
    /// <summary>How long a started sign-in may take.</summary>
    public static readonly TimeSpan LIFETIME = TimeSpan.FromMinutes(10);

    private const int STATE_BYTES = 32;

    private readonly ConcurrentDictionary<string, StartedSignIn> signInByState = new(StringComparer.Ordinal);

    /// <summary>Makes and keeps a new random state value for a sign-in of this source.</summary>
    public string Create(string source)
    {
        var now = timeProvider.GetUtcNow();
        RemoveExpired(now);
        var state = Base64Url.EncodeToString(RandomNumberGenerator.GetBytes(STATE_BYTES));
        signInByState[state] = new StartedSignIn(source, now + LIFETIME);

        return state;
    }

    /// <summary>
    /// True when this API made the state for this source less than <see cref="LIFETIME"/> ago and it was not used yet.
    /// It cannot be used again, also when it belonged to another source.
    /// </summary>
    public bool TryUse(string source, string? state) =>
        !string.IsNullOrEmpty(state)
        && signInByState.TryRemove(state, out var signIn)
        && signIn.Source == source
        && timeProvider.GetUtcNow() < signIn.Expiry;

    // Sign-ins the Learner never finished would otherwise stay in memory.
    private void RemoveExpired(DateTimeOffset now)
    {
        foreach (var (state, signIn) in signInByState)
        {
            if (signIn.Expiry <= now)
            {
                signInByState.TryRemove(state, out _);
            }
        }
    }

    private sealed record StartedSignIn(string Source, DateTimeOffset Expiry);
}
