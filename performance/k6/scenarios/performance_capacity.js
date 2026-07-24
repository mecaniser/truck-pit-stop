import { fail, sleep } from 'k6'
import exec from 'k6/execution'
import { loadConfig, requireLoadTestPassword } from '../lib/config.js'
import {
  dashboardActionQueue,
  fleetBoard,
  loginPerformanceUser,
  repairOrderList,
  repairOrderWorkspace,
} from '../lib/requests.js'

const config = loadConfig({ allowProduction: false })

if (config.target !== 'performance') {
  fail('performance_capacity.js requires TARGET_ENV=performance')
}
if (!config.orderId) {
  fail('performance_capacity.js requires REPAIR_ORDER_ID')
}
requireLoadTestPassword(config)

const flows = [
  dashboardActionQueue,
  dashboardActionQueue,
  repairOrderList,
  repairOrderList,
  fleetBoard,
  repairOrderWorkspace,
]

export const options = {
  scenarios: {
    scaled_staff_read_mix: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { target: 2, duration: '3m' },
        { target: 5, duration: '5m' },
        { target: 10, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '1m' }],
    checks: ['rate>0.99'],
    'http_req_duration{name:performance_login}': ['p(95)<1000', 'p(99)<2000'],
    'http_req_duration{name:dashboard_action_queue}': ['p(95)<1200', 'p(99)<2500'],
    'http_req_duration{name:repair_order_list}': ['p(95)<1200', 'p(99)<2500'],
    'http_req_duration{name:fleet_board}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_detail}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_price_build}': ['p(95)<2000', 'p(99)<4000'],
  },
}

let accessToken = null

export default function () {
  if (!accessToken) {
    accessToken = loginPerformanceUser(config, __VU)
    if (!accessToken) {
      exec.test.abort(`Unable to authenticate performance load user for VU ${__VU}`)
    }
  }

  const staffConfig = { ...config, accessToken }
  const flow = flows[(__VU + __ITER) % flows.length]
  flow(staffConfig)
  sleep(1)
}
