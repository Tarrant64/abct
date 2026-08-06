import SwiftUI

@main
struct PortfolioWatchApp: App {
  @State private var model = SharedPortfolioSnapshotStore.load() ?? .sample

  init() {
    // Wire the WCSession delegate before any UI exists; background launches
    // (complication pushes, application context) deliver at app start, and
    // waiting for .onAppear would drop them.
    WatchHandoffController.shared.start()
  }

  var body: some Scene {
    WindowGroup {
      PortfolioTabView(
        data: model,
        onRefresh: refresh,
        onHandoff: handoffToPhone
      )
      .onAppear {
        // Data arrivals only reload locally — never re-request, or the
        // request → reply → notify cycle would loop forever.
        WatchHandoffController.shared.onDataReceived = { [self] in
          reloadFromStore()
        }
      }
    }
  }

  /// Refresh button: ask the phone for a fresh snapshot, and show whatever
  /// is stored right now; onDataReceived reloads again when the reply lands.
  private func refresh() {
    WatchHandoffController.shared.requestSnapshot()
    reloadFromStore()
  }

  private func reloadFromStore() {
    model = SharedPortfolioSnapshotStore.load() ?? .sample
  }

  private func handoffToPhone() {
    WatchHandoffController.shared.requestOpenOnPhone()
  }
}
