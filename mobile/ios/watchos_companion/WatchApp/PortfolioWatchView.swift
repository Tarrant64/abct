import SwiftUI

struct PortfolioOverviewPage: View {
  let data: PortfolioWatchData
  let onRefresh: () -> Void
  let onHandoff: () -> Void

  private var sparklineColor: Color {
    data.percentChange >= 0 ? .green : .red
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("Total Portfolio")
        .font(.system(size: 12, weight: .medium))
        .foregroundStyle(.secondary)

      Text(PortfolioFormatters.currency(data.totalValue))
        .font(.system(size: 27, weight: .bold, design: .rounded))
        .monospacedDigit()
        .lineLimit(1)
        .minimumScaleFactor(0.75)

      HStack(spacing: 6) {
        changePill

        Text(PortfolioFormatters.signedCurrency(data.sevenDayChange))
          .font(.system(size: 11, weight: .medium, design: .rounded))
          .foregroundStyle(.secondary)
          .monospacedDigit()
          .lineLimit(1)
      }

      // Mini sparkline with vibrant gradient
      let sparklinePoints = data.historyPoints.isEmpty ? [data.totalValue] : data.historyPoints
      let isPositive = data.percentChange >= 0
      ZStack(alignment: .bottom) {
        SparklineFillShape(points: sparklinePoints)
          .fill(
            LinearGradient(
              colors: isPositive
                ? [Color.cyan.opacity(0.35), Color.green.opacity(0.12), Color.clear]
                : [Color.orange.opacity(0.35), Color.red.opacity(0.12), Color.clear],
              startPoint: .top,
              endPoint: .bottom
            )
          )

        SparklineShape(points: sparklinePoints)
          .stroke(
            LinearGradient(
              colors: isPositive
                ? [.cyan, .mint, .green]
                : [.yellow, .orange, .red],
              startPoint: .leading,
              endPoint: .trailing
            ),
            style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round)
          )
      }
      .frame(height: 48)
      .padding(10)
      .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))

      HStack(spacing: 10) {
        actionButton(systemImage: "arrow.clockwise", action: onRefresh)
        actionButton(systemImage: "iphone.gen3.radiowaves.left.and.right", action: onHandoff)
      }
      .padding(.top, 2)
    }
    .padding(.horizontal, 10)
    .padding(.vertical, 8)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(Color.black)
  }

  private var changePill: some View {
    Text(PortfolioFormatters.signedPercent(data.percentChange))
      .font(.system(size: 11, weight: .bold, design: .rounded))
      .monospacedDigit()
      .foregroundStyle(data.percentChange >= 0 ? .green : .red)
      .padding(.horizontal, 8)
      .padding(.vertical, 4)
      .background(
        (data.percentChange >= 0 ? Color.green : Color.red).opacity(0.2),
        in: Capsule(style: .continuous)
      )
  }

  private func actionButton(systemImage: String, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Image(systemName: systemImage)
        .font(.system(size: 13, weight: .semibold))
        .frame(width: 28, height: 28)
        .background(Color.white.opacity(0.10), in: Circle())
    }
    .buttonStyle(.plain)
    .foregroundStyle(.white)
  }
}

#Preview("41mm") {
  PortfolioOverviewPage(data: .sample, onRefresh: {}, onHandoff: {})
    .frame(width: 176, height: 215)
}

#Preview("45mm") {
  PortfolioOverviewPage(data: .sample, onRefresh: {}, onHandoff: {})
    .frame(width: 198, height: 242)
}
