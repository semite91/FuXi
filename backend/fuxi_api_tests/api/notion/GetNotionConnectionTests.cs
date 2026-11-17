using System.Net;
using System.Text.Json;
using FluentAssertions;
using FuXi.Api.Database.Entities;
using Xunit;

namespace FuXi.Api.Tests.Api.Notion;

/// <summary>Phase 6b section C (test_scenarios_2026_11_17_11_48): GET /api/GetNotionConnection.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetNotionConnectionTests : IDisposable
{
    private readonly DatabaseApi api = new();

    [Fact]
    public async Task NoTokenRowIsNotConnected()
    {
        // C1
        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.WORKSPACE_NAME).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task TokenRowIsConnectedWithWorkspaceName()
    {
        // C2
        AddNotionRows(NotionTestData.ACCESS_TOKEN, NotionTestData.WORKSPACE_NAME);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.Text(ApiFields.WORKSPACE_NAME).Should().Be(NotionTestData.WORKSPACE_NAME);
    }

    [Fact]
    public async Task EmptyWorkspaceNameIsConnectedWithoutName()
    {
        // C2, B9: the Settings page then shows "Connected" alone
        AddNotionRows(NotionTestData.ACCESS_TOKEN, string.Empty);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeTrue();
        answer.GetProperty(ApiFields.WORKSPACE_NAME).ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task AnswerHoldsNoToken()
    {
        // C3
        AddNotionRows(NotionTestData.ACCESS_TOKEN, NotionTestData.WORKSPACE_NAME);

        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_NOTION_CONNECTION);
        var body = await response.ReadTextAsync();

        body.Should().NotContain(NotionTestData.ACCESS_TOKEN).And.NotContain(NotionTestData.REFRESH_TOKEN);
        (await response.ReadJsonAsync()).FieldNames().Should().BeEquivalentTo(ApiFields.IS_CONNECTED, ApiFields.WORKSPACE_NAME);
    }

    [Fact]
    public async Task EmptyTokenIsNotConnected()
    {
        // C4
        AddNotionRows(string.Empty, NotionTestData.WORKSPACE_NAME);

        var answer = await GetConnectionAsync();

        answer.Flag(ApiFields.IS_CONNECTED).Should().BeFalse();
        answer.GetProperty(ApiFields.WORKSPACE_NAME).ValueKind.Should().Be(JsonValueKind.Null);
    }

    public void Dispose() => api.Dispose();

    private void AddNotionRows(string accessToken, string workspaceName) =>
        api.Arrange(context =>
        {
            context.Settings.AddRange(
                new Setting { Code = SettingCodes.NOTION_ACCESS_TOKEN, Value = accessToken },
                new Setting { Code = SettingCodes.NOTION_REFRESH_TOKEN, Value = NotionTestData.REFRESH_TOKEN },
                new Setting { Code = SettingCodes.NOTION_WORKSPACE_NAME, Value = workspaceName });
            context.SaveChanges();
        });

    private async Task<JsonElement> GetConnectionAsync()
    {
        using var response = await api.Client.GetApiAsync(ApiRoutes.GET_NOTION_CONNECTION);
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        return await response.ReadJsonAsync();
    }
}
