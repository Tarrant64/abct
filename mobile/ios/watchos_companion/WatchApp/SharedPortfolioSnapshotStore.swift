import Foundation

private enum WatchSnapshotConfig {
  static let appGroupIdentifier = "group.com.teamcata.abct"
  static let snapshotDefaultsKey = "portfolio_snapshot_v1"
}

private struct StoredAssetSnapshot: Codable {
  let symbol: String
  let name: String
  let valueUsd: Double
  let nativePriceUsd: Double
  let priceChange24h: Double
  let percentage: Double
  let imageUrl: String?
  let sparkline7d: [Double]?
  let sparkline24h: [Double]?
}

private struct StoredPortfolioSnapshot: Codable {
  let totalValue: Double
  let sevenDayChange: Double
  let percentChange: Double
  let historyPoints: [Double]
  let assets: [StoredAssetSnapshot]?
  let updatedAt: TimeInterval
}

enum SharedPortfolioSnapshotStore {
  static func load() -> PortfolioWatchData? {
    guard let defaults = UserDefaults(suiteName: WatchSnapshotConfig.appGroupIdentifier),
          let data = defaults.data(forKey: WatchSnapshotConfig.snapshotDefaultsKey),
          let decoded = try? JSONDecoder().decode(StoredPortfolioSnapshot.self, from: data),
          !decoded.historyPoints.isEmpty
    else {
      return nil
    }

    let assets = (decoded.assets ?? []).map { stored in
      WatchAsset(
        symbol: stored.symbol,
        name: stored.name,
        valueUsd: stored.valueUsd,
        nativePriceUsd: stored.nativePriceUsd,
        priceChange24h: stored.priceChange24h,
        percentage: stored.percentage,
        imageUrl: stored.imageUrl ?? "",
        sparkline7d: stored.sparkline7d ?? [],
        sparkline24h: stored.sparkline24h ?? []
      )
    }

    return PortfolioWatchData(
      totalValue: decoded.totalValue,
      sevenDayChange: decoded.sevenDayChange,
      percentChange: decoded.percentChange,
      historyPoints: decoded.historyPoints,
      assets: assets
    )
  }
}
