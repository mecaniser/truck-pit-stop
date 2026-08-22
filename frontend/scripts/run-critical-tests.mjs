import { execFileSync } from 'node:child_process'
import process from 'node:process'

execFileSync(process.execPath, ['scripts/check-runtime-identity.mjs'], { stdio: 'inherit' })

const criticalTests = [
  'src/__tests__/LandingPage.test.tsx',
  'src/__tests__/RouteGuards.test.tsx',
  'src/__tests__/TenantBrandLogo.test.tsx',
  'src/__tests__/authStore.test.ts',
  'src/__tests__/authTokens.test.ts',
  'src/__tests__/password.test.ts',
  'src/__tests__/passwordPolicy.test.ts',
  'src/__tests__/phone.test.ts',
  'src/components/__tests__/CustomerSelect.typeahead.test.tsx',
  'src/features/auth/__tests__/LoginPage.test.tsx',
  'src/features/mechanics/__tests__/MechanicsPage.test.tsx',
  'src/features/repair-orders/__tests__/RepairOrdersPage.abort.test.tsx',
  'src/lib/__tests__/apiCancellation.test.ts',
]

execFileSync('npx', ['vitest', 'run', ...criticalTests], { stdio: 'inherit' })
