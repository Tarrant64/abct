import Flutter
import UIKit
import workmanager_apple

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var portfolioWatchSyncBridge: PortfolioWatchSyncBridge?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Plugin registration and method channel setup moved to
    // didInitializeImplicitFlutterEngine for UIScene lifecycle support.

    // BGTaskScheduler handlers must be registered before launch completes —
    // this cannot wait for the Flutter engine. The identifier must match
    // kPortfolioSyncTask (background_sync.dart) and
    // BGTaskSchedulerPermittedIdentifiers (Info.plist). The frequency is the
    // reschedule floor for the BGAppRefreshTask chain; iOS decides the actual
    // run times opportunistically.
    WorkmanagerPlugin.registerPeriodicTask(
      withIdentifier: "com.abct.portfolioSync",
      frequency: NSNumber(value: 60 * 60)
    )

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  // UIScene lifecycle: plugins and method channels are initialized here
  // instead of didFinishLaunchingWithOptions, because the FlutterViewController
  // is not yet available at launch time under the UIScene lifecycle.
  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    // Set up the watch sync method channel using the engine bridge's messenger
    let messenger = engineBridge.applicationRegistrar.messenger()
    portfolioWatchSyncBridge = PortfolioWatchSyncBridge(binaryMessenger: messenger)
  }
}
