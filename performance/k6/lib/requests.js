import http from 'k6/http'
import { check } from 'k6'

function failureDetails(response, endpoint) {
  const body = response.body ? String(response.body).replace(/\s+/g, ' ').slice(0, 300) : ''
  return `endpoint=${endpoint} status=${response.status} error=${response.error || 'none'} body=${body}`
}

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

  if (response.status < 200 || response.status >= 300) {
    console.error(`k6_request_failure ${failureDetails(response, name)}`)
  }

  return response
}

export function loginPerformanceUser(config, userNumber) {
  const email = `${config.loadTestUserPrefix}-${String(userNumber).padStart(2, '0')}@${config.loadTestEmailDomain}`
  const response = http.post(
    `${config.baseUrl}/api/v1/auth/login`,
    JSON.stringify({ email, password: config.loadTestPassword, remember_me: false }),
    {
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-DieselBridge-Load-Actor': `k6-vu-${userNumber}`,
      },
      tags: { name: 'performance_login' },
      timeout: '15s',
    },
  )

  const successful = check(response, {
    'performance_login returns 2xx': (res) => res.status >= 200 && res.status < 300,
  })
  if (!successful) {
    console.error(`k6_login_failure vu=${userNumber} ${failureDetails(response, 'performance_login')}`)
    return null
  }

  const accessToken = response.json('access_token')
  if (!accessToken) {
    console.error(`k6_login_failure vu=${userNumber} missing_access_token`)
    return null
  }
  return accessToken
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
