import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Single-series stick spectrum (IR, Raman): one vertical line per transition, heights in
// percent of the strongest. Hovering a stick shows its tooltip, clicking selects it.
// points: [{key, x, y, title, detail}], x in axis units, y >= 0 in any unit.
Item {
    id: chart

    property var points: []
    property string xTitle: ''
    property string yTitle: ''
    property var selectedKey: null
    signal picked(var key)

    property int hoveredIndex: -1

    // One hue, validated against both surfaces (3:1 contrast, lightness band).
    readonly property color markColor: EaStyle.Colors.isDarkPalette ? '#2f9fd4' : '#0090cc'
    readonly property int fontSize: EaStyle.Sizes.fontPixelSize
    readonly property real plotLeft: fontSize * 4.5
    readonly property real plotRight: fontSize
    readonly property real plotTop: fontSize
    readonly property real plotBottom: fontSize * 3.5

    readonly property real yMax: Math.max(...points.map(point => point.y), 0)
    readonly property real xStep: {
        const span = xMaxRaw - xMinRaw
        return span > 2000 ? 500 : span > 800 ? 200 : 100
    }
    readonly property real xMinRaw: points.length ? Math.min(...points.map(point => point.x)) : 0
    readonly property real xMaxRaw: points.length ? Math.max(...points.map(point => point.x)) : 4000
    readonly property real xMin: Math.floor(xMinRaw / xStep) * xStep
    readonly property real xMax: Math.max(Math.ceil(xMaxRaw / xStep) * xStep, xMin + xStep)

    function px(x) { return plotLeft + (width - plotLeft - plotRight) * (x - xMin) / (xMax - xMin) }
    function py(percent) { return height - plotBottom - (height - plotTop - plotBottom) * percent / 100 }
    function percent(point) { return yMax > 0 ? 100 * point.y / yMax : 0 }

    onPointsChanged: { hoveredIndex = -1; canvas.requestPaint() }
    onSelectedKeyChanged: canvas.requestPaint()
    onHoveredIndexChanged: canvas.requestPaint()
    onMarkColorChanged: canvas.requestPaint()

    Canvas {
        id: canvas

        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext('2d')
            ctx.reset()
            const left = chart.plotLeft
            const right = width - chart.plotRight
            const top = chart.plotTop
            const bottom = height - chart.plotBottom
            ctx.font = `${chart.fontSize * 0.9}px sans-serif`

            // Recessive grid with tick labels
            ctx.lineWidth = 1
            ctx.strokeStyle = EaStyle.Colors.chartGridLine
            ctx.fillStyle = EaStyle.Colors.themeForegroundMinor
            ctx.textBaseline = 'middle'
            ctx.textAlign = 'right'
            for (let value = 0; value <= 100; value += 25) {
                const y = Math.round(chart.py(value)) + 0.5
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.fillText(value, left - chart.fontSize * 0.5, y)
            }
            ctx.textBaseline = 'top'
            ctx.textAlign = 'center'
            for (let value = chart.xMin; value <= chart.xMax + 1e-9; value += chart.xStep) {
                const x = Math.round(chart.px(value)) + 0.5
                ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke()
                ctx.fillText(value, x, bottom + chart.fontSize * 0.5)
            }
            ctx.strokeStyle = EaStyle.Colors.chartAxis
            ctx.beginPath(); ctx.moveTo(left, bottom + 0.5); ctx.lineTo(right, bottom + 0.5); ctx.stroke()

            // Axis titles
            ctx.fillStyle = EaStyle.Colors.chartLabels
            ctx.font = `${chart.fontSize}px sans-serif`
            ctx.fillText(chart.xTitle, (left + right) / 2, bottom + chart.fontSize * 2)
            ctx.save()
            ctx.translate(chart.fontSize * 0.8, (top + bottom) / 2)
            ctx.rotate(-Math.PI / 2)
            ctx.fillText(chart.yTitle, 0, 0)
            ctx.restore()

            // Sticks, anchored to the baseline; the hovered and the selected one are wider.
            ctx.strokeStyle = chart.markColor
            for (let i = 0; i < chart.points.length; i++) {
                const point = chart.points[i]
                const x = chart.px(point.x)
                const emphasised = i === chart.hoveredIndex || point.key === chart.selectedKey
                ctx.lineWidth = emphasised ? 3.5 : 2
                ctx.beginPath(); ctx.moveTo(x, bottom); ctx.lineTo(x, chart.py(chart.percent(point))); ctx.stroke()
            }

            // Marker on the selected stick, with a surface ring
            const selected = chart.points.findIndex(point => point.key === chart.selectedKey)
            if (selected >= 0) {
                const point = chart.points[selected]
                ctx.beginPath()
                ctx.arc(chart.px(point.x), chart.py(chart.percent(point)), chart.fontSize * 0.4, 0, 2 * Math.PI)
                ctx.fillStyle = chart.markColor
                ctx.fill()
                ctx.lineWidth = 2
                ctx.strokeStyle = EaStyle.Colors.mainContentBackground
                ctx.stroke()
            }
        }
    }

    // Hit targets are wider than the 2 px sticks; only visible sticks can be hovered.
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: chart.hoveredIndex >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor

        onPositionChanged: (mouse) => {
            let best = -1
            let bestDistance = chart.fontSize * 0.6
            for (let i = 0; i < chart.points.length; i++) {
                if (chart.percent(chart.points[i]) < 0.5) {
                    continue
                }
                const distance = Math.abs(chart.px(chart.points[i].x) - mouse.x)
                if (distance <= bestDistance) {
                    best = i
                    bestDistance = distance
                }
            }
            chart.hoveredIndex = best
        }
        onExited: chart.hoveredIndex = -1
        onClicked: {
            if (chart.hoveredIndex >= 0) {
                chart.picked(chart.points[chart.hoveredIndex].key)
            }
        }
    }

    // Tooltip of the hovered stick
    Rectangle {
        id: tooltip

        readonly property var point: chart.hoveredIndex >= 0 ? chart.points[chart.hoveredIndex] : null
        readonly property real anchorX: point ? chart.px(point.x) : 0
        readonly property real anchorY: point ? chart.py(chart.percent(point)) : 0

        visible: point !== null
        x: Math.min(Math.max(anchorX + chart.fontSize * 0.75, 0), chart.width - width)
        y: Math.min(Math.max(anchorY, chart.plotTop), chart.height - chart.plotBottom - height)
        width: tooltipColumn.width + chart.fontSize
        height: tooltipColumn.height + chart.fontSize * 0.8
        radius: 2
        color: EaStyle.Colors.mainContentBackground
        border.width: 1
        border.color: EaStyle.Colors.appBorder

        Column {
            id: tooltipColumn
            anchors.centerIn: parent

            EaElements.Label {
                text: tooltip.point ? tooltip.point.title : ''
            }
            EaElements.Label {
                color: EaStyle.Colors.themeForegroundMinor
                font.pixelSize: chart.fontSize * 0.9
                text: tooltip.point ? tooltip.point.detail : ''
            }
        }
    }
}
