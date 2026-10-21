// Independent checks share the VM's two CPUs; both must finish successfully.
import { spawn } from 'node:child_process'
const run = (command, args = []) => new Promise(resolve => {
  const child = spawn(process.execPath, [command, ...args], { stdio: 'inherit' })
  child.on('error', error => { console.error(error); resolve(1) })
  child.on('exit', code => resolve(code === 0 ? 0 : 1))
})
const results = await Promise.all([
  run('node_modules/typescript/bin/tsc'),
  run('node_modules/vite/bin/vite.js', ['build']),
])
process.exitCode = results.some(code => code !== 0) ? 1 : 0
