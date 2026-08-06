import Foundation
import WatchConnectivity
import WidgetKit

final class WatchHandoffController: NSObject {
  static let shared = WatchHandoffController()

  var onDataReceived: (() -> Void)?

  private override init() {
    super.init()
    activateSessionIfNeeded()
  }

  /// Ensures the singleton exists and its WCSession delegate is wired.
  /// Called from the App initializer so deliveries that wake the app in the
  /// background (complication pushes, application context) are not dropped
  /// before the first view appears.
  func start() {}

  private func activateSessionIfNeeded() {
    guard WCSession.isSupported() else { return }
    let session = WCSession.default
    session.delegate = self
    session.activate()
  }

  func requestOpenOnPhone() {
    guard WCSession.isSupported() else { return }
    let session = WCSession.default
    if session.activationState != .activated {
      session.activate()
    }
    if session.isReachable {
      session.sendMessage(["action": "open_portfolio"], replyHandler: nil)
    }
  }

  /// Refresh button: ask the phone for its latest snapshot. Sending a message
  /// wakes the iPhone app in the background, which replies from its persisted
  /// cache. When the phone is unreachable, fall back to the newest
  /// application context WatchConnectivity has already delivered.
  func requestSnapshot() {
    guard WCSession.isSupported() else {
      return
    }
    let session = WCSession.default
    guard session.activationState == .activated, session.isReachable else {
      adoptReceivedApplicationContext()
      return
    }

    session.sendMessage(
      ["action": "request_snapshot"],
      replyHandler: { [weak self] reply in
        if reply["totalValue"] != nil {
          self?.persistAndNotify(payload: reply)
        } else {
          self?.adoptReceivedApplicationContext()
        }
      },
      errorHandler: { [weak self] _ in
        self?.adoptReceivedApplicationContext()
      }
    )
  }

  /// Persists the last application context the session delivered, if it is
  /// newer than what's stored. Covers deliveries missed while the app wasn't
  /// running and delegate callbacks that never fired.
  private func adoptReceivedApplicationContext() {
    let context = WCSession.default.receivedApplicationContext
    guard let updatedAt = context["updatedAt"] as? Double, context["totalValue"] != nil else {
      return
    }
    if let stored = storedSnapshotUpdatedAt(), stored >= updatedAt {
      return
    }
    persistAndNotify(payload: context)
  }

  private func storedSnapshotUpdatedAt() -> Double? {
    guard let defaults = UserDefaults(suiteName: "group.com.teamcata.abct"),
          let data = defaults.data(forKey: "portfolio_snapshot_v1"),
          let object = try? JSONSerialization.jsonObject(with: data),
          let payload = object as? [String: Any]
    else {
      return nil
    }
    return payload["updatedAt"] as? Double
  }

  private func persistAndNotify(payload: [String: Any]) {
    guard let defaults = UserDefaults(suiteName: "group.com.teamcata.abct") else { return }

    // Only persist if payload contains expected portfolio data
    guard payload["totalValue"] != nil else { return }

    if let jsonData = try? JSONSerialization.data(withJSONObject: payload) {
      defaults.set(jsonData, forKey: "portfolio_snapshot_v1")
      // Fresh data just landed — refresh complications now instead of
      // leaving them stale until their next scheduled timeline reload, and
      // rebuild the gallery's per-token recommendations from the new holdings.
      WidgetCenter.shared.reloadAllTimelines()
      WidgetCenter.shared.invalidateConfigurationRecommendations()
    }

    DispatchQueue.main.async { [weak self] in
      self?.onDataReceived?()
    }
  }
}

extension WatchHandoffController: WCSessionDelegate {
  func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
    guard activationState == .activated else { return }
    // Catch up on anything delivered while the app wasn't running, and make
    // sure complication recommendations reflect the on-watch holdings even
    // when no new push arrives this launch.
    adoptReceivedApplicationContext()
    if storedSnapshotUpdatedAt() != nil {
      WidgetCenter.shared.invalidateConfigurationRecommendations()
    }
  }

  func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
    if message["totalValue"] != nil {
      persistAndNotify(payload: message)
    }
  }

  func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
    if userInfo["totalValue"] != nil {
      persistAndNotify(payload: userInfo)
    }
  }

  func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
    if applicationContext["totalValue"] != nil {
      persistAndNotify(payload: applicationContext)
    }
  }
}
