namespace FuXi.Api.Words;

/// <summary>A Due Word as it is sent in a push notification.</summary>
public sealed record NotificationWord(Guid Id, string Name);
