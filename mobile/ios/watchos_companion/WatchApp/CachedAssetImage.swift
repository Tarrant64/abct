import CryptoKit
import SwiftUI

/// Disk-cached image loader for watchOS.
/// - Caches successful loads to disk so they survive app restarts.
/// - Tracks failed URLs for 1 hour to avoid retrying broken URLs and draining battery.
/// - Falls back to a deterministic letter badge when image is unavailable.
struct CachedAssetImage: View {
  let url: String
  let symbol: String
  let size: CGFloat

  @State private var loadedImage: UIImage?
  @State private var didAttempt = false

  var body: some View {
    Group {
      if let image = loadedImage {
        Image(uiImage: image)
          .resizable()
          .scaledToFit()
          .frame(width: size, height: size)
          .clipShape(Circle())
      } else {
        letterBadge
      }
    }
    .task(id: url) {
      guard !url.isEmpty, !didAttempt else { return }
      didAttempt = true
      loadedImage = await ImageDiskCache.shared.image(for: url, size: size)
    }
  }

  private var letterBadge: some View {
    let colors: [Color] = [.blue, .purple, .orange, .teal, .pink, .indigo, .mint, .cyan]
    let hash = symbol.unicodeScalars.reduce(0) { $0 + Int($1.value) }
    return Text(String(symbol.prefix(1)))
      .font(.system(size: size * 0.46, weight: .bold, design: .rounded))
      .foregroundStyle(.white)
      .frame(width: size, height: size)
      .background(colors[hash % colors.count], in: Circle())
  }
}

/// Singleton disk cache for asset images.
/// Thread-safe via actor isolation.
actor ImageDiskCache {
  static let shared = ImageDiskCache()

  private let cacheDir: URL
  private let failureDir: URL
  private let failureTTL: TimeInterval = 3600 // 1 hour
  private let session: URLSession

  private init() {
    let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
    cacheDir = base.appendingPathComponent("asset_images", isDirectory: true)
    failureDir = base.appendingPathComponent("asset_failures", isDirectory: true)

    try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    try? FileManager.default.createDirectory(at: failureDir, withIntermediateDirectories: true)

    let config = URLSessionConfiguration.default
    config.urlCache = nil // We manage our own disk cache
    config.timeoutIntervalForRequest = 10
    config.timeoutIntervalForResource = 15
    config.waitsForConnectivity = false // Don't wait for connectivity — fail fast
    session = URLSession(configuration: config)
  }

  /// Returns a cached or freshly-downloaded image, or nil if unavailable.
  func image(for urlString: String, size: CGFloat) async -> UIImage? {
    let key = cacheKey(for: urlString)

    // 1. Check disk cache
    let cachedFile = cacheDir.appendingPathComponent(key)
    if let data = try? Data(contentsOf: cachedFile),
       let img = UIImage(data: data) {
      return img
    }

    // 2. Check failure cache
    let failFile = failureDir.appendingPathComponent(key)
    if FileManager.default.fileExists(atPath: failFile.path) {
      if let attrs = try? FileManager.default.attributesOfItem(atPath: failFile.path),
         let modified = attrs[.modificationDate] as? Date,
         Date().timeIntervalSince(modified) < failureTTL {
        return nil // Recently failed, skip network
      }
      try? FileManager.default.removeItem(at: failFile) // Expired, retry
    }

    // 3. Download
    guard let url = URL(string: urlString) else {
      markFailed(key: key)
      return nil
    }

    do {
      let (data, response) = try await session.data(from: url)
      guard let httpResponse = response as? HTTPURLResponse,
            (200...299).contains(httpResponse.statusCode),
            let img = UIImage(data: data) else {
        markFailed(key: key)
        return nil
      }

      // Resize to target size to save disk space
      let targetSize = CGSize(width: size * 2, height: size * 2) // @2x
      let resized = img.resized(to: targetSize)

      if let pngData = resized.pngData() {
        try? pngData.write(to: cachedFile, options: .atomic)
      }

      return resized
    } catch {
      markFailed(key: key)
      return nil
    }
  }

  private func markFailed(key: String) {
    let failFile = failureDir.appendingPathComponent(key)
    FileManager.default.createFile(atPath: failFile.path, contents: nil)
  }

  private func cacheKey(for urlString: String) -> String {
    let digest = SHA256.hash(data: Data(urlString.utf8))
    return digest.prefix(16).map { String(format: "%02x", $0) }.joined()
  }
}

private extension UIImage {
  func resized(to targetSize: CGSize) -> UIImage {
    guard let cgImage = cgImage else { return self }
    guard let ctx = CGContext(
      data: nil,
      width: Int(targetSize.width),
      height: Int(targetSize.height),
      bitsPerComponent: 8,
      bytesPerRow: 0,
      space: CGColorSpaceCreateDeviceRGB(),
      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return self }
    ctx.draw(cgImage, in: CGRect(origin: .zero, size: targetSize))
    guard let scaled = ctx.makeImage() else { return self }
    return UIImage(cgImage: scaled)
  }
}
