const round = (value, digits = 2) => Number(value.toFixed(digits))

const runConfigs = [
  { id: 'run-0412', name: 'Track validation · Run 12', date: 'May 19, 2026 · 3:06 PM', duration: 84.75, peak: 12.7, distance: 842, phase: 0 },
  { id: 'run-0411', name: 'Track validation · Run 11', date: 'May 19, 2026 · 2:48 PM', duration: 79.32, peak: 11.9, distance: 798, phase: 1.1 },
  { id: 'run-0410', name: 'Shakedown · Run 10', date: 'May 19, 2026 · 2:21 PM', duration: 92.08, peak: 10.8, distance: 865, phase: 2.4 },
  { id: 'run-0409', name: 'Track validation · Run 09', date: 'May 18, 2026 · 4:12 PM', duration: 76.54, peak: 12.1, distance: 821, phase: 3.3 },
]

function makeRun(config) {
  const count = Math.floor(config.duration) + 1
  const speed = Array.from({ length: count }, (_, time) => {
    const lapWave = 0.5 + 0.5 * Math.sin(time / 10 + config.phase)
    const curve = 0.78 + Math.sin(time / 5.5 + config.phase) * 0.18
    const braking = [22, 43, 66].some((point) => Math.abs(point - time) < 2.5) ? 0.56 : 1
    return { time, value: round(Math.max(0, config.peak * lapWave * curve * braking)) }
  })
  const throttle = speed.map(({ time, value }) => ({ time, value: round(Math.max(4, Math.min(100, value / config.peak * 86 + 8 * Math.sin(time / 3.7))), 0) }))
  const steering = speed.map(({ time }) => ({ time, value: round(Math.max(-100, Math.min(100, 63 * Math.sin(time / 7 + config.phase) + 22 * Math.sin(time / 2.8))), 0) }))
  const acceleration = speed.map(({ time, value }, index) => ({ time, value: round((value - (speed[index - 1]?.value ?? value)) * 2.4 + 0.18 * Math.sin(time / 3)) }))
  const commanded = speed.map(({ time, value }) => ({ time, actual: value, target: round(Math.min(config.peak, value + 0.45 * Math.sin(time / 5.1))) }))
  const gps = Array.from({ length: 90 }, (_, i) => {
    const t = i / 89
    const angle = t * Math.PI * 2
    return { x: round(50 + 34 * Math.cos(angle) + 5 * Math.sin(angle * 3)), y: round(50 + 27 * Math.sin(angle) + 7 * Math.sin(angle * 2)) }
  })
  const peak = Math.max(...speed.map((point) => point.value))
  const mean = speed.reduce((sum, point) => sum + point.value, 0) / speed.length
  return {
    ...config,
    currentSpeed: speed.at(-1).value,
    maxSpeed: round(peak),
    averageSpeed: round(mean),
    distance: config.distance,
    status: 'Complete',
    telemetry: { speed, throttle, steering, acceleration, commanded, gps },
    controller: { mode: 'AUTO · MPC', health: 'Nominal', frequency: 48, trackingError: 0.18, messages: 4621 },
  }
}

export const mockRuns = runConfigs.map(makeRun)
export const mockTelemetry = Object.fromEntries(mockRuns.map((run) => [run.id, run]))
