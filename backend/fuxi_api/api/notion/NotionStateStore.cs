using System.Buffers.Text;
using System.Collections.Concurrent;
using System.Security.Cryptography;

namespace FuXi.Api.Notion;

/// <summary>
/// Keeps the one-time state values that tie a Notion callback to a sign-in this API started, so a forged
/// callback is refused. They live in memory only: a restart forgets them, and the Learner simply connects again.
/// </summary>
public sealed class NotionStateStore(TimeProvider timeProvider)
{
    /// <summary>How long a started sign-in may take.</summary>
    public static readonly TimeSpan LIFETIME = TimeSpan.FromMinutes(10);

    private const int STATE_BYTES = 32;

    private readonly ConcurrentDictionary<string, DateTimeOffset> expiryByState = new(StringComparer.Ordinal);

    /// <summary>Makes and keeps a new random state value.</summary>
    public string Create()
    {
        var now = timeProvider.GetUtcNow();
        RemoveExpired(now);
        var state = Base64Url.EncodeToString(RandomNumberGenerator.GetBytes(STATE_BYTES));
        expiryByState[state] = now + LIFETIME;

        return state;
    }

    /// <summary>True when this API made the state less than <see cref="LIFETIME"/> ago and it was not used yet. It cannot be used again.</summary>
    public bool TryUse(string? state) =>
        !string.IsNullOrEmpty(state)
        && expiryByState.TryRemove(state, out var expiry)
        && timeProvider.GetUtcNow() < expiry;

    // Sign-ins the Learner never finished would otherwise stay in memory.
    private void RemoveExpired(DateTimeOffset now)
    {
        foreach (var (state, expiry) in expiryByState)
        {
            if (expiry <= now)
            {
                expiryByState.TryRemove(state, out _);
            }
        }
    }
}
