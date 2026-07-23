import http from 'k6/http'
import { check } from 'k6'

export function get(config, path, name) {
  const response = http.get(`${config.baseUrl}${path}`, {
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      Accept: 'application/json',
    },
    tags: { name },
    timeout: '15s',
  })

  check(response, {
    [`${name} returns 2xx`]: (res) => res.status >= 200 && res.status < 300,
  })

  return response
}

export function dashboardActionQueue(config) {
  return get(config, '/api/v1/dashboard/action-queue', 'dashboard_action_queue')
}

export function repairOrderList(config) {
  return get(config, '/api/v1/repair-orders?paginated=true&skip=0&limit=25', 'repair_order_list')
}

export function fleetBoard(config) {
  return get(config, '/api/v1/fleet/board', 'fleet_board')
}

export function repairOrderWorkspace(config) {
  if (!config.orderId) {
    return
  }

  get(config, `/api/v1/repair-orders/${config.orderId}/detail`, 'repair_order_detail')
  get(config, `/api/v1/repair-orders/${config.orderId}/price-build`, 'repair_order_price_build')
}
