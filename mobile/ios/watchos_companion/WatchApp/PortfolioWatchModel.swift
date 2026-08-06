import Foundation

struct WatchAsset: Identifiable, Equatable {
  let id: String
  let symbol: String
  let name: String
  let valueUsd: Double
  let nativePriceUsd: Double
  let priceChange24h: Double
  let percentage: Double
  let imageUrl: String
  let sparkline7d: [Double]
  let sparkline24h: [Double]

  init(symbol: String, name: String, valueUsd: Double, nativePriceUsd: Double, priceChange24h: Double, percentage: Double, imageUrl: String = "", sparkline7d: [Double] = [], sparkline24h: [Double] = []) {
    self.id = symbol
    self.symbol = symbol
    self.name = name
    self.valueUsd = valueUsd
    self.nativePriceUsd = nativePriceUsd
    self.priceChange24h = priceChange24h
    self.percentage = percentage
    self.imageUrl = imageUrl
    self.sparkline7d = sparkline7d
    self.sparkline24h = sparkline24h
  }
}

struct PortfolioWatchData: Equatable {
  let totalValue: Double
  let sevenDayChange: Double
  let percentChange: Double
  let historyPoints: [Double]
  let assets: [WatchAsset]

  static let sample = PortfolioWatchData(
    totalValue: 128_442.63,
    sevenDayChange: 5_182.40,
    percentChange: 4.20,
    historyPoints: [
      121_190.0,
      122_010.0,
      123_420.0,
      122_840.0,
      125_090.0,
      126_910.0,
      128_442.63,
    ],
    assets: [
      WatchAsset(symbol: "BTC", name: "Bitcoin", valueUsd: 68_210.50, nativePriceUsd: 97_443.57, priceChange24h: 2.35, percentage: 53.1, sparkline7d: [94_100, 95_200, 96_800, 95_900, 97_100, 96_500, 97_443.57], sparkline24h: [96_800, 96_650, 96_900, 97_100, 96_750, 96_400, 96_200, 96_500, 96_800, 97_000, 96_900, 97_200, 97_400, 97_100, 96_800, 96_950, 97_200, 97_350, 97_100, 97_000, 97_200, 97_300, 97_400, 97_443.57]),
      WatchAsset(symbol: "ETH", name: "Ethereum", valueUsd: 32_180.20, nativePriceUsd: 3_215.80, priceChange24h: -1.12, percentage: 25.1, sparkline7d: [3_180, 3_210, 3_250, 3_230, 3_200, 3_190, 3_215.80], sparkline24h: [3_250, 3_240, 3_235, 3_220, 3_210, 3_200, 3_195, 3_210, 3_225, 3_230, 3_220, 3_215, 3_200, 3_195, 3_205, 3_210, 3_220, 3_225, 3_215, 3_210, 3_205, 3_210, 3_215, 3_215.80]),
      WatchAsset(symbol: "ADA", name: "Cardano", valueUsd: 15_420.00, nativePriceUsd: 0.742, priceChange24h: 5.67, percentage: 12.0, sparkline7d: [0.68, 0.69, 0.71, 0.70, 0.72, 0.73, 0.742], sparkline24h: [0.71, 0.712, 0.715, 0.718, 0.72, 0.722, 0.725, 0.728, 0.73, 0.729, 0.731, 0.733, 0.735, 0.734, 0.736, 0.738, 0.735, 0.737, 0.739, 0.74, 0.738, 0.74, 0.741, 0.742]),
      WatchAsset(symbol: "SOL", name: "Solana", valueUsd: 8_632.93, nativePriceUsd: 178.50, priceChange24h: -0.45, percentage: 6.7, sparkline7d: [175.0, 177.0, 180.0, 179.0, 178.0, 177.5, 178.50], sparkline24h: [180.0, 179.5, 179.0, 178.8, 179.2, 179.5, 179.0, 178.5, 178.2, 178.0, 178.3, 178.5, 178.8, 179.0, 178.7, 178.5, 178.3, 178.1, 178.4, 178.6, 178.3, 178.5, 178.4, 178.50]),
      WatchAsset(symbol: "MATIC", name: "Polygon", valueUsd: 3_999.00, nativePriceUsd: 1.08, priceChange24h: 1.20, percentage: 3.1, sparkline7d: [1.02, 1.04, 1.05, 1.06, 1.07, 1.075, 1.08], sparkline24h: [1.05, 1.052, 1.055, 1.058, 1.06, 1.062, 1.065, 1.068, 1.07, 1.069, 1.071, 1.073, 1.075, 1.074, 1.076, 1.078, 1.075, 1.077, 1.079, 1.08, 1.078, 1.08, 1.079, 1.08]),
    ]
  )
}

enum PortfolioFormatters {
  static let currencyFormatter: NumberFormatter = {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = "USD"
    formatter.maximumFractionDigits = 2
    return formatter
  }()

  static func currency(_ value: Double) -> String {
    currencyFormatter.string(from: NSNumber(value: value)) ?? "$0.00"
  }

  static func signedCurrency(_ value: Double) -> String {
    let prefix = value >= 0 ? "+" : ""
    return "\(prefix)\(currency(value))"
  }

  static func signedPercent(_ value: Double) -> String {
    let prefix = value >= 0 ? "+" : ""
    return "\(prefix)\(String(format: "%.2f", value))%"
  }

  static func compactCurrency(_ value: Double) -> String {
    let absValue = abs(value)
    let sign = value < 0 ? "-" : ""
    if absValue >= 1_000_000 {
      return "\(sign)$\(String(format: "%.1f", absValue / 1_000_000))M"
    } else if absValue >= 1_000 {
      return "\(sign)$\(String(format: "%.0f", absValue / 1_000))K"
    } else if absValue >= 1 {
      return "\(sign)$\(String(format: "%.2f", absValue))"
    } else if absValue >= 0.01 {
      return "\(sign)$\(String(format: "%.4f", absValue))"
    } else {
      return "\(sign)$\(String(format: "%.6f", absValue))"
    }
  }

  static func compactPrice(_ value: Double) -> String {
    if value >= 1_000 {
      return "$\(String(format: "%.0f", value))"
    } else if value >= 1 {
      return "$\(String(format: "%.2f", value))"
    } else if value >= 0.01 {
      return "$\(String(format: "%.4f", value))"
    } else {
      return "$\(String(format: "%.6f", value))"
    }
  }
}
