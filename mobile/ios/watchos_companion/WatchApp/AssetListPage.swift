import SwiftUI

struct AssetListPage: View {
  let assets: [WatchAsset]

  var body: some View {
    if assets.isEmpty {
      VStack(spacing: 8) {
        Image(systemName: "chart.pie")
          .font(.system(size: 28))
          .foregroundStyle(.secondary)
        Text("No assets synced")
          .font(.system(size: 13, weight: .medium))
          .foregroundStyle(.secondary)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(Color.black)
    } else {
      ScrollView {
        VStack(spacing: 0) {
          Text("Assets")
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .padding(.top, 8)
            .padding(.bottom, 6)

          ForEach(assets) { asset in
            AssetRow(asset: asset)
          }
        }
      }
      .background(Color.black)
    }
  }
}

private struct AssetRow: View {
  let asset: WatchAsset

  private var changeColor: Color {
    asset.priceChange24h >= 0 ? .green : .red
  }

  var body: some View {
    HStack(spacing: 8) {
      // Asset logo with disk-cached loader
      CachedAssetImage(url: asset.imageUrl, symbol: asset.symbol, size: 24)

      VStack(alignment: .leading, spacing: 1) {
        Text(asset.symbol)
          .font(.system(size: 13, weight: .semibold))
          .foregroundStyle(.white)
          .lineLimit(1)

        Text(PortfolioFormatters.compactPrice(asset.nativePriceUsd))
          .font(.system(size: 10, weight: .regular, design: .rounded))
          .foregroundStyle(.secondary)
          .monospacedDigit()
          .lineLimit(1)
      }

      Spacer(minLength: 4)

      VStack(alignment: .trailing, spacing: 1) {
        Text(PortfolioFormatters.compactCurrency(asset.valueUsd))
          .font(.system(size: 12, weight: .medium, design: .rounded))
          .foregroundStyle(.white)
          .monospacedDigit()
          .lineLimit(1)

        Text(PortfolioFormatters.signedPercent(asset.priceChange24h))
          .font(.system(size: 10, weight: .bold, design: .rounded))
          .foregroundStyle(changeColor)
          .monospacedDigit()
          .lineLimit(1)
      }
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 6)
  }
}

#Preview {
  AssetListPage(assets: PortfolioWatchData.sample.assets)
    .frame(width: 198, height: 242)
}
