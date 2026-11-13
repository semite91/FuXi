using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace FuXi.Api.Tests.Api;

/// <summary>Keeps every log entry in memory, so a test can check what was logged.</summary>
public sealed class RecordingLoggerProvider : ILoggerProvider
{
    private readonly ConcurrentQueue<LogEntry> entries = new();

    public IReadOnlyList<LogEntry> Entries => entries.ToList();

    /// <summary>The entries of one category, such as the full name of the class that logged them.</summary>
    public IReadOnlyList<LogEntry> Of(string category) => Entries.Where(entry => entry.Category == category).ToList();

    public ILogger CreateLogger(string categoryName) => new RecordingLogger(categoryName, entries);

    public void Dispose()
    {
    }

    private sealed class RecordingLogger(string category, ConcurrentQueue<LogEntry> entries) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) =>
            entries.Enqueue(new LogEntry(category, logLevel, formatter(state, exception), exception));
    }
}

/// <summary>One recorded log entry.</summary>
public sealed record LogEntry(string Category, LogLevel Level, string Message, Exception? Exception);
