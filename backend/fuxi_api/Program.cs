using FuXi.Api;

EnvironmentFile.Load();

var builder = WebApplication.CreateBuilder(args);

// Fails fast when the database configuration is incomplete.
_ = DatabaseSettings.BuildConnectionString(builder.Configuration);

var app = builder.Build();

app.Run();
