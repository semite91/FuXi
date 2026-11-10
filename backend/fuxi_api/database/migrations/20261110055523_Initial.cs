using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace FuXi.Api.Database.Migrations
{
    /// <inheritdoc />
    public partial class Initial : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Config",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    Name = table.Column<string>(type: "text", nullable: false),
                    Code = table.Column<string>(type: "text", nullable: false),
                    Value = table.Column<string>(type: "text", nullable: false),
                    InputType = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Config", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "PushSubscription",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    Endpoint = table.Column<string>(type: "text", nullable: false),
                    P256dh = table.Column<string>(type: "text", nullable: false),
                    Auth = table.Column<string>(type: "text", nullable: false),
                    CreatedDate = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PushSubscription", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Schedule",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    StartDate = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    EndDate = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Schedule", x => x.Id);
                    table.CheckConstraint("CK_Schedule_EndDate_After_StartDate", "\"EndDate\" > \"StartDate\"");
                });

            migrationBuilder.CreateTable(
                name: "Words",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    Name = table.Column<string>(type: "text", nullable: false),
                    Translation = table.Column<string>(type: "text", nullable: false),
                    Content = table.Column<string>(type: "text", nullable: true),
                    IsKnown = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    IsReinforcement = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    ShownCount = table.Column<int>(type: "integer", nullable: false, defaultValue: 0),
                    KnownCount = table.Column<int>(type: "integer", nullable: false, defaultValue: 0)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Words", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RotatedWords",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    WordId = table.Column<Guid>(type: "uuid", nullable: false),
                    LastShownDate = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    Counter = table.Column<int>(type: "integer", nullable: false, defaultValue: 1)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RotatedWords", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RotatedWords_Words_WordId",
                        column: x => x.WordId,
                        principalTable: "Words",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "WordHistory",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    WordId = table.Column<Guid>(type: "uuid", nullable: false),
                    IsKnown = table.Column<bool>(type: "boolean", nullable: false),
                    Date = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_WordHistory", x => x.Id);
                    table.ForeignKey(
                        name: "FK_WordHistory_Words_WordId",
                        column: x => x.WordId,
                        principalTable: "Words",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.InsertData(
                table: "Config",
                columns: new[] { "Id", "Code", "InputType", "Name", "Value" },
                values: new object[,]
                {
                    { new Guid("6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e01"), "RotationCount", "Number", "Rotation Count", "20" },
                    { new Guid("6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e02"), "RotationPeriod", "Number", "Rotation period", "15" },
                    { new Guid("6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e03"), "ReinforcementPeriod", "Number", "Reinforcement period", "10800" },
                    { new Guid("6f1c2a3e-0b7d-4c5a-9e21-1a2b3c4d5e04"), "NotificationPeriod", "Number", "Notification period", "15" }
                });

            migrationBuilder.CreateIndex(
                name: "IX_Config_Code",
                table: "Config",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_RotatedWords_WordId",
                table: "RotatedWords",
                column: "WordId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_WordHistory_WordId",
                table: "WordHistory",
                column: "WordId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Config");

            migrationBuilder.DropTable(
                name: "PushSubscription");

            migrationBuilder.DropTable(
                name: "RotatedWords");

            migrationBuilder.DropTable(
                name: "Schedule");

            migrationBuilder.DropTable(
                name: "WordHistory");

            migrationBuilder.DropTable(
                name: "Words");
        }
    }
}
