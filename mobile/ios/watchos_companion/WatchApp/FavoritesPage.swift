import SwiftUI
import WidgetKit

struct FavoritesPage: View {
  let assets: [WatchAsset]

  @AppStorage("favoriteSymbols", store: UserDefaults(suiteName: "group.com.teamcata.abct"))
  private var favoritesData: Data = Data()

  @State private var isEditing = false

  private var favoriteSymbols: Set<String> {
    (try? JSONDecoder().decode(Set<String>.self, from: favoritesData)) ?? []
  }

  private var favoriteAssets: [WatchAsset] {
    let syms = favoriteSymbols
    return assets
      .filter { syms.contains($0.symbol) }
      .sorted { $0.valueUsd > $1.valueUsd }
  }

  var body: some View {
    if assets.isEmpty {
      emptyState(message: "No assets synced")
    } else if favoriteSymbols.isEmpty {
      VStack(spacing: 10) {
        Image(systemName: "star")
          .font(.system(size: 28))
          .foregroundStyle(.yellow.opacity(0.6))
        Text("No favorites yet")
          .font(.system(size: 13, weight: .medium))
          .foregroundStyle(.secondary)
        Button("Choose Favorites") {
          isEditing = true
        }
        .font(.system(size: 12, weight: .semibold))
        .buttonStyle(.borderedProminent)
        .tint(.yellow.opacity(0.8))
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(Color.black)
      .sheet(isPresented: $isEditing) {
        FavoritesEditSheet(
          assets: assets,
          favoritesData: $favoritesData
        )
      }
    } else {
      ScrollView {
        VStack(spacing: 0) {
          HStack {
            Text("Favorites")
              .font(.system(size: 12, weight: .medium))
              .foregroundStyle(.secondary)
            Spacer()
            Button {
              isEditing = true
            } label: {
              Image(systemName: "pencil.circle.fill")
                .font(.system(size: 16))
                .foregroundStyle(.yellow.opacity(0.7))
            }
            .buttonStyle(.plain)
          }
          .padding(.horizontal, 10)
          .padding(.top, 8)
          .padding(.bottom, 6)

          ForEach(favoriteAssets) { asset in
            NavigationLink(destination: FavoriteDetailPage(asset: asset)) {
              FavoriteCard(asset: asset)
            }
            .buttonStyle(.plain)
          }
        }
      }
      .background(Color.black)
      .sheet(isPresented: $isEditing) {
        FavoritesEditSheet(
          assets: assets,
          favoritesData: $favoritesData
        )
      }
    }
  }

  private func emptyState(message: String) -> some View {
    VStack(spacing: 8) {
      Image(systemName: "star")
        .font(.system(size: 28))
        .foregroundStyle(.secondary)
      Text(message)
        .font(.system(size: 13, weight: .medium))
        .foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Color.black)
  }
}

private struct FavoriteCard: View {
  let asset: WatchAsset

  private var changeColor: Color {
    asset.priceChange24h >= 0 ? .green : .red
  }

  var body: some View {
    HStack(spacing: 8) {
      // Logo with disk-cached loader
      CachedAssetImage(url: asset.imageUrl, symbol: asset.symbol, size: 26)

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
    .padding(.vertical, 8)
  }
}

// MARK: - Edit Sheet

struct FavoritesEditSheet: View {
  let assets: [WatchAsset]
  @Binding var favoritesData: Data
  @Environment(\.dismiss) private var dismiss

  @State private var selected: Set<String> = []

  var body: some View {
    NavigationStack {
      List {
        ForEach(assets.sorted(by: { $0.valueUsd > $1.valueUsd })) { asset in
          Button {
            if selected.contains(asset.symbol) {
              selected.remove(asset.symbol)
            } else {
              selected.insert(asset.symbol)
            }
          } label: {
            HStack {
              Text(asset.symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.white)
              Spacer()
              if selected.contains(asset.symbol) {
                Image(systemName: "star.fill")
                  .foregroundStyle(.yellow)
                  .font(.system(size: 12))
              }
            }
          }
        }
      }
      .navigationTitle("Favorites")
      .toolbar {
        ToolbarItem(placement: .confirmationAction) {
          Button("Done") {
            if let encoded = try? JSONEncoder().encode(selected) {
              favoritesData = encoded
              // Favorites lead the complication gallery — rebuild its
              // recommendation list to match the new selection.
              WidgetCenter.shared.invalidateConfigurationRecommendations()
            }
            dismiss()
          }
        }
      }
    }
    .onAppear {
      selected = (try? JSONDecoder().decode(Set<String>.self, from: favoritesData)) ?? []
    }
  }
}

// MARK: - Chart Range Picker

private enum ChartRange: String, CaseIterable, Identifiable {
  case day = "24H"
  case week = "7D"

  var id: String { rawValue }
}

// MARK: - Detail Page

struct FavoriteDetailPage: View {
  let asset: WatchAsset

  @State private var chartRange: ChartRange = .day

  private var changeColor: Color {
    asset.priceChange24h >= 0 ? .green : .red
  }

  private var changeAmount: Double {
    let pct = asset.priceChange24h / 100.0
    return asset.nativePriceUsd * pct / (1 + pct)
  }

  private var activeSparkline: [Double] {
    switch chartRange {
    case .day:
      return asset.sparkline24h.count > 1 ? asset.sparkline24h : asset.sparkline7d
    case .week:
      return asset.sparkline7d
    }
  }

  private var sparklineTrend: Color {
    guard let first = activeSparkline.first, let last = activeSparkline.last else {
      return .green
    }
    return last >= first ? .green : .red
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 8) {
        // Header: logo + name
        HStack(spacing: 8) {
          CachedAssetImage(url: asset.imageUrl, symbol: asset.symbol, size: 28)

          VStack(alignment: .leading, spacing: 1) {
            Text(asset.name)
              .font(.system(size: 15, weight: .semibold))
              .foregroundStyle(.white)
              .lineLimit(1)
            Text(asset.symbol)
              .font(.system(size: 11, weight: .medium))
              .foregroundStyle(.secondary)
          }
        }

        Divider().overlay(Color.white.opacity(0.1))

        // Price
        detailRow(label: "Price", value: PortfolioFormatters.compactPrice(asset.nativePriceUsd))

        // 24h Change %
        HStack {
          Text("24h Change")
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(.secondary)
          Spacer()
          Text(PortfolioFormatters.signedPercent(asset.priceChange24h))
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundStyle(changeColor)
            .monospacedDigit()
        }

        // 24h Change $
        HStack {
          Text("24h Amount")
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(.secondary)
          Spacer()
          Text(PortfolioFormatters.signedCurrency(changeAmount))
            .font(.system(size: 12, weight: .medium, design: .rounded))
            .foregroundStyle(changeColor)
            .monospacedDigit()
        }

        // Sparkline chart with range picker
        if activeSparkline.count > 1 {
          VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
              ForEach(ChartRange.allCases) { range in
                Button {
                  chartRange = range
                } label: {
                  Text(range.rawValue)
                    .font(.system(size: 11, weight: chartRange == range ? .bold : .medium))
                    .foregroundStyle(chartRange == range ? .white : .secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
                    .background(
                      chartRange == range
                        ? Color.white.opacity(0.15)
                        : Color.clear,
                      in: RoundedRectangle(cornerRadius: 6, style: .continuous)
                    )
                }
                .buttonStyle(.plain)
              }
            }
            .padding(3)
            .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 8, style: .continuous))

            ZStack(alignment: .bottom) {
              SparklineFillShape(points: activeSparkline)
                .fill(
                  LinearGradient(
                    colors: sparklineTrend == .green
                      ? [Color.cyan.opacity(0.35), Color.green.opacity(0.1), Color.clear]
                      : [Color.orange.opacity(0.35), Color.red.opacity(0.1), Color.clear],
                    startPoint: .top,
                    endPoint: .bottom
                  )
                )

              SparklineShape(points: activeSparkline)
                .stroke(
                  LinearGradient(
                    colors: sparklineTrend == .green
                      ? [.cyan, .green]
                      : [.orange, .red],
                    startPoint: .leading,
                    endPoint: .trailing
                  ),
                  style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round)
                )
            }
            .frame(height: 50)
            .padding(8)
            .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))

            HStack {
              Text(chartRange == .day ? "24h ago" : "7d ago")
                .font(.system(size: 8, weight: .regular))
                .foregroundStyle(.secondary)
              Spacer()
              Text("Now")
                .font(.system(size: 8, weight: .regular))
                .foregroundStyle(.secondary)
            }
          }
        }

        Divider().overlay(Color.white.opacity(0.1))

        // Portfolio value
        detailRow(label: "Holdings", value: PortfolioFormatters.compactCurrency(asset.valueUsd))

        // Allocation
        detailRow(label: "Allocation", value: String(format: "%.1f%%", asset.percentage))
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 8)
    }
    .background(Color.black)
    .navigationTitle(asset.symbol)
  }

  private func detailRow(label: String, value: String) -> some View {
    HStack {
      Text(label)
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(.secondary)
      Spacer()
      Text(value)
        .font(.system(size: 12, weight: .medium, design: .rounded))
        .foregroundStyle(.white)
        .monospacedDigit()
    }
  }

}

#Preview {
  FavoritesPage(assets: PortfolioWatchData.sample.assets)
    .frame(width: 198, height: 242)
}
