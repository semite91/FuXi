using FluentAssertions;
using FuXi.Api.Database.Entities;
using Xunit;

namespace FuXi.Api.Tests.Api;

/// <summary>Section K: GetConfigs.</summary>
[Collection(nameof(SmokeTests))]
public sealed class GetConfigsTests : IDisposable
{
    private const int CHANGED_ROTATION_COUNT = 35;
    private const string CHANGED_VALUE = "35";
    private static readonly string[] ITEM_FIELDS =
        [ApiFields.CONFIG_ID, ApiFields.CODE, ApiFields.NAME, ApiFields.VALUE, ApiFields.INPUT_TYPE];

    private readonly DatabaseApi api = new();

    [Fact]
    public async Task SeededDatabaseGivesFourItems()
    {
        // K1
        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_CONFIGS);

        items.Should().HaveCount(TestData.SEEDED_CONFIG_COUNT);
    }

    [Fact]
    public async Task ItemHoldsConfigFieldsWithInputTypeAsText()
    {
        // K2, K3
        var config = api.Read(context => TestData.ConfigOf(context, TestData.ROTATION_COUNT_CODE));

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_CONFIGS);

        items.Should().AllSatisfy(item => item.FieldNames().Should().BeEquivalentTo(ITEM_FIELDS));
        var item = items.Should().ContainSingle(candidate => candidate.Text(ApiFields.CODE) == config.Code).Subject;
        item.GuidOf(ApiFields.CONFIG_ID).Should().Be(config.Id);
        item.Text(ApiFields.NAME).Should().Be(config.Name);
        item.Text(ApiFields.VALUE).Should().Be(config.Value);
        item.Text(ApiFields.INPUT_TYPE).Should().Be(nameof(InputType.Number));
    }

    [Fact]
    public async Task ChangedValueIsReturned()
    {
        // K4
        api.Arrange(context => TestData.SetConfig(context, TestData.ROTATION_COUNT_CODE, CHANGED_ROTATION_COUNT));

        var items = await api.Client.GetItemsAsync(ApiRoutes.GET_CONFIGS);

        items.Should().ContainSingle(item => item.Text(ApiFields.CODE) == TestData.ROTATION_COUNT_CODE)
            .Which.Text(ApiFields.VALUE).Should().Be(CHANGED_VALUE);
    }

    public void Dispose() => api.Dispose();
}
