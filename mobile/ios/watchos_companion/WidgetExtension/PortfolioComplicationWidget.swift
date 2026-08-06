import SwiftUI
import WidgetKit
import AppIntents
import Foundation

// MARK: - Shared Configuration

private nonisolated enum ComplicationConfig {
  static let appGroupIdentifier = "group.com.teamcata.abct"
  static let snapshotDefaultsKey = "portfolio_snapshot_v1"
  /// Written by the watch app's FavoritesPage (@AppStorage, JSON Set<String>).
  static let favoritesDefaultsKey = "favoriteSymbols"
  static let refreshIntervalMinutes = 15
  /// The gallery is scrollable but shouldn't be a haystack. Note: chronod
  /// (watchOS 26.1, observed in its descriptor store) keeps only the FIRST
  /// 15 recommendations per widget — ordering below guarantees the truncated
  /// tail is always the least relevant (market-cap laggards).
  static let galleryCap = 25
}

// MARK: - Shared Data Models

private nonisolated struct SharedAssetSnapshot: Codable {
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

/// Market-cap-ranked token (not necessarily held); lean by payload contract.
private nonisolated struct SharedMarketAsset: Codable {
  let symbol: String
  let name: String
  let nativePriceUsd: Double
  let priceChange24h: Double
}

private nonisolated struct SharedPortfolioSnapshot: Codable {
  let totalValue: Double
  let sevenDayChange: Double
  let percentChange: Double
  let historyPoints: [Double]
  let assets: [SharedAssetSnapshot]?
  let marketAssets: [SharedMarketAsset]?
  let updatedAt: TimeInterval
}

/// One selectable token for the complication gallery and picker: a holding
/// (with sparkline) or a top-of-market token (price + 24h change only).
private nonisolated struct GalleryToken {
  let symbol: String
  let name: String
  let price: Double
  let priceChange24h: Double
  let sparkline: [Double]
  /// nil for tokens the user doesn't hold.
  let valueUsd: Double?
}

/// nonisolated: called from nonisolated timeline/entity-query contexts; the
/// project default actor isolation (MainActor) would otherwise flag data races.
private nonisolated enum WidgetDataSource {
  /// Returns the last snapshot the watch app persisted to the shared app
  /// group, or nil when no real data is available. Never fabricates data —
  /// callers must render an explicit no-data state instead.
  static func latestSnapshot() -> SharedPortfolioSnapshot? {
    guard let defaults = UserDefaults(suiteName: ComplicationConfig.appGroupIdentifier),
          let data = defaults.data(forKey: ComplicationConfig.snapshotDefaultsKey),
          let decoded = try? JSONDecoder().decode(SharedPortfolioSnapshot.self, from: data),
          !decoded.historyPoints.isEmpty
    else {
      return nil
    }
    return decoded
  }

  /// Symbols the user starred in the watch app's Favorites page.
  static func favoriteSymbols() -> Set<String> {
    guard let defaults = UserDefaults(suiteName: ComplicationConfig.appGroupIdentifier),
          let data = defaults.data(forKey: ComplicationConfig.favoritesDefaultsKey),
          let symbols = try? JSONDecoder().decode(Set<String>.self, from: data)
    else {
      return []
    }
    return Set(symbols.map { $0.uppercased() })
  }

  /// The selectable-token union for the gallery and picker, ordered:
  /// favorites first, then all holdings by value, then top-of-market tokens
  /// in market-cap order — deduped by symbol (holdings win) and capped.
  static func galleryTokens() -> [GalleryToken] {
    guard let snapshot = latestSnapshot() else { return [] }

    var seen = Set<String>()
    var pool: [GalleryToken] = []

    let holdings = (snapshot.assets ?? []).sorted { $0.valueUsd > $1.valueUsd }
    for asset in holdings {
      let symbol = asset.symbol.uppercased()
      guard seen.insert(symbol).inserted else { continue }
      pool.append(GalleryToken(
        symbol: symbol,
        name: asset.name,
        price: asset.nativePriceUsd,
        priceChange24h: asset.priceChange24h,
        sparkline: asset.sparkline7d ?? [],
        valueUsd: asset.valueUsd
      ))
    }

    for market in snapshot.marketAssets ?? [] {
      let symbol = market.symbol.uppercased()
      guard seen.insert(symbol).inserted else { continue }
      pool.append(GalleryToken(
        symbol: symbol,
        name: market.name,
        price: market.nativePriceUsd,
        priceChange24h: market.priceChange24h,
        sparkline: [],
        valueUsd: nil
      ))
    }

    let favorites = favoriteSymbols()
    let starred = pool.filter { favorites.contains($0.symbol) }
    let rest = pool.filter { !favorites.contains($0.symbol) }
    return Array((starred + rest).prefix(ComplicationConfig.galleryCap))
  }

  static func token(forSymbol symbol: String) -> GalleryToken? {
    let wanted = symbol.uppercased()
    // Uncapped lookup so a configured token resolves even when it falls
    // outside the gallery cap.
    guard let snapshot = latestSnapshot() else { return nil }
    if let asset = (snapshot.assets ?? []).first(where: { $0.symbol.uppercased() == wanted }) {
      return GalleryToken(
        symbol: wanted,
        name: asset.name,
        price: asset.nativePriceUsd,
        priceChange24h: asset.priceChange24h,
        sparkline: asset.sparkline7d ?? [],
        valueUsd: asset.valueUsd
      )
    }
    if let market = (snapshot.marketAssets ?? []).first(where: { $0.symbol.uppercased() == wanted }) {
      return GalleryToken(
        symbol: wanted,
        name: market.name,
        price: market.nativePriceUsd,
        priceChange24h: market.priceChange24h,
        sparkline: [],
        valueUsd: nil
      )
    }
    return nil
  }
}

// MARK: - Formatters

private nonisolated enum ComplicationFormatters {
  /// Shown wherever a live value is unavailable; never substitute fake numbers.
  static let noData = "——"

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

  static func compactCurrency(_ value: Double) -> String {
    let absValue = abs(value)
    let sign = value < 0 ? "-" : ""
    if absValue >= 1_000_000 {
      return "\(sign)$\(String(format: "%.1f", absValue / 1_000_000))M"
    } else if absValue >= 100_000 {
      return "\(sign)$\(String(format: "%.0f", absValue / 1_000))K"
    } else if absValue >= 1_000 {
      return "\(sign)$\(String(format: "%.1f", absValue / 1_000))K"
    } else if absValue >= 1 {
      return "\(sign)$\(String(format: "%.2f", absValue))"
    } else if absValue >= 0.01 {
      return "\(sign)$\(String(format: "%.4f", absValue))"
    } else {
      return "\(sign)$\(String(format: "%.6f", absValue))"
    }
  }

  static func compactPrice(_ value: Double) -> String {
    if value >= 100_000 {
      return "$\(String(format: "%.0f", value / 1_000))K"
    } else if value >= 1_000 {
      return "$\(String(format: "%.0f", value))"
    } else if value >= 100 {
      return "$\(String(format: "%.1f", value))"
    } else if value >= 1 {
      return "$\(String(format: "%.2f", value))"
    } else if value >= 0.01 {
      return "$\(String(format: "%.4f", value))"
    } else {
      return "$\(String(format: "%.6f", value))"
    }
  }

  static func signedPercent(_ value: Double) -> String {
    let prefix = value >= 0 ? "+" : ""
    return "\(prefix)\(String(format: "%.1f", value))%"
  }

  static func trendArrow(_ value: Double) -> String {
    value >= 0 ? "\u{2197}" : "\u{2198}"
  }
}

// MARK: - Sparkline Shape

private struct SparklineShape: Shape {
  let points: [Double]

  func path(in rect: CGRect) -> Path {
    guard points.count > 1 else { return Path() }

    let minY = points.min() ?? 0
    let maxY = points.max() ?? 0
    let ySpan = max(maxY - minY, 0.0001)
    let stepX = rect.width / CGFloat(points.count - 1)

    func yPosition(for value: Double) -> CGFloat {
      let normalized = (value - minY) / ySpan
      return rect.maxY - CGFloat(normalized) * rect.height
    }

    var path = Path()
    path.move(to: CGPoint(x: rect.minX, y: yPosition(for: points[0])))

    for index in 1..<points.count {
      let x = rect.minX + CGFloat(index) * stepX
      let y = yPosition(for: points[index])
      path.addLine(to: CGPoint(x: x, y: y))
    }

    return path
  }
}

// MARK: - ============================================
// MARK: - TOKEN PRICE COMPLICATION (Configurable)
// MARK: - ============================================

/// AppEntity representing a selectable token for complication configuration.
struct TokenEntity: AppEntity {
  static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Token")

  static var defaultQuery = TokenEntityQuery()

  var id: String
  var symbol: String
  var name: String

  var displayRepresentation: DisplayRepresentation {
    DisplayRepresentation(title: "\(symbol)", subtitle: "\(name)")
  }
}

/// Query that provides available tokens from the shared portfolio data.
struct TokenEntityQuery: EntityQuery {
  func entities(for identifiers: [String]) async -> [TokenEntity] {
    identifiers.compactMap { id in
      guard let token = WidgetDataSource.token(forSymbol: id) else { return nil }
      return TokenEntity(id: token.symbol, symbol: token.symbol, name: token.name)
    }
  }

  func suggestedEntities() async -> [TokenEntity] {
    WidgetDataSource.galleryTokens().map { token in
      TokenEntity(id: token.symbol, symbol: token.symbol, name: token.name)
    }
  }

  func defaultResult() async -> TokenEntity? {
    // Unconfigured default stays the highest-value HOLDING; market-only
    // tokens never self-select.
    guard let top = WidgetDataSource.latestSnapshot()?.assets?.max(by: { $0.valueUsd < $1.valueUsd })
    else { return nil }
    return TokenEntity(id: top.symbol.uppercased(), symbol: top.symbol.uppercased(), name: top.name)
  }
}

/// AppIntent for configuring which token to display in a complication slot.
struct SelectTokenIntent: WidgetConfigurationIntent {
  static var title: LocalizedStringResource = "Select Token"
  static var description: IntentDescription = "Choose which token price to display on your watch face."

  @Parameter(title: "Token")
  var token: TokenEntity?
}

// MARK: - Token Complication Entry

struct TokenComplicationEntry: TimelineEntry {
  let date: Date
  let symbol: String
  let name: String
  /// nil = no live data; views must render a no-data state, never a number.
  let price: Double?
  let priceChange24h: Double?
  let sparkline: [Double]

  /// Sample entry for the face gallery ONLY (WidgetKit's placeholder API,
  /// where illustrative data is expected). Never returned as live content.
  static var placeholder: TokenComplicationEntry {
    TokenComplicationEntry(
      date: Date(),
      symbol: "BTC",
      name: "Bitcoin",
      price: 97_443.57,
      priceChange24h: 2.35,
      sparkline: [94_100, 95_200, 96_800, 95_900, 97_100, 96_500, 97_443.57]
    )
  }

  static func noData(symbol: String) -> TokenComplicationEntry {
    TokenComplicationEntry(
      date: Date(),
      symbol: symbol,
      name: "",
      price: nil,
      priceChange24h: nil,
      sparkline: []
    )
  }
}

// MARK: - Token Complication Provider

struct TokenComplicationProvider: AppIntentTimelineProvider {
  func placeholder(in context: Context) -> TokenComplicationEntry {
    .placeholder
  }

  func snapshot(for configuration: SelectTokenIntent, in context: Context) async -> TokenComplicationEntry {
    // The gallery preview may show sample data; a live snapshot must not.
    if context.isPreview {
      return .placeholder
    }
    return liveEntry(for: configuration)
  }

  func timeline(for configuration: SelectTokenIntent, in context: Context) async -> Timeline<TokenComplicationEntry> {
    let entry = liveEntry(for: configuration)
    let nextRefresh = Calendar.current.date(
      byAdding: .minute,
      value: ComplicationConfig.refreshIntervalMinutes,
      to: Date()
    ) ?? Date().addingTimeInterval(TimeInterval(ComplicationConfig.refreshIntervalMinutes * 60))

    return Timeline(entries: [entry], policy: .after(nextRefresh))
  }

  /// watchOS requires explicit recommendations for configurable complications
  /// to appear in the watch face gallery. The entry list IS the token picker
  /// on watchOS: favorites first, then holdings by value, then top-of-market
  /// tokens. The watch app invalidates these when data or favorites change.
  func recommendations() -> [AppIntentRecommendation<SelectTokenIntent>] {
    let tokens = WidgetDataSource.galleryTokens()

    guard !tokens.isEmpty else {
      return [AppIntentRecommendation(intent: SelectTokenIntent(), description: "Token Price")]
    }

    return tokens.map { token in
      let intent = SelectTokenIntent()
      intent.token = TokenEntity(id: token.symbol, symbol: token.symbol, name: token.name)
      // Text(verbatim:) is required: an interpolated description becomes
      // FORMATTED text and WidgetKit hard-traps on it ("Formatted text for
      // `AppIntentRecommendation` is not supported"), killing the extension
      // during every gallery query and freezing the picker on stale entries.
      return AppIntentRecommendation(intent: intent, description: Text(verbatim: "\(token.symbol) Price"))
    }
  }

  private func liveEntry(for configuration: SelectTokenIntent) -> TokenComplicationEntry {
    if let symbol = configuration.token?.symbol {
      guard let token = WidgetDataSource.token(forSymbol: symbol) else {
        return .noData(symbol: symbol.uppercased())
      }
      return liveEntry(for: token)
    }

    // Unconfigured slot: default to the highest-value holding.
    guard let top = WidgetDataSource.latestSnapshot()?.assets?.max(by: { $0.valueUsd < $1.valueUsd }),
          let token = WidgetDataSource.token(forSymbol: top.symbol)
    else {
      return .noData(symbol: "TOKEN")
    }
    return liveEntry(for: token)
  }

  private func liveEntry(for token: GalleryToken) -> TokenComplicationEntry {
    TokenComplicationEntry(
      date: Date(),
      symbol: token.symbol,
      name: token.name,
      price: token.price,
      priceChange24h: token.priceChange24h,
      sparkline: token.sparkline
    )
  }
}

// MARK: - Token Complication Views

/// Rectangular: "BTC $97,443 +2.4%" with mini sparkline
struct TokenRectangularView: View {
  let entry: TokenComplicationEntry

  private var changeColor: Color {
    guard let change = entry.priceChange24h else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    HStack(spacing: 6) {
      VStack(alignment: .leading, spacing: 2) {
        Text(entry.symbol)
          .font(.system(size: 13, weight: .bold))
          .foregroundStyle(.white)

        Text(entry.price.map(ComplicationFormatters.compactPrice) ?? ComplicationFormatters.noData)
          .font(.system(size: 16, weight: .bold, design: .rounded))
          .monospacedDigit()
          .foregroundStyle(.white)
          .lineLimit(1)
          .minimumScaleFactor(0.7)

        if let change = entry.priceChange24h {
          Text(ComplicationFormatters.signedPercent(change))
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .monospacedDigit()
            .foregroundStyle(changeColor)
        }
      }

      if entry.sparkline.count > 1 {
        SparklineShape(points: entry.sparkline)
          .stroke(
            LinearGradient(
              colors: (entry.priceChange24h ?? 0) >= 0 ? [.cyan, .green] : [.orange, .red],
              startPoint: .leading,
              endPoint: .trailing
            ),
            style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round)
          )
          .frame(width: 44, height: 22)
      }
    }
    .padding(.vertical, 2)
  }
}

/// Circular: Token symbol + compact price in a ring
struct TokenCircularView: View {
  let entry: TokenComplicationEntry

  private var changeColor: Color {
    guard let change = entry.priceChange24h else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    VStack(spacing: 1) {
      Text(entry.symbol)
        .font(.system(size: 10, weight: .bold))
        .foregroundStyle(.white)
        .lineLimit(1)
        .minimumScaleFactor(0.6)

      Text(entry.price.map(ComplicationFormatters.compactPrice) ?? ComplicationFormatters.noData)
        .font(.system(size: 11, weight: .bold, design: .rounded))
        .monospacedDigit()
        .foregroundStyle(changeColor)
        .lineLimit(1)
        .minimumScaleFactor(0.5)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

/// Inline: "BTC $97K ↗"
struct TokenInlineView: View {
  let entry: TokenComplicationEntry

  var body: some View {
    let price = entry.price.map(ComplicationFormatters.compactPrice) ?? ComplicationFormatters.noData
    let arrow = entry.priceChange24h.map { " \(ComplicationFormatters.trendArrow($0))" } ?? ""
    Text("\(entry.symbol) \(price)\(arrow)")
  }
}

/// Corner: Compact price with gauge showing 24h change
struct TokenCornerView: View {
  let entry: TokenComplicationEntry

  private var changeColor: Color {
    guard let change = entry.priceChange24h else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    VStack(spacing: 0) {
      Text(entry.symbol)
        .font(.system(size: 10, weight: .bold))
        .foregroundStyle(.white)
        .lineLimit(1)

      Text(entry.price.map(ComplicationFormatters.compactPrice) ?? ComplicationFormatters.noData)
        .font(.system(size: 12, weight: .bold, design: .rounded))
        .monospacedDigit()
        .foregroundStyle(changeColor)
        .lineLimit(1)
        .minimumScaleFactor(0.6)
    }
  }
}

/// Token complication entry view that dispatches based on widget family
struct TokenComplicationEntryView: View {
  @Environment(\.widgetFamily) private var family
  let entry: TokenComplicationEntry

  var body: some View {
    switch family {
    case .accessoryCircular:
      TokenCircularView(entry: entry)
    case .accessoryInline:
      TokenInlineView(entry: entry)
    case .accessoryCorner:
      TokenCornerView(entry: entry)
    default:
      TokenRectangularView(entry: entry)
    }
  }
}

// MARK: - Token Price Widget Definition

struct TokenPriceWidget: Widget {
  let kind = "TokenPriceWidget"

  var body: some WidgetConfiguration {
    AppIntentConfiguration(
      kind: kind,
      intent: SelectTokenIntent.self,
      provider: TokenComplicationProvider()
    ) { entry in
      TokenComplicationEntryView(entry: entry)
        .containerBackground(.black, for: .widget)
    }
    .configurationDisplayName("Token Price")
    .description("Shows the live price and 24h change for a token from your portfolio.")
    .supportedFamilies([
      .accessoryRectangular,
      .accessoryCircular,
      .accessoryInline,
      .accessoryCorner,
    ])
  }
}

// MARK: - ============================================
// MARK: - PORTFOLIO OVERVIEW COMPLICATION (Static)
// MARK: - ============================================

struct PortfolioComplicationEntry: TimelineEntry {
  let date: Date
  /// nil = no live data; views must render a no-data state, never a number.
  let totalValue: Double?
  let percentChange: Double?
  let historyPoints: [Double]

  /// Sample entry for the face gallery ONLY (WidgetKit's placeholder API,
  /// where illustrative data is expected). Never returned as live content.
  static var placeholder: PortfolioComplicationEntry {
    PortfolioComplicationEntry(
      date: Date(),
      totalValue: 128_442.63,
      percentChange: 4.20,
      historyPoints: [121_190.0, 122_010.0, 123_420.0, 122_840.0, 125_090.0, 126_910.0, 128_442.63]
    )
  }

  static var noData: PortfolioComplicationEntry {
    PortfolioComplicationEntry(date: Date(), totalValue: nil, percentChange: nil, historyPoints: [])
  }
}

struct PortfolioComplicationProvider: TimelineProvider {
  func placeholder(in context: Context) -> PortfolioComplicationEntry {
    .placeholder
  }

  func getSnapshot(in context: Context, completion: @escaping (PortfolioComplicationEntry) -> Void) {
    // The gallery preview may show sample data; a live snapshot must not.
    completion(context.isPreview ? .placeholder : liveEntry())
  }

  func getTimeline(in context: Context, completion: @escaping (Timeline<PortfolioComplicationEntry>) -> Void) {
    let now = Date()
    let entry = liveEntry()

    let nextRefresh = Calendar.current.date(
      byAdding: .minute,
      value: ComplicationConfig.refreshIntervalMinutes,
      to: now
    ) ?? now.addingTimeInterval(TimeInterval(ComplicationConfig.refreshIntervalMinutes * 60))

    completion(Timeline(entries: [entry], policy: .after(nextRefresh)))
  }

  private func liveEntry() -> PortfolioComplicationEntry {
    guard let snapshot = WidgetDataSource.latestSnapshot() else {
      return .noData
    }
    return PortfolioComplicationEntry(
      date: Date(),
      totalValue: snapshot.totalValue,
      percentChange: snapshot.percentChange,
      historyPoints: snapshot.historyPoints
    )
  }
}

// MARK: - Portfolio Complication Views

struct PortfolioRectangularView: View {
  let entry: PortfolioComplicationEntry

  private var changeColor: Color {
    guard let change = entry.percentChange else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 3) {
      HStack {
        Text("Portfolio")
          .font(.system(size: 11, weight: .medium))
          .foregroundStyle(.secondary)
        Spacer()
        if let change = entry.percentChange {
          Text(ComplicationFormatters.signedPercent(change))
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .monospacedDigit()
            .foregroundStyle(changeColor)
        }
      }

      Text(entry.totalValue.map(ComplicationFormatters.currency) ?? ComplicationFormatters.noData)
        .font(.system(size: 18, weight: .bold, design: .rounded))
        .monospacedDigit()
        .lineLimit(1)
        .minimumScaleFactor(0.7)

      if entry.historyPoints.count > 1 {
        SparklineShape(points: entry.historyPoints)
          .stroke(
            LinearGradient(
              colors: (entry.percentChange ?? 0) >= 0 ? [.cyan, .green] : [.orange, .red],
              startPoint: .leading,
              endPoint: .trailing
            ),
            style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round)
          )
          .frame(height: 16)
      }
    }
    .padding(.vertical, 2)
  }
}

/// Circular: compact dollar value front and center ("$15.2K"), colored by the
/// 7-day change. The value is the point — not a sparkline (user feedback).
struct PortfolioCircularView: View {
  let entry: PortfolioComplicationEntry

  private var changeColor: Color {
    guard let change = entry.percentChange else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    VStack(spacing: 1) {
      Text("ABCT")
        .font(.system(size: 9, weight: .semibold))
        .foregroundStyle(.secondary)
        .lineLimit(1)
        .minimumScaleFactor(0.6)

      Text(entry.totalValue.map(ComplicationFormatters.compactCurrency) ?? ComplicationFormatters.noData)
        .font(.system(size: 12, weight: .bold, design: .rounded))
        .monospacedDigit()
        .foregroundStyle(changeColor)
        .lineLimit(1)
        .minimumScaleFactor(0.5)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

/// Inline: "ABCT $15.2K +1.2%"
struct PortfolioInlineView: View {
  let entry: PortfolioComplicationEntry

  var body: some View {
    let value = entry.totalValue.map(ComplicationFormatters.compactCurrency) ?? ComplicationFormatters.noData
    let percent = entry.percentChange.map { " \(ComplicationFormatters.signedPercent($0))" } ?? ""
    Text("ABCT \(value)\(percent)")
  }
}

struct PortfolioCornerView: View {
  let entry: PortfolioComplicationEntry

  private var changeColor: Color {
    guard let change = entry.percentChange else { return .secondary }
    return change >= 0 ? .green : .red
  }

  var body: some View {
    VStack(spacing: 0) {
      Text("ABCT")
        .font(.system(size: 10, weight: .bold))
        .foregroundStyle(.white)
        .lineLimit(1)

      Text(entry.totalValue.map(ComplicationFormatters.compactCurrency) ?? ComplicationFormatters.noData)
        .font(.system(size: 12, weight: .bold, design: .rounded))
        .monospacedDigit()
        .foregroundStyle(changeColor)
        .lineLimit(1)
        .minimumScaleFactor(0.6)
    }
  }
}

struct PortfolioComplicationEntryView: View {
  @Environment(\.widgetFamily) private var family
  let entry: PortfolioComplicationEntry

  var body: some View {
    switch family {
    case .accessoryCircular:
      PortfolioCircularView(entry: entry)
    case .accessoryInline:
      PortfolioInlineView(entry: entry)
    case .accessoryCorner:
      PortfolioCornerView(entry: entry)
    default:
      PortfolioRectangularView(entry: entry)
    }
  }
}

struct PortfolioComplicationWidget: Widget {
  let kind = "PortfolioComplicationWidget"

  var body: some WidgetConfiguration {
    StaticConfiguration(kind: kind, provider: PortfolioComplicationProvider()) { entry in
      PortfolioComplicationEntryView(entry: entry)
        .containerBackground(.black, for: .widget)
    }
    .configurationDisplayName("Portfolio Total")
    .description("Shows total portfolio value with a 7-day trend sparkline.")
    .supportedFamilies([
      .accessoryRectangular,
      .accessoryCircular,
      .accessoryInline,
      .accessoryCorner,
    ])
  }
}

// MARK: - ============================================
// MARK: - WIDGET BUNDLE (Registers Both Complications)
// MARK: - ============================================

@main
struct ABCTComplicationBundle: WidgetBundle {
  @WidgetBundleBuilder
  var body: some Widget {
    TokenPriceWidget()
    PortfolioComplicationWidget()
  }
}
