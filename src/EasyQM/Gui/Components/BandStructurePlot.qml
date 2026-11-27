import QtQuick

import EasyApplication.Gui.Style as EaStyle
import EasyApplication.Gui.Elements as EaElements


// Electronic bands along a high-symmetry path: one line per band, the path's named points
// as vertical rules, energies from the reference (the dashed zero line). Spin down is a second
// hue and dashed, so the channels differ by more than colour. A crosshair snaps to the nearest
// k-point; the tooltip names where it is and the band nearest the pointer in each channel.
// bands: {distances, starts, ticks: [{x, label}], levels: [channel][k][band]}, as the backend gives it.
Item {
    id: chart

    property var bands: ({})
    property real energyMin: -10
    property real energyMax: 5
    property string yTitle: ''

    property int hoveredK: -1
    property real hoveredEnergy: 0

    // Validated with the dataviz palette checks: blue, then orange, on both surfaces.
    readonly property var channelColors: EaStyle.Colors.isDarkPalette ? ['#2f9fd4', '#e86934'] : ['#0090cc', '#eb6834']
    readonly property var distances: bands.distances || []
    readonly property var levels: bands.levels || []
    readonly property var ticks: bands.ticks || []
    readonly property real xMax: distances.length ? distances[distances.length - 1] : 1

    readonly property int fontSize: EaStyle.Sizes.fontPixelSize
    readonly property real plotLeft: fontSize * 4.5
    readonly property real plotRight: fontSize * 0.5
    readonly property real plotTop: fontSize
    readonly property real plotBottom: fontSize * 2.5
    readonly property real yStep: niceStep(energyMax - energyMin)

    function niceStep(span) {
        return span > 30 ? 10 : span > 12 ? 5 : span > 6 ? 2 : 1
    }
    function px(x) { return plotLeft + (width - plotLeft - plotRight) * x / (xMax || 1) }
    function py(energy) {
        return plotTop + (height - plotTop - plotBottom) * (energyMax - energy) / (energyMax - energyMin)
    }
    function energyAt(y) {
        return energyMax - (y - plotTop) * (energyMax - energyMin) / (height - plotTop - plotBottom)
    }
    // Where k-point k lies: the named point there, or the two it is between.
    function location(k) {
        const x = distances[k]
        const here = ticks.find(tick => Math.abs(tick.x - x) < 1e-6)
        if (here) {
            return here.label
        }
        const before = ticks.filter(tick => tick.x < x)
        const after = ticks.filter(tick => tick.x > x)
        if (!before.length || !after.length) {
            return ''
        }
        return `${before[before.length - 1].label.split('|').pop()}–${after[0].label.split('|')[0]}`
    }
    // Per channel, the band at k-point k nearest `energy`: {band, energy}.
    function nearestBands(k, energy) {
        return levels.map(channel => {
            let best = 0
            for (let band = 1; band < channel[k].length; band++) {
                if (Math.abs(channel[k][band] - energy) < Math.abs(channel[k][best] - energy)) {
                    best = band
                }
            }
            return { band: best + 1, energy: channel[k][best] }
        })
    }

    onBandsChanged: { hoveredK = -1; canvas.requestPaint() }
    onEnergyMinChanged: canvas.requestPaint()
    onEnergyMaxChanged: canvas.requestPaint()
    onHoveredKChanged: canvas.requestPaint()
    onHoveredEnergyChanged: canvas.requestPaint()
    onChannelColorsChanged: canvas.requestPaint()

    Canvas {
        id: canvas

        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext('2d')
            ctx.reset()
            if (!chart.distances.length) {
                return
            }
            const left = chart.plotLeft
            const right = width - chart.plotRight
            const top = chart.plotTop
            const bottom = height - chart.plotBottom
            ctx.font = `${chart.fontSize * 0.9}px sans-serif`

            // Recessive energy grid with tick labels
            ctx.lineWidth = 1
            ctx.strokeStyle = EaStyle.Colors.chartGridLine
            ctx.fillStyle = EaStyle.Colors.themeForegroundMinor
            ctx.textAlign = 'right'
            ctx.textBaseline = 'middle'
            const step = chart.yStep
            for (let value = Math.ceil(chart.energyMin / step) * step; value <= chart.energyMax + 1e-9; value += step) {
                const y = Math.round(chart.py(value)) + 0.5
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.fillText(value.toFixed(0).replace('-', '−'), left - chart.fontSize * 0.5, y)
            }

            // The path's named points: rules and labels in text ink
            ctx.strokeStyle = EaStyle.Colors.chartAxis
            ctx.fillStyle = EaStyle.Colors.chartLabels
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.font = `${chart.fontSize}px sans-serif`
            for (const tick of chart.ticks) {
                const x = Math.round(chart.px(tick.x)) + 0.5
                ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke()
                ctx.fillText(tick.label, x, bottom + chart.fontSize * 0.4)
            }
            ctx.strokeRect(left + 0.5, top + 0.5, right - left - 1, bottom - top - 1)

            // Axis title
            ctx.save()
            ctx.translate(chart.fontSize * 0.8, (top + bottom) / 2)
            ctx.rotate(-Math.PI / 2)
            ctx.textBaseline = 'middle'
            ctx.fillText(chart.yTitle, 0, 0)
            ctx.restore()

            // Bands, clipped to the plot; spin down dashed
            ctx.save()
            ctx.beginPath(); ctx.rect(left, top, right - left, bottom - top); ctx.clip()
            const starts = chart.bands.starts.concat([chart.distances.length])
            ctx.lineWidth = 1.5
            ctx.lineJoin = 'round'
            for (let channel = 0; channel < chart.levels.length; channel++) {
                const levels = chart.levels[channel]
                ctx.strokeStyle = chart.channelColors[channel]
                ctx.setLineDash(channel === 1 ? [5, 3] : [])
                for (let band = 0; band < levels[0].length; band++) {
                    ctx.beginPath()
                    for (let branch = 0; branch + 1 < starts.length; branch++) {
                        for (let k = starts[branch]; k < starts[branch + 1]; k++) {
                            const x = chart.px(chart.distances[k])
                            const y = chart.py(levels[k][band])
                            if (k === starts[branch]) {
                                ctx.moveTo(x, y)
                            } else {
                                ctx.lineTo(x, y)
                            }
                        }
                    }
                    ctx.stroke()
                }
            }
            ctx.setLineDash([])

            // The reference energy
            if (0 >= chart.energyMin && 0 <= chart.energyMax) {
                ctx.strokeStyle = EaStyle.Colors.themeForegroundMinor
                ctx.lineWidth = 1
                ctx.setLineDash([2, 3])
                const y = Math.round(chart.py(0)) + 0.5
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.setLineDash([])
            }

            // Crosshair and the markers of the nearest bands, with a surface ring
            if (chart.hoveredK >= 0) {
                const x = Math.round(chart.px(chart.distances[chart.hoveredK])) + 0.5
                ctx.strokeStyle = EaStyle.Colors.themeForegroundMinor
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke()
                const nearest = chart.nearestBands(chart.hoveredK, chart.hoveredEnergy)
                for (let channel = 0; channel < nearest.length; channel++) {
                    ctx.beginPath()
                    ctx.arc(x, chart.py(nearest[channel].energy), chart.fontSize * 0.35, 0, 2 * Math.PI)
                    ctx.fillStyle = chart.channelColors[channel]
                    ctx.fill()
                    ctx.lineWidth = 2
                    ctx.strokeStyle = EaStyle.Colors.mainContentBackground
                    ctx.stroke()
                }
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
            if (!inside || !chart.distances.length) {
                chart.hoveredK = -1
                return
            }
            let best = 0
            for (let k = 1; k < chart.distances.length; k++) {
                if (Math.abs(chart.px(chart.distances[k]) - mouse.x) < Math.abs(chart.px(chart.distances[best]) - mouse.x)) {
                    best = k
                }
            }
            chart.hoveredEnergy = chart.energyAt(mouse.y)
            chart.hoveredK = best
        }
        onExited: chart.hoveredK = -1
    }

    // One tooltip for every channel
    Rectangle {
        id: tooltip

        readonly property var nearest: chart.hoveredK >= 0 ? chart.nearestBands(chart.hoveredK, chart.hoveredEnergy) : []
        readonly property real anchorX: chart.hoveredK >= 0 ? chart.px(chart.distances[chart.hoveredK]) : 0

        visible: chart.hoveredK >= 0
        x: anchorX + width + chart.fontSize > chart.width ? anchorX - width - chart.fontSize * 0.75 : anchorX + chart.fontSize * 0.75
        y: chart.plotTop
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
                text: chart.hoveredK >= 0 ?
                          `${chart.location(chart.hoveredK) || '–'} · k = ${chart.distances[chart.hoveredK].toFixed(3)} Å⁻¹` : ''
            }
            Repeater {
                model: tooltip.nearest

                Row {
                    spacing: chart.fontSize * 0.4

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: chart.fontSize * 0.8
                        height: 2
                        color: chart.channelColors[index]
                    }
                    EaElements.Label {
                        color: EaStyle.Colors.themeForegroundMinor
                        font.pixelSize: chart.fontSize * 0.9
                        text: (chart.levels.length === 2 ? (index === 0 ? qsTr('Spin up · ') : qsTr('Spin down · ')) : '') +
                              qsTr('band %1 · %2 eV').arg(modelData.band).arg(modelData.energy.toFixed(3).replace('-', '−'))
                    }
                }
            }
        }
    }
}
