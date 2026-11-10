using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace FuXi.Api.Database;

/// <summary>Converts every DateTimeOffset to UTC, because timestamptz accepts only offset zero.</summary>
public sealed class UtcDateTimeOffsetConverter() : ValueConverter<DateTimeOffset, DateTimeOffset>(
    value => value.ToUniversalTime(),
    value => value.ToUniversalTime());
