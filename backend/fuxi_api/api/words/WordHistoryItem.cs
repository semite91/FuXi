namespace FuXi.Api.Words;

/// <summary>One answer in the Word History of a Word.</summary>
public sealed record WordHistoryItem(bool IsKnown, DateTimeOffset Date);
