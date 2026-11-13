using FuXi.Api;
using FuXi.Api.Database;
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

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();
app.MapFuXiApi();

if (DatabaseMigration.IsEnabled(app.Configuration))
{
    DatabaseMigration.Apply(app.Services);
}

app.Run();
