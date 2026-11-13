using Quartz;
using Quartz.Extensibility;

namespace FuXi.Api.Push;

/// <summary>Creates each <see cref="NotificationJob"/> in a DI scope of its own, so it gets a fresh DbContext, and disposes the scope after the run.</summary>
public sealed class NotificationJobFactory(IServiceScopeFactory scopeFactory) : IJobFactory
{
    public ValueTask<JobScope> CreateJob(TriggerFiredBundle bundle, IScheduler scheduler, CancellationToken cancellationToken)
    {
        var scope = scopeFactory.CreateAsyncScope();
        try
        {
            return ValueTask.FromResult(new JobScope(scope.ServiceProvider.GetRequiredService<NotificationJob>(), scope));
        }
        catch
        {
            scope.Dispose();
            throw;
        }
    }

    public async ValueTask ReturnJob(JobScope scope, CancellationToken cancellationToken)
    {
        if (scope.State is AsyncServiceScope serviceScope)
        {
            await serviceScope.DisposeAsync();
        }
    }
}
