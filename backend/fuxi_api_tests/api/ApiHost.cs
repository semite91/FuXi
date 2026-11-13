using FuXi.Api.Push;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Time.Testing;

namespace FuXi.Api.Tests.Api;

/// <summary>
/// Runs the API in memory with a fake clock and a recording notification timer.
/// No push service is ever called: every push goes to <see cref="PushSender"/>.
/// The Quartz.NET timer is not started unless <paramref name="startsNotificationTimer"/> is true.
/// The environment the API reads at startup is prepared by <see cref="NowApi"/> or <see cref="DatabaseApi"/>.
/// </summary>
public sealed class ApiHost(bool replacesServices = true, bool startsNotificationTimer = false) : WebApplicationFactory<Program>
{
    public const string BASE_ADDRESS = "https://localhost";

    public FakeTimeProvider Clock { get; } = new(TestData.Now);

    public RecordingNotificationTimer Timer { get; } = new();

    public FakePushMessageSender PushSender { get; } = new();

    public RecordingLoggerProvider Logs { get; } = new();

    /// <summary>Configuration values that win over the env file. Set them before the host starts.</summary>
    public Dictionary<string, string?> Settings { get; } = [];

    /// <summary>A client that calls over HTTPS and never follows a redirect on its own.</summary>
    public HttpClient CreateApiClient() =>
        CreateClient(new WebApplicationFactoryClientOptions { BaseAddress = new Uri(BASE_ADDRESS), AllowAutoRedirect = false });

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(Settings));
        builder.ConfigureTestServices(ReplacePushServices);
        if (replacesServices)
        {
            builder.ConfigureTestServices(ReplaceClockAndTimer);
        }
    }

    private void ReplacePushServices(IServiceCollection services)
    {
        services.AddSingleton<ILoggerProvider>(Logs);
        services.RemoveAll<IPushMessageSender>();
        services.AddSingleton<IPushMessageSender>(PushSender);
        if (!startsNotificationTimer)
        {
            SkipNotificationTimerStart(services);
        }
    }

    private void ReplaceClockAndTimer(IServiceCollection services)
    {
        services.RemoveAll<TimeProvider>();
        services.AddSingleton<TimeProvider>(Clock);
        if (!startsNotificationTimer)
        {
            services.RemoveAll<INotificationTimer>();
            services.AddSingleton<INotificationTimer>(Timer);
        }
    }

    // The timer's hosted service is registered through a factory, so the factory's result tells which one it is.
    private static void SkipNotificationTimerStart(IServiceCollection services)
    {
        for (var index = 0; index < services.Count; index++)
        {
            var descriptor = services[index];
            if (descriptor.ServiceType != typeof(IHostedService) || descriptor.IsKeyedService || descriptor.ImplementationFactory is null)
            {
                continue;
            }

            var factory = descriptor.ImplementationFactory;
            services[index] = ServiceDescriptor.Singleton<IHostedService>(provider =>
                factory(provider) is var service && service is QuartzNotificationTimer ? new SkippedHostedService() : (IHostedService)service);
        }
    }
}
