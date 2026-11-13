using Microsoft.Extensions.Hosting;

namespace FuXi.Api.Tests.Api;

/// <summary>Stands in for a hosted service a test host must not start.</summary>
public sealed class SkippedHostedService : IHostedService
{
    public Task StartAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
