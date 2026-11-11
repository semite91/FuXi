using FuXi.Api.Database.Entities;

namespace FuXi.Api.Configs;

/// <summary>A setting as the settings page shows it.</summary>
public sealed record ConfigItem(Guid ConfigId, string Code, string Name, string Value, InputType InputType);
