import { sleep } from 'k6'
import { loadConfig, requireAccessToken } from '../lib/config.js'
import {
  dashboardActionQueue,
  fleetBoard,
  repairOrderList,
  repairOrderWorkspace,
} from '../lib/requests.js'

const config = loadConfig({ allowProduction: true })
requireAccessToken(config)

export const options = {
  scenarios: {
    production_safe_canary: {
      executor: 'constant-arrival-rate',
      rate: config.canaryRate,
      timeUnit: '1m',
      duration: __ENV.CANARY_DURATION || '5m',
      preAllocatedVUs: 1,
      maxVUs: 2,
      gracefulStop: '15s',
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '30s' }],
    checks: ['rate>0.99'],
    'http_req_duration{name:dashboard_action_queue}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_list}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:fleet_board}': ['p(95)<2000', 'p(99)<4000'],
    'http_req_duration{name:repair_order_detail}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_price_build}': ['p(95)<2000', 'p(99)<4000'],
  },
}

export default function () {
  dashboardActionQueue(config)
  repairOrderList(config)
  fleetBoard(config)
  repairOrderWorkspace(config)
  sleep(1)
}
