using FuXi.Api;
using FuXi.Api.Database;

EnvironmentFile.Load();

var builder = WebApplication.CreateBuilder(args);

// Fails fast when the database configuration is incomplete.
var connectionString = DatabaseSettings.BuildConnectionString(builder.Configuration);
builder.Services.AddFuXiDatabase(connectionString);

var app = builder.Build();

DatabaseMigration.Apply(app.Services);

app.Run();
