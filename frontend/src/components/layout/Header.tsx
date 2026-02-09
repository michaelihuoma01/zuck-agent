import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { health } from '../../api/client'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { useToast } from '../common/Toast'

type ConnectionStatus = 'connected' | 'disconnected' | 'checking'

export default function Header() {
  const [status, setStatus] = useState<ConnectionStatus>('checking')
  const prevStatus = useRef<ConnectionStatus>('checking')
  const online = useOnlineStatus()
  const { warning, success } = useToast()

  useEffect(() => {
    let mounted = true

    async function check() {
      try {
        await health.check()
        if (mounted) setStatus('connected')
      } catch {
        if (mounted) setStatus('disconnected')
      }
    }

    check()
    const interval = setInterval(check, 15_000)
    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [])

  // Toast on status transitions (skip initial check)
  useEffect(() => {
    const prev = prevStatus.current
    prevStatus.current = status

    if (prev === 'checking') return // Skip initial transition

    if (status === 'disconnected' && prev === 'connected') {
      warning('Backend connection lost')
    } else if (status === 'connected' && prev === 'disconnected') {
      success('Backend reconnected')
    }
  }, [status, warning, success])

  return (
    <>
      {!online && (
        <div className="bg-amber-600/90 text-white text-xs text-center py-1 px-4 font-medium">
          You're offline — cached app shell loaded
        </div>
      )}
      <header className="sticky top-0 z-20 h-14 border-b border-zurk-700/70 bg-zurk-800/70 backdrop-blur flex items-center justify-between px-4 sm:px-6">
        <div className="md:hidden flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-zurk-700 border border-zurk-600 flex items-center justify-center">
            <span className="text-zurk-50 font-semibold text-xs">Z</span>
          </div>
          <span className="font-medium text-zurk-50 tracking-[0.08em] text-xs">ZURK</span>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/settings"
            className="hidden sm:inline-flex text-xs text-zurk-400 hover:text-zurk-200 transition-colors"
          >
            Settings
          </Link>
          <div className="flex items-center gap-2 text-sm">
            <div
              className={`w-2 h-2 rounded-full ${
                status === 'connected'
                  ? 'bg-status-running'
                  : status === 'disconnected'
                    ? 'bg-status-error'
                    : 'bg-status-waiting animate-pulse'
              }`}
            />
            <span className="text-zurk-300 text-xs">
              {status === 'connected'
                ? 'Backend online'
                : status === 'disconnected'
                  ? 'Backend offline'
                  : 'Checking...'}
            </span>
          </div>
        </div>
      </header>
    </>
  )
}
