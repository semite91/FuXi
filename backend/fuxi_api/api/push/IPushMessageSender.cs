namespace FuXi.Api.Push;

/// <summary>Delivers signed push messages to the push services of Push Subscriptions.</summary>
public interface IPushMessageSender
{
    /// <summary>Builds the VAPID authentication once for one run of the timed task. The caller disposes the run after its pushes.</summary>
    IPushRun StartRun(VapidDetails vapid);
}
