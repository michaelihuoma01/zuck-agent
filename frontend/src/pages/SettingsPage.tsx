import { useEffect, useState } from 'react'

export default function SettingsPage() {
  const [installStatus, setInstallStatus] = useState<'installed' | 'not_installed'>('not_installed')

  useEffect(() => {
    const mq = window.matchMedia('(display-mode: standalone)')
    const isStandalone = mq.matches || (window.navigator as Navigator & { standalone?: boolean }).standalone
    setInstallStatus(isStandalone ? 'installed' : 'not_installed')
  }, [])

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-zurk-500">
          Preferences
        </p>
        <h1 className="text-2xl font-semibold text-zurk-50 mt-2">
          Settings
        </h1>
        <p className="text-sm text-zurk-400 mt-1">
          Device and experience preferences
        </p>
      </div>

      <section className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zurk-100">PWA Install</h2>
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full ${
              installStatus === 'installed'
                ? 'bg-status-running/10 text-status-running'
                : 'bg-zurk-600/40 text-zurk-300'
            }`}
          >
            {installStatus === 'installed' ? 'Installed' : 'Not installed'}
          </span>
        </div>
        <p className="text-xs text-zurk-400 mt-1">
          Install ZURK for a faster, app-like experience on mobile.
        </p>
        <p className="text-xs text-zurk-300 mt-2">
          iOS: Share → Add to Home Screen. Android: tap Install when prompted.
        </p>
      </section>

      <section className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl p-4">
        <h2 className="text-sm font-medium text-zurk-100">Connectivity</h2>
        <p className="text-xs text-zurk-400 mt-1">
          WebSocket will auto-reconnect. SSE is used as a fallback on mobile.
        </p>
      </section>
    </div>
  )
}
