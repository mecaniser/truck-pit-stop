import { describe, expect, it } from 'vitest'
import {
  buildEventRoute,
  buildModuleRoute,
  inflateRect,
  isOrthogonalRoute,
  pointsToPath,
  routeIntersectsObstacles,
  type OrthogonalRoute,
} from '../routeGeometry'

describe('landing preview route geometry', () => {
  it('builds the module connector through the left rail with exact endpoints', () => {
    const route = buildModuleRoute({
      source: { x: 280, y: 240 },
      target: { x: 210, y: 330 },
      leftRailX: 245,
    })

    expect(route).not.toBeNull()
    expect(route?.points).toEqual([
      { x: 280, y: 240 },
      { x: 245, y: 240 },
      { x: 245, y: 330 },
      { x: 210, y: 330 },
    ])
    expect(route?.path).toBe('M 280 240 L 245 240 L 245 330 L 210 330')
    expect(isOrthogonalRoute(route?.points ?? [])).toBe(true)
  })

  it('builds the selected-evidence connector through the upper and right rails', () => {
    const route = buildEventRoute({
      source: { x: 820, y: 310 },
      target: { x: 1190, y: 220 },
      eventRailY: 280,
      rightRailX: 1160,
    })

    expect(route?.points).toEqual([
      { x: 820, y: 310 },
      { x: 820, y: 280 },
      { x: 1160, y: 280 },
      { x: 1160, y: 220 },
      { x: 1190, y: 220 },
    ])
    expect(route?.points[0]).toEqual({ x: 820, y: 310 })
    expect(route?.points[route.points.length - 1]).toEqual({ x: 1190, y: 220 })
    expect(isOrthogonalRoute(route?.points ?? [])).toBe(true)
  })

  it('inflates route obstacles by the required eight pixels', () => {
    expect(inflateRect({ x: 100, y: 80, width: 40, height: 20 })).toEqual({
      x: 92,
      y: 72,
      width: 56,
      height: 36,
    })
  })

  it('suppresses a route whose segment crosses an inflated obstacle', () => {
    const route = buildModuleRoute({
      source: { x: 280, y: 240 },
      target: { x: 210, y: 330 },
      leftRailX: 245,
      obstacles: [{ x: 250, y: 228, width: 8, height: 8 }],
    })

    expect(route).toBeNull()
  })

  it('reports a direct inflated-obstacle collision but allows endpoint-only anchor contact', () => {
    const route: OrthogonalRoute = {
      points: [
        { x: 40, y: 40 },
        { x: 100, y: 40 },
      ],
      path: pointsToPath([
        { x: 40, y: 40 },
        { x: 100, y: 40 },
      ]),
    }

    expect(routeIntersectsObstacles(route, [{ x: 70, y: 39, width: 2, height: 2 }], 0)).toBe(
      true,
    )
    expect(routeIntersectsObstacles(route, [{ x: 100, y: 40, width: 0, height: 0 }], 0)).toBe(
      false,
    )
  })

  it('rejects absent, zero, or non-finite anchors', () => {
    expect(
      buildModuleRoute({
        source: { x: 0, y: 0 },
        target: { x: 210, y: 330 },
        leftRailX: 245,
      }),
    ).toBeNull()
    expect(
      buildEventRoute({
        source: { x: Number.NaN, y: 310 },
        target: { x: 1190, y: 220 },
        eventRailY: 280,
        rightRailX: 1160,
      }),
    ).toBeNull()
  })

  it('suppresses routes when a reserved rail has less than sixteen pixels clearance', () => {
    expect(
      buildModuleRoute({
        source: { x: 220, y: 240 },
        target: { x: 210, y: 330 },
        leftRailX: 215,
      }),
    ).toBeNull()
    expect(
      buildEventRoute({
        source: { x: 820, y: 310 },
        target: { x: 1190, y: 220 },
        eventRailY: 300,
        rightRailX: 1160,
      }),
    ).toBeNull()
    expect(
      buildEventRoute({
        source: { x: 820, y: 310 },
        target: { x: 1170, y: 220 },
        eventRailY: 280,
        rightRailX: 1160,
      }),
    ).toBeNull()
  })

  it('keeps a valid route when every inflated obstacle remains clear', () => {
    const route = buildEventRoute({
      source: { x: 820, y: 310 },
      target: { x: 1190, y: 220 },
      eventRailY: 280,
      rightRailX: 1160,
      obstacles: [
        { x: 850, y: 320, width: 180, height: 100 },
        { x: 1070, y: 120, width: 40, height: 80 },
      ],
    })

    expect(route).not.toBeNull()
    expect(routeIntersectsObstacles(route!, [
      { x: 850, y: 320, width: 180, height: 100 },
      { x: 1070, y: 120, width: 40, height: 80 },
    ])).toBe(false)
  })
})
