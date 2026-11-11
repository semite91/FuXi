using FuXi.Api;
using FuXi.Api.Database;

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
