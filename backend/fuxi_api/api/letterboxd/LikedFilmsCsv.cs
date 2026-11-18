using System.Text;

namespace FuXi.Api.Letterboxd;

/// <summary>Reads the liked movies file of Letterboxd's data export (likes/films.csv) as far as the API needs.</summary>
public static class LikedFilmsCsv
{
    private const string DATE_COLUMN = "Date";
    private const string NAME_COLUMN = "Name";
    private const string YEAR_COLUMN = "Year";

    /// <summary>
    /// The number of movie rows, or null when the text has no header with the Date, Name and Year columns or
    /// no movie row. A movie row has a name and a year that is a number, as the RAG engine reads it; other rows
    /// are not counted. A comma or a line break inside quotes does not split a row; a blank line is not a row.
    /// </summary>
    public static int? CountMovies(string text)
    {
        var rows = ReadRows(text.TrimStart('﻿'));
        if (rows.Count == 0 || new[] { DATE_COLUMN, NAME_COLUMN, YEAR_COLUMN }.Any(column => !rows[0].Contains(column)))
        {
            return null;
        }

        var nameIndex = rows[0].IndexOf(NAME_COLUMN);
        var yearIndex = rows[0].IndexOf(YEAR_COLUMN);
        var movies = rows.Skip(1).Count(row => IsMovie(row, nameIndex, yearIndex));

        return movies > 0 ? movies : null;
    }

    private static bool IsMovie(List<string> row, int nameIndex, int yearIndex) =>
        row.Count > Math.Max(nameIndex, yearIndex)
        && !string.IsNullOrWhiteSpace(row[nameIndex])
        && row[yearIndex].Trim() is { Length: > 0 } year
        && year.All(char.IsAsciiDigit);

    private static List<List<string>> ReadRows(string text)
    {
        var rows = new List<List<string>>();
        var row = new List<string>();
        var field = new StringBuilder();
        var isQuoted = false;

        for (var index = 0; index < text.Length; index++)
        {
            var letter = text[index];
            if (isQuoted)
            {
                if (letter != '"')
                {
                    field.Append(letter);
                }
                else if (index + 1 < text.Length && text[index + 1] == '"')
                {
                    field.Append('"');
                    index++;
                }
                else
                {
                    isQuoted = false;
                }

                continue;
            }

            switch (letter)
            {
                case '"':
                    isQuoted = true;
                    break;
                case ',':
                    row.Add(field.ToString());
                    field.Clear();
                    break;
                case '\r':
                    break;
                case '\n':
                    EndRow(rows, row, field);
                    row = [];
                    break;
                default:
                    field.Append(letter);
                    break;
            }
        }

        EndRow(rows, row, field);

        return rows;
    }

    // A row of one empty field is a blank line.
    private static void EndRow(List<List<string>> rows, List<string> row, StringBuilder field)
    {
        row.Add(field.ToString());
        field.Clear();
        if (row.Count > 1 || row[0].Length > 0)
        {
            rows.Add(row);
        }
    }
}
