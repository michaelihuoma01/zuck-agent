import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

// ── Types ───────────────────────────────────────────────────────────

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: string
  type: ToastType
  message: string
  duration: number
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType, duration?: number) => void
  success: (message: string) => void
  error: (message: string) => void
  warning: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

// ── Provider ────────────────────────────────────────────────────────

const DEFAULT_DURATION = 4000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counterRef = useRef(0)

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback(
    (message: string, type: ToastType = 'info', duration = DEFAULT_DURATION) => {
      const id = `toast-${++counterRef.current}`
      setToasts((prev) => [...prev.slice(-4), { id, type, message, duration }])

      if (duration > 0) {
        setTimeout(() => removeToast(id), duration)
      }
    },
    [removeToast],
  )

  const contextValue: ToastContextValue = {
    toast: addToast,
    success: useCallback((msg: string) => addToast(msg, 'success'), [addToast]),
    error: useCallback((msg: string) => addToast(msg, 'error', 6000), [addToast]),
    warning: useCallback((msg: string) => addToast(msg, 'warning', 5000), [addToast]),
    info: useCallback((msg: string) => addToast(msg, 'info'), [addToast]),
  }

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  )
}

// ── Hook ────────────────────────────────────────────────────────────

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

// ── Toast Container ─────────────────────────────────────────────────

const typeStyles: Record<ToastType, { bg: string; border: string; icon: string; iconColor: string }> = {
  success: {
    bg: 'bg-status-running/10',
    border: 'border-status-running/25',
    icon: 'M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
    iconColor: 'text-status-running',
  },
  error: {
    bg: 'bg-status-error/10',
    border: 'border-status-error/25',
    icon: 'M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z',
    iconColor: 'text-status-error',
  },
  warning: {
    bg: 'bg-status-waiting/10',
    border: 'border-status-waiting/25',
    icon: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z',
    iconColor: 'text-status-waiting',
  },
  info: {
    bg: 'bg-accent-500/10',
    border: 'border-accent-500/20',
    icon: 'm11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z',
    iconColor: 'text-accent-500',
  },
}

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[]
  onDismiss: (id: string) => void
}) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => {
        const style = typeStyles[toast.type]
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border backdrop-blur-sm shadow-lg
              animate-[slideUp_0.2s_ease-out] ${style.bg} ${style.border}`}
            role="alert"
          >
            <svg
              className={`w-4.5 h-4.5 shrink-0 mt-0.5 ${style.iconColor}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d={style.icon} />
            </svg>
            <p className="text-sm text-zurk-100 flex-1 break-words">{toast.message}</p>
            <button
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 text-zurk-400 hover:text-zurk-200 transition-colors"
              aria-label="Dismiss"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )
      })}
    </div>
  )
}
