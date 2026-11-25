import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Density of states on a vertical energy axis, so that it lines up with a band structure
// drawn beside it over the same energies. A single series: a 2 px line over a faint fill of
// the same hue. A horizontal crosshair snaps to the nearest energy; the tooltip gives it with
// the DOS there.
// curve: {energies, values, max}, energies in eV from the reference, values in states/eV/cell.
Item {
    id: chart

    property var curve: ({})
    property real energyMin: -10
    property real energyMax: 5
    property bool showEnergyAxis: true  // off beside a band structure, which carries it
    property string yTitle: ''

    property int hoveredIndex: -1

    readonly property color markColor: EaStyle.Colors.isDarkPalette ? '#2f9fd4' : '#0090cc'
    readonly property var energies: curve.energies || []
    readonly property var values: curve.values || []
    readonly property real valueMax: niceMax(curve.max || 1)

    readonly property int fontSize: EaStyle.Sizes.fontPixelSize
    readonly property real plotLeft: showEnergyAxis ? fontSize * 4.5 : fontSize * 0.5
    readonly property real plotRight: fontSize * 0.75
    readonly property real plotTop: fontSize
    readonly property real plotBottom: fontSize * 2.5

    // The visible maximum of the curve, rounded up to 1, 2 or 5 times a power of ten.
    function niceMax(value) {
        const window = values.filter((v, i) => energies[i] >= energyMin && energies[i] <= energyMax)
        const top = Math.max(...window, value > 0 ? 0 : 1, 1e-6)
        const power = Math.pow(10, Math.floor(Math.log10(top)))
        return [1, 2, 5, 10].map(f => f * power).find(m => m >= top)
    }
    function px(value) { return plotLeft + (width - plotLeft - plotRight) * value / valueMax }
    function py(energy) {
        return plotTop + (height - plotTop - plotBottom) * (energyMax - energy) / (energyMax - energyMin)
    }

    onCurveChanged: { hoveredIndex = -1; canvas.requestPaint() }
    onEnergyMinChanged: canvas.requestPaint()
    onEnergyMaxChanged: canvas.requestPaint()
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
            if (!chart.energies.length) {
                return
            }
            const left = chart.plotLeft
            const right = width - chart.plotRight
            const top = chart.plotTop
            const bottom = height - chart.plotBottom
            ctx.font = `${chart.fontSize * 0.9}px sans-serif`
            ctx.lineWidth = 1

            // Recessive grid: energies as on the band structure, DOS at 0, half and full scale
            ctx.strokeStyle = EaStyle.Colors.chartGridLine
            ctx.fillStyle = EaStyle.Colors.themeForegroundMinor
            const span = chart.energyMax - chart.energyMin
            const step = span > 30 ? 10 : span > 12 ? 5 : span > 6 ? 2 : 1
            ctx.textAlign = 'right'
            ctx.textBaseline = 'middle'
            for (let value = Math.ceil(chart.energyMin / step) * step; value <= chart.energyMax + 1e-9; value += step) {
                const y = Math.round(chart.py(value)) + 0.5
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                if (chart.showEnergyAxis) {
                    ctx.fillText(value.toFixed(0).replace('-', '−'), left - chart.fontSize * 0.5, y)
                }
            }
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            for (const fraction of [0.5, 1]) {
                const x = Math.round(chart.px(fraction * chart.valueMax)) + 0.5
                ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke()
                ctx.fillText(+(fraction * chart.valueMax).toPrecision(2), Math.min(x, right - chart.fontSize), bottom + chart.fontSize * 0.4)
            }
            ctx.fillText('0', left, bottom + chart.fontSize * 0.4)
            ctx.strokeStyle = EaStyle.Colors.chartAxis
            ctx.strokeRect(left + 0.5, top + 0.5, right - left - 1, bottom - top - 1)

            // Axis titles
            ctx.fillStyle = EaStyle.Colors.chartLabels
            ctx.font = `${chart.fontSize}px sans-serif`
            ctx.fillText(qsTr('DOS (states/eV)'), (left + right) / 2, bottom + chart.fontSize * 1.4)
            if (chart.showEnergyAxis) {
                ctx.save()
                ctx.translate(chart.fontSize * 0.8, (top + bottom) / 2)
                ctx.rotate(-Math.PI / 2)
                ctx.textBaseline = 'middle'
                ctx.fillText(chart.yTitle, 0, 0)
                ctx.restore()
            }

            // The curve over a faint fill, clipped to the plot
            ctx.save()
            ctx.beginPath(); ctx.rect(left, top, right - left, bottom - top); ctx.clip()
            ctx.beginPath()
            ctx.moveTo(left, chart.py(chart.energies[0]))
            for (let i = 0; i < chart.energies.length; i++) {
                ctx.lineTo(chart.px(chart.values[i]), chart.py(chart.energies[i]))
            }
            ctx.lineTo(left, chart.py(chart.energies[chart.energies.length - 1]))
            ctx.closePath()
            ctx.globalAlpha = 0.15
            ctx.fillStyle = chart.markColor
            ctx.fill()
            ctx.globalAlpha = 1
            ctx.beginPath()
            for (let i = 0; i < chart.energies.length; i++) {
                const x = chart.px(chart.values[i])
                const y = chart.py(chart.energies[i])
                if (i === 0) {
                    ctx.moveTo(x, y)
                } else {
                    ctx.lineTo(x, y)
                }
            }
            ctx.strokeStyle = chart.markColor
            ctx.lineWidth = 2
            ctx.lineJoin = 'round'
            ctx.stroke()

            // The reference energy
            if (0 >= chart.energyMin && 0 <= chart.energyMax) {
                ctx.strokeStyle = EaStyle.Colors.themeForegroundMinor
                ctx.lineWidth = 1
                ctx.setLineDash([2, 3])
                const y = Math.round(chart.py(0)) + 0.5
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.setLineDash([])
            }

            // Crosshair and marker, with a surface ring
            if (chart.hoveredIndex >= 0) {
                const y = Math.round(chart.py(chart.energies[chart.hoveredIndex])) + 0.5
                ctx.strokeStyle = EaStyle.Colors.themeForegroundMinor
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.beginPath()
                ctx.arc(chart.px(chart.values[chart.hoveredIndex]), y, chart.fontSize * 0.35, 0, 2 * Math.PI)
                ctx.fillStyle = chart.markColor
                ctx.fill()
                ctx.lineWidth = 2
                ctx.strokeStyle = EaStyle.Colors.mainContentBackground
                ctx.stroke()
            }
            ctx.restore()
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true

        onPositionChanged: (mouse) => {
            const inside = mouse.x >= chart.plotLeft && mouse.x <= chart.width - chart.plotRight &&
                           mouse.y >= chart.plotTop && mouse.y <= chart.height - chart.plotBottom
            if (!inside || !chart.energies.length) {
                chart.hoveredIndex = -1
                return
            }
            // Evenly spaced energies: the nearest one is found by its position.
            const first = chart.energies[0]
            const step = (chart.energies[chart.energies.length - 1] - first) / (chart.energies.length - 1)
            const energy = chart.energyMax - (mouse.y - chart.plotTop) * (chart.energyMax - chart.energyMin) /
                           (chart.height - chart.plotTop - chart.plotBottom)
            chart.hoveredIndex = Math.min(Math.max(Math.round((energy - first) / step), 0), chart.energies.length - 1)
        }
        onExited: chart.hoveredIndex = -1
    }

    Rectangle {
        readonly property real anchorY: chart.hoveredIndex >= 0 ? chart.py(chart.energies[chart.hoveredIndex]) : 0

        visible: chart.hoveredIndex >= 0
        x: chart.width - width - chart.plotRight - chart.fontSize * 0.25
        y: Math.min(Math.max(anchorY - height - chart.fontSize * 0.5, chart.plotTop), chart.height - chart.plotBottom - height)
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
                text: chart.hoveredIndex >= 0 ?
                          `${chart.energies[chart.hoveredIndex].toFixed(2).replace('-', '−')} eV` : ''
            }
            EaElements.Label {
                color: EaStyle.Colors.themeForegroundMinor
                font.pixelSize: chart.fontSize * 0.9
                text: chart.hoveredIndex >= 0 ? qsTr('%1 states/eV').arg(chart.values[chart.hoveredIndex].toFixed(2)) : ''
            }
        }
    }
}
