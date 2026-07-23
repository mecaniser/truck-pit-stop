import { sleep } from 'k6'
import { loadConfig } from '../lib/config.js'
import {
  dashboardActionQueue,
  fleetBoard,
  repairOrderList,
  repairOrderWorkspace,
} from '../lib/requests.js'

const config = loadConfig({ allowProduction: false })

const flows = [
  dashboardActionQueue,
  dashboardActionQueue,
  repairOrderList,
  repairOrderList,
  fleetBoard,
]

if (config.orderId) {
  flows.push(repairOrderWorkspace)
}

export const options = {
  scenarios: {
    normal_staff_read_mix: {
      executor: 'ramping-arrival-rate',
      startRate: 2,
      timeUnit: '1m',
      preAllocatedVUs: 3,
      maxVUs: 20,
      stages: [
        { target: 5, duration: '2m' },
        { target: 10, duration: '5m' },
        { target: 20, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '1m' }],
    checks: ['rate>0.99'],
    'http_req_duration{name:dashboard_action_queue}': ['p(95)<1200', 'p(99)<2500'],
    'http_req_duration{name:repair_order_list}': ['p(95)<1200', 'p(99)<2500'],
    'http_req_duration{name:fleet_board}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_detail}': ['p(95)<1500', 'p(99)<3000'],
    'http_req_duration{name:repair_order_price_build}': ['p(95)<2000', 'p(99)<4000'],
  },
}

export default function () {
  const flow = flows[(__VU + __ITER) % flows.length]
  flow(config)
  sleep(1)
}
