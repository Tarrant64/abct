import Flutter
import Foundation
import UIKit
import WatchConnectivity

private enum WatchSyncConfig {
  static let methodChannel = "abct/watch_sync"
  static let appGroupIdentifier = "group.com.teamcata.abct"
  static let snapshotDefaultsKey = "portfolio_snapshot_v1"
  static let handoffURL = "abctmobile://portfolio"
}

private struct AssetSnapshot: Codable {
  let symbol: String
  let name: String
  let valueUsd: Double
  let nativePriceUsd: Double
  let priceChange24h: Double
  let percentage: Double
  let imageUrl: String
  let sparkline7d: [Double]
  let sparkline24h: [Double]
}

/// Market-cap-ranked token (not necessarily held) for watch complication
/// tracking. Lean by contract — no sparklines or holdings context.
private struct MarketAssetSnapshot: Codable {
  let symbol: String
  let name: String
  let nativePriceUsd: Double
  let priceChange24h: Double
}

private struct PortfolioSnapshot: Codable {
  let totalValue: Double
  let sevenDayChange: Double
  let percentChange: Double
  let historyPoints: [Double]
  let assets: [AssetSnapshot]
  let marketAssets: [MarketAssetSnapshot]
  let updatedAt: TimeInterval

  var wcPayload: [String: Any] {
    [
      "totalValue": totalValue,
      "sevenDayChange": sevenDayChange,
      "percentChange": percentChange,
      "historyPoints": historyPoints,
      "assets": assets.map { asset in
        [
          "symbol": asset.symbol,
          "name": asset.name,
          "valueUsd": asset.valueUsd,
          "nativePriceUsd": asset.nativePriceUsd,
          "priceChange24h": asset.priceChange24h,
          "percentage": asset.percentage,
          "imageUrl": asset.imageUrl,
          "sparkline7d": asset.sparkline7d,
          "sparkline24h": asset.sparkline24h,
        ] as [String: Any]
      },
      "marketAssets": marketAssets.map { market in
        [
          "symbol": market.symbol,
          "name": market.name,
          "nativePriceUsd": market.nativePriceUsd,
          "priceChange24h": market.priceChange24h,
        ] as [String: Any]
      },
      "updatedAt": updatedAt,
    ]
  }
}

final class PortfolioWatchSyncBridge: NSObject {
  private let channel: FlutterMethodChannel
  private let defaults: UserDefaults?

  init(binaryMessenger: FlutterBinaryMessenger) {
    self.channel = FlutterMethodChannel(
      name: WatchSyncConfig.methodChannel,
      binaryMessenger: binaryMessenger
    )
    self.defaults = UserDefaults(suiteName: WatchSyncConfig.appGroupIdentifier)
    super.init()

    activateWatchSessionIfNeeded()
    registerChannelHandler()
  }

  private func registerChannelHandler() {
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(FlutterError(code: "bridge_deallocated", message: "Bridge unavailable", details: nil))
        return
      }

      switch call.method {
      case "updateSnapshot":
        self.handleUpdateSnapshot(call: call, result: result)
      case "openPortfolio":
        self.openPortfolioOnPhone()
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// Track last synced totalValue to avoid redundant complication pushes.
  private var lastSyncedTotalValue: Double = -1

  private func handleUpdateSnapshot(call: FlutterMethodCall, result: FlutterResult) {
    guard let args = call.arguments as? [String: Any] else {
      result(FlutterError(code: "invalid_args", message: "Arguments must be a map", details: nil))
      return
    }

    guard let snapshot = parseSnapshot(from: args) else {
      result(FlutterError(code: "invalid_payload", message: "Missing required snapshot fields", details: nil))
      return
    }

    persist(snapshot: snapshot)

    // Complication pushes draw from a daily budget (~50/day); spend one only
    // when the portfolio value actually changed (>$1 difference).
    let valueDelta = abs(snapshot.totalValue - lastSyncedTotalValue)
    let updatesComplication = valueDelta > 1.0
    transfer(snapshot: snapshot, updatesComplication: updatesComplication)
    if updatesComplication {
      lastSyncedTotalValue = snapshot.totalValue
    }

    result(nil)
  }

  private func parseSnapshot(from args: [String: Any]) -> PortfolioSnapshot? {
    guard
      let totalValue = asDouble(args["totalValue"]),
      let sevenDayChange = asDouble(args["sevenDayChange"]),
      let percentChange = asDouble(args["percentChange"]),
      let rawHistory = args["historyPoints"] as? [Any]
    else {
      return nil
    }

    let historyPoints = rawHistory.compactMap(asDouble)
    if historyPoints.isEmpty {
      return nil
    }

    var assets: [AssetSnapshot] = []
    if let rawAssets = args["assets"] as? [[String: Any]] {
      assets = rawAssets.compactMap { dict in
        guard
          let symbol = dict["symbol"] as? String,
          let name = dict["name"] as? String,
          let valueUsd = asDouble(dict["valueUsd"]),
          let nativePriceUsd = asDouble(dict["nativePriceUsd"])
        else {
          return nil
        }
        let rawSparkline = (dict["sparkline7d"] as? [Any])?.compactMap(asDouble) ?? []
        let rawSparkline24h = (dict["sparkline24h"] as? [Any])?.compactMap(asDouble) ?? []
        return AssetSnapshot(
          symbol: symbol,
          name: name,
          valueUsd: valueUsd,
          nativePriceUsd: nativePriceUsd,
          priceChange24h: asDouble(dict["priceChange24h"]) ?? 0,
          percentage: asDouble(dict["percentage"]) ?? 0,
          imageUrl: dict["imageUrl"] as? String ?? "",
          sparkline7d: rawSparkline,
          sparkline24h: rawSparkline24h
        )
      }
    }

    var marketAssets: [MarketAssetSnapshot] = []
    if let rawMarket = args["marketAssets"] as? [[String: Any]] {
      marketAssets = rawMarket.compactMap { dict in
        guard
          let symbol = dict["symbol"] as? String,
          let name = dict["name"] as? String,
          let nativePriceUsd = asDouble(dict["nativePriceUsd"])
        else {
          return nil
        }
        return MarketAssetSnapshot(
          symbol: symbol,
          name: name,
          nativePriceUsd: nativePriceUsd,
          priceChange24h: asDouble(dict["priceChange24h"]) ?? 0
        )
      }
    }

    return PortfolioSnapshot(
      totalValue: totalValue,
      sevenDayChange: sevenDayChange,
      percentChange: percentChange,
      historyPoints: historyPoints,
      assets: assets,
      marketAssets: marketAssets,
      updatedAt: Date().timeIntervalSince1970
    )
  }

  private func persist(snapshot: PortfolioSnapshot) {
    guard let defaults else { return }
    let encoder = JSONEncoder()
    guard let encoded = try? encoder.encode(snapshot) else { return }
    defaults.set(encoded, forKey: WatchSyncConfig.snapshotDefaultsKey)
  }

  /// Transfer waiting for session activation. WCSession.activate() completes
  /// asynchronously, and updateApplicationContext throws until it does — the
  /// very first push after a cold launch would otherwise be silently dropped.
  private var pendingTransfer: (payload: [String: Any], updatesComplication: Bool)?

  private func transfer(snapshot: PortfolioSnapshot, updatesComplication: Bool) {
    guard WCSession.isSupported() else { return }
    let session = WCSession.default

    if session.activationState != .activated {
      pendingTransfer = (snapshot.wcPayload, updatesComplication)
      session.activate()
      return
    }

    deliver(payload: snapshot.wcPayload, updatesComplication: updatesComplication, via: session)
  }

  private func deliver(payload: [String: Any], updatesComplication: Bool, via session: WCSession) {
    // Latest-wins delivery: application context replaces any undelivered
    // snapshot rather than queueing stale ones like transferUserInfo would.
    try? session.updateApplicationContext(payload)

    if session.isReachable {
      session.sendMessage(payload, replyHandler: nil)
    }

    if updatesComplication {
      session.transferCurrentComplicationUserInfo(payload)
    }
  }

  /// Answers the watch's refresh button: the last snapshot this bridge
  /// persisted, decoded back to a plist-safe dictionary, or nil if none.
  private func lastPersistedPayload() -> [String: Any]? {
    guard let defaults,
          let data = defaults.data(forKey: WatchSyncConfig.snapshotDefaultsKey),
          let object = try? JSONSerialization.jsonObject(with: data),
          let payload = object as? [String: Any]
    else {
      return nil
    }
    return payload
  }

  private func openPortfolioOnPhone() {
    guard let url = URL(string: WatchSyncConfig.handoffURL) else { return }
    UIApplication.shared.open(url)
  }

  private func activateWatchSessionIfNeeded() {
    guard WCSession.isSupported() else { return }
    let session = WCSession.default
    session.delegate = self
    session.activate()
  }

  private func asDouble(_ value: Any?) -> Double? {
    switch value {
    case let d as Double:
      return d
    case let i as Int:
      return Double(i)
    case let n as NSNumber:
      return n.doubleValue
    case let s as String:
      return Double(s)
    default:
      return nil
    }
  }
}

extension PortfolioWatchSyncBridge: WCSessionDelegate {
  func session(
    _ session: WCSession,
    activationDidCompleteWith activationState: WCSessionActivationState,
    error: Error?
  ) {
    guard activationState == .activated, let pending = pendingTransfer else { return }
    pendingTransfer = nil
    deliver(payload: pending.payload, updatesComplication: pending.updatesComplication, via: session)
  }

  func sessionDidBecomeInactive(_ session: WCSession) {}

  func sessionDidDeactivate(_ session: WCSession) {
    session.activate()
  }

  func session(
    _ session: WCSession,
    didReceiveMessage message: [String: Any]
  ) {
    guard let action = message["action"] as? String, action == "open_portfolio" else {
      return
    }

    DispatchQueue.main.async { [weak self] in
      self?.openPortfolioOnPhone()
    }
  }

  /// Reply path for the watch's refresh button. Sending a message from the
  /// watch wakes this app in the background, so the reply works even when
  /// the phone app isn't foreground — it answers from the persisted snapshot
  /// without needing the Flutter layer.
  func session(
    _ session: WCSession,
    didReceiveMessage message: [String: Any],
    replyHandler: @escaping ([String: Any]) -> Void
  ) {
    guard let action = message["action"] as? String, action == "request_snapshot" else {
      replyHandler([:])
      return
    }
    replyHandler(lastPersistedPayload() ?? [:])
  }
}
