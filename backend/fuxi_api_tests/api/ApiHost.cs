using FuXi.Api.Push;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Time.Testing;

namespace FuXi.Api.Tests.Api;

/// <summary>
/// Runs the API in memory with a fake clock and a recording notification timer.
/// The environment the API reads at startup is prepared by <see cref="NowApi"/> or <see cref="DatabaseApi"/>.
/// </summary>
public sealed class ApiHost(bool replacesServices = true) : WebApplicationFactory<Program>
{
    public const string BASE_ADDRESS = "https://localhost";

    public FakeTimeProvider Clock { get; } = new(TestData.Now);

    public RecordingNotificationTimer Timer { get; } = new();

    /// <summary>A client that calls over HTTPS and never follows a redirect on its own.</summary>
    public HttpClient CreateApiClient() =>
        CreateClient(new WebApplicationFactoryClientOptions { BaseAddress = new Uri(BASE_ADDRESS), AllowAutoRedirect = false });

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        if (replacesServices)
        {
            builder.ConfigureTestServices(ReplaceClockAndTimer);
        }
    }

    private void ReplaceClockAndTimer(IServiceCollection services)
    {
        services.RemoveAll<TimeProvider>();
        services.AddSingleton<TimeProvider>(Clock);
        services.RemoveAll<INotificationTimer>();
        services.AddSingleton<INotificationTimer>(Timer);
    }
}
