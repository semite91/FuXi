namespace FuXi.Api.Database.Entities;

/// <summary>A browser push subscription.</summary>
public class PushSubscription
{
    public Guid Id { get; set; }

    public required string Endpoint { get; set; }

    public required string P256dh { get; set; }

    public required string Auth { get; set; }

    public DateTimeOffset CreatedDate { get; set; }
}
