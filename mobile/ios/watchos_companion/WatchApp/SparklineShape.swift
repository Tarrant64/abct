import SwiftUI

struct SparklineShape: Shape {
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

/// Closed shape that fills the area under the sparkline curve.
struct SparklineFillShape: Shape {
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
    path.move(to: CGPoint(x: rect.minX, y: rect.maxY))
    path.addLine(to: CGPoint(x: rect.minX, y: yPosition(for: points[0])))

    for index in 1..<points.count {
      let x = rect.minX + CGFloat(index) * stepX
      let y = yPosition(for: points[index])
      path.addLine(to: CGPoint(x: x, y: y))
    }

    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    path.closeSubpath()

    return path
  }
}
