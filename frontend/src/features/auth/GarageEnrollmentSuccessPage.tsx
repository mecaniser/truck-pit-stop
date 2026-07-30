import { Link } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'

export default function GarageEnrollmentSuccessPage() {
  return <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4 text-white"><section className="w-full max-w-lg rounded-2xl border border-emerald-400/25 bg-zinc-900 p-8 text-center shadow-2xl"><CheckCircle2 className="mx-auto h-12 w-12 text-emerald-400" /><h1 className="mt-4 text-2xl font-semibold">Application received</h1><p className="mt-3 text-sm leading-6 text-zinc-300">Thanks for applying to join DieselBridge. Our team will review your shop information and contact you with next steps.</p><Link to="/" className="mt-6 inline-flex rounded-lg bg-emerald-400 px-4 py-2 text-sm font-medium text-black">Return to DieselBridge</Link></section></main>
}
