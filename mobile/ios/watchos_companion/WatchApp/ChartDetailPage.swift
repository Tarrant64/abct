import SwiftUI

struct ChartDetailPage: View {
  let historyPoints: [Double]
  let totalValue: Double

  @State private var crownIndex: Double = 6
  @FocusState private var crownFocused: Bool

  private var safeHistory: [Double] {
    historyPoints.isEmpty ? [totalValue] : historyPoints
  }

  private var selectedIndex: Int {
    let maxIndex = max(safeHistory.count - 1, 0)
    return min(max(Int(crownIndex.rounded()), 0), maxIndex)
  }

  private var selectedValue: Double {
    safeHistory[selectedIndex]
  }

  private var maxCrownValue: Double {
    Double(max(safeHistory.count - 1, 0))
  }

  private var dayLabel: String {
    let daysAgo = safeHistory.count - 1 - selectedIndex
    if daysAgo == 0 {
      return "Today"
    } else if daysAgo == 1 {
      return "1 day ago"
    } else {
      return "\(daysAgo) days ago"
    }
  }

  private var trendColor: Color {
    guard safeHistory.count > 1 else { return .green }
    let first = safeHistory.first ?? 0
    let last = safeHistory.last ?? 0
    return last >= first ? .green : .red
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      // Selected value display
      Text(PortfolioFormatters.currency(selectedValue))
        .font(.system(size: 20, weight: .bold, design: .rounded))
        .monospacedDigit()
        .lineLimit(1)
        .minimumScaleFactor(0.7)
        .foregroundStyle(.white)

      Text(dayLabel)
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(.secondary)

      // Full sparkline chart
      ZStack {
        SparklineShape(points: safeHistory)
          .stroke(
            trendColor,
            style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
          )

        chartOverlay
      }
      .frame(height: 100)
      .padding(.top, 4)

      // Range labels
      HStack {
        Text("7d ago")
          .font(.system(size: 9, weight: .regular))
          .foregroundStyle(.secondary)
        Spacer()
        Text("Now")
          .font(.system(size: 9, weight: .regular))
          .foregroundStyle(.secondary)
      }
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 8)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(Color.black)
    .focusable(true)
    .focused($crownFocused)
    .digitalCrownRotation(
      $crownIndex,
      from: 0,
      through: maxCrownValue,
      by: 1,
      sensitivity: .medium,
      isContinuous: false,
      isHapticFeedbackEnabled: true
    )
    .onAppear {
      crownIndex = maxCrownValue
      crownFocused = true
    }
  }

  private var chartOverlay: some View {
    GeometryReader { proxy in
      let values = safeHistory
      let minY = values.min() ?? 0
      let maxY = values.max() ?? 0
      let ySpan = max(maxY - minY, 0.0001)
      let xStep = proxy.size.width / CGFloat(max(values.count - 1, 1))
      let x = CGFloat(selectedIndex) * xStep
      let normalizedY = (selectedValue - minY) / ySpan
      let y = proxy.size.height - CGFloat(normalizedY) * proxy.size.height

      ZStack {
        Rectangle()
          .fill(Color.white.opacity(0.15))
          .frame(width: 1)
          .position(x: x, y: proxy.size.height / 2)

        Circle()
          .fill(trendColor)
          .frame(width: 8, height: 8)
          .position(x: x, y: y)
      }
    }
    .allowsHitTesting(false)
  }
}

#Preview {
  ChartDetailPage(
    historyPoints: PortfolioWatchData.sample.historyPoints,
    totalValue: PortfolioWatchData.sample.totalValue
  )
  .frame(width: 198, height: 242)
}
