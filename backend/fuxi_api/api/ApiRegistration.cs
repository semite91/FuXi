using System.Text.Json.Serialization;
using FuXi.Api.Configs;
using FuXi.Api.Push;
using FuXi.Api.Schedules;
using FuXi.Api.Words;
using Microsoft.AspNetCore.Cors.Infrastructure;

namespace FuXi.Api;

/// <summary>Registers the API services and maps the API endpoints.</summary>
public static class ApiRegistration
{
    public static IServiceCollection AddFuXiApi(this IServiceCollection services) =>
        services
            .AddFuXiErrorHandling()
            .AddFuXiCors()
            .ConfigureHttpJsonOptions(options => options.SerializerOptions.Converters.Add(new JsonStringEnumConverter()))
            .AddSingleton(TimeProvider.System)
            .AddSingleton<INotificationTimer, IdleNotificationTimer>()
            .AddScoped<WordService>()
            .AddScoped<ConfigService>()
            .AddScoped<ScheduleService>()
            .AddScoped<PushService>();

    /// <summary>Stops the startup when a required configuration value is missing.</summary>
    public static void ValidateFuXiConfiguration(this IConfiguration configuration)
    {
        DatabaseSettings.BuildConnectionString(configuration);
        CorsSettings.ReadOrigins(configuration);
    }

    public static IEndpointRouteBuilder MapFuXiApi(this IEndpointRouteBuilder routes) =>
        routes
            .MapWordEndpoints()
            .MapConfigEndpoints()
            .MapScheduleEndpoints()
            .MapPushEndpoints();

    // Every error answer is ProblemDetails, also the ones the framework creates (binding failures, 404, 405, 500).
    private static IServiceCollection AddFuXiErrorHandling(this IServiceCollection services) =>
        services
            .AddProblemDetails()
            .AddExceptionHandler<ApiExceptionHandler>()
            .Configure<RouteHandlerOptions>(options => options.ThrowOnBadRequest = false);

    // The origins are read when the policy is first needed, so they come from the final configuration.
    private static IServiceCollection AddFuXiCors(this IServiceCollection services)
    {
        services.AddCors();
        services.AddOptions<CorsOptions>().Configure<IConfiguration>((options, configuration) =>
            options.AddDefaultPolicy(policy => policy
                .WithOrigins(CorsSettings.ReadOrigins(configuration))
                .AllowAnyHeader()
                .WithMethods(CorsSettings.ALLOWED_METHODS)));

        return services;
    }
}
