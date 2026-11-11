using System.Globalization;
using FuXi.Api.Database.Entities;

namespace FuXi.Api.Configs;

/// <summary>Checks a Config value against the input type of its row.</summary>
public static class ConfigValue
{
    /// <summary>The largest Number value: one year in minutes.</summary>
    public const int MAXIMUM_NUMBER = 525600;

    /// <summary>Number: whole number from 1 to the maximum. Date: ISO 8601 date-time. Other types: any text that is not empty.</summary>
    public static bool IsValid(InputType inputType, string value) =>
        inputType switch
        {
            InputType.Number => TryParseNumber(value, out _),
            InputType.Date => IsoDateTime.TryParse(value, out _),
            _ => !string.IsNullOrWhiteSpace(value),
        };

    /// <summary>Reads a whole number from 1 to the maximum. Only digits are accepted: no sign, no spaces, no decimals.</summary>
    public static bool TryParseNumber(string value, out int number) =>
        int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out number) && number is > 0 and <= MAXIMUM_NUMBER;
}
