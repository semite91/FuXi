using FuXi.Api;
using FuXi.Api.Database;
using FuXi.Api.GoogleDrive;
using FuXi.Api.Notion;
using FuXi.Api.OAuth;
using FuXi.Api.Push;

// A tool command runs before anything else, so it needs no env file, no database and no API.
if (VapidKeyGenerator.TryRunCommand(args, Console.Out))
{
    return;
}

EnvironmentFile.Load();

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFuXiDatabase();
builder.Services.AddFuXiApi();

var app = builder.Build();

// Fails fast when the database or CORS configuration is incomplete.
app.Configuration.ValidateFuXiConfiguration();

// Notion and Google Drive are optional: a missing key is only logged.
var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
OAuthSettings.LogMissingAppUrl(app.Configuration, loggerFactory);
NotionSettings.LogMissingKeys(app.Configuration, loggerFactory);
GoogleDriveSettings.LogMissingKeys(app.Configuration, loggerFactory);

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();
app.MapFuXiApi();

if (DatabaseMigration.IsEnabled(app.Configuration))
{
    DatabaseMigration.Apply(app.Services);
}

app.Run();
