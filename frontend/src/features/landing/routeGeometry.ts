export interface Point {
  x: number
  y: number
}

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export interface OrthogonalRoute {
  points: readonly Point[]
  path: string
}

export interface BuildModuleRouteOptions {
  source: Point
  target: Point
  leftRailX: number
  obstacles?: readonly Rect[]
  obstaclePadding?: number
}

export interface BuildEventRouteOptions {
  source: Point
  target: Point
  eventRailY: number
  rightRailX: number
  obstacles?: readonly Rect[]
  obstaclePadding?: number
}

const ROUTE_PADDING = 8
const MIN_RAIL_CLEARANCE = 16
const EPSILON = 0.001

const isFiniteNumber = (value: number) => Number.isFinite(value)

const isValidAnchor = (point: Point) =>
  isFiniteNumber(point.x) &&
  isFiniteNumber(point.y) &&
  point.x > 0 &&
  point.y > 0

const isValidRect = (rect: Rect) =>
  isFiniteNumber(rect.x) &&
  isFiniteNumber(rect.y) &&
  isFiniteNumber(rect.width) &&
  isFiniteNumber(rect.height) &&
  rect.width >= 0 &&
  rect.height >= 0

const samePoint = (a: Point, b: Point) =>
  Math.abs(a.x - b.x) <= EPSILON && Math.abs(a.y - b.y) <= EPSILON

const normalizeNumber = (value: number) => (Object.is(value, -0) ? 0 : value)

export const inflateRect = (rect: Rect, padding = ROUTE_PADDING): Rect => ({
  x: rect.x - padding,
  y: rect.y - padding,
  width: rect.width + padding * 2,
  height: rect.height + padding * 2,
})

export const pointsToPath = (points: readonly Point[]): string =>
  points
    .map((point, index) => {
      const command = index === 0 ? 'M' : 'L'
      return `${command} ${normalizeNumber(point.x)} ${normalizeNumber(point.y)}`
    })
    .join(' ')

export const isOrthogonalRoute = (points: readonly Point[]): boolean =>
  points.length >= 2 &&
  points.every((point, index) => {
    if (!isFiniteNumber(point.x) || !isFiniteNumber(point.y)) return false
    if (index === 0) return true
    const previous = points[index - 1]
    const horizontal = Math.abs(previous.y - point.y) <= EPSILON
    const vertical = Math.abs(previous.x - point.x) <= EPSILON
    return (horizontal || vertical) && !samePoint(previous, point)
  })

interface SegmentIntersection {
  start: Point
  end: Point
}

const segmentRectIntersection = (
  start: Point,
  end: Point,
  rect: Rect,
): SegmentIntersection | null => {
  const right = rect.x + rect.width
  const bottom = rect.y + rect.height

  if (Math.abs(start.y - end.y) <= EPSILON) {
    if (start.y < rect.y - EPSILON || start.y > bottom + EPSILON) return null
    const overlapStart = Math.max(Math.min(start.x, end.x), rect.x)
    const overlapEnd = Math.min(Math.max(start.x, end.x), right)
    if (overlapStart > overlapEnd + EPSILON) return null
    return {
      start: { x: overlapStart, y: start.y },
      end: { x: overlapEnd, y: start.y },
    }
  }

  if (Math.abs(start.x - end.x) <= EPSILON) {
    if (start.x < rect.x - EPSILON || start.x > right + EPSILON) return null
    const overlapStart = Math.max(Math.min(start.y, end.y), rect.y)
    const overlapEnd = Math.min(Math.max(start.y, end.y), bottom)
    if (overlapStart > overlapEnd + EPSILON) return null
    return {
      start: { x: start.x, y: overlapStart },
      end: { x: start.x, y: overlapEnd },
    }
  }

  return null
}

const isDeclaredAnchorTouch = (
  intersection: SegmentIntersection,
  routeStart: Point,
  routeEnd: Point,
) => {
  if (!samePoint(intersection.start, intersection.end)) return false
  return samePoint(intersection.start, routeStart) || samePoint(intersection.start, routeEnd)
}

/**
 * Checks the already-routed orthogonal segments against inflated obstacles.
 * A zero-area touch at the declared source or target anchor is allowed; every
 * other contact suppresses the route.
 */
export const routeIntersectsObstacles = (
  route: OrthogonalRoute,
  obstacles: readonly Rect[],
  padding = ROUTE_PADDING,
): boolean => {
  if (!isOrthogonalRoute(route.points)) return true

  const routeStart = route.points[0]
  const routeEnd = route.points[route.points.length - 1]

  return obstacles.some((obstacle) => {
    if (!isValidRect(obstacle)) return true
    const inflated = inflateRect(obstacle, padding)

    return route.points.slice(1).some((segmentEnd, index) => {
      const segmentStart = route.points[index]
      const intersection = segmentRectIntersection(segmentStart, segmentEnd, inflated)
      return (
        intersection !== null &&
        !isDeclaredAnchorTouch(intersection, routeStart, routeEnd)
      )
    })
  })
}

const createRoute = (
  points: readonly Point[],
  obstacles: readonly Rect[],
  obstaclePadding: number,
): OrthogonalRoute | null => {
  if (!isOrthogonalRoute(points)) return null
  const route: OrthogonalRoute = { points, path: pointsToPath(points) }
  return routeIntersectsObstacles(route, obstacles, obstaclePadding) ? null : route
}

/**
 * Connects the selected module's left-edge anchor to the entity sheet's
 * right-edge anchor. The middle vertical segment stays inside the reserved
 * left rail.
 */
export const buildModuleRoute = ({
  source,
  target,
  leftRailX,
  obstacles = [],
  obstaclePadding = ROUTE_PADDING,
}: BuildModuleRouteOptions): OrthogonalRoute | null => {
  if (!isValidAnchor(source) || !isValidAnchor(target) || !isFiniteNumber(leftRailX)) {
    return null
  }

  if (target.x >= source.x) return null
  if (leftRailX <= target.x || leftRailX >= source.x) return null
  if (source.x - target.x < MIN_RAIL_CLEARANCE) return null

  return createRoute(
    [
      source,
      { x: leftRailX, y: source.y },
      { x: leftRailX, y: target.y },
      target,
    ],
    obstacles,
    obstaclePadding,
  )
}

/**
 * Connects the selected stage's top-edge anchor to the event sheet's
 * left-edge anchor. It rises into the clear event rail, crosses to the right
 * rail, descends there, and only then enters the sheet.
 */
export const buildEventRoute = ({
  source,
  target,
  eventRailY,
  rightRailX,
  obstacles = [],
  obstaclePadding = ROUTE_PADDING,
}: BuildEventRouteOptions): OrthogonalRoute | null => {
  if (
    !isValidAnchor(source) ||
    !isValidAnchor(target) ||
    !isFiniteNumber(eventRailY) ||
    !isFiniteNumber(rightRailX)
  ) {
    return null
  }

  if (eventRailY >= source.y || source.y - eventRailY < MIN_RAIL_CLEARANCE) return null
  if (rightRailX <= source.x || rightRailX >= target.x) return null
  if (target.x - rightRailX < MIN_RAIL_CLEARANCE) return null

  return createRoute(
    [
      source,
      { x: source.x, y: eventRailY },
      { x: rightRailX, y: eventRailY },
      { x: rightRailX, y: target.y },
      target,
    ],
    obstacles,
    obstaclePadding,
  )
}
