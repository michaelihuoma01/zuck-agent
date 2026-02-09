import { useEffect, useState, useRef, useCallback } from 'react'

const DISMISS_KEY = 'zurk-install-dismissed'
const DISMISS_DAYS = 30

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export default function InstallPrompt() {
  const [show, setShow] = useState(false)
  const [iosGuide, setIosGuide] = useState(false)
  const deferredPrompt = useRef<BeforeInstallPromptEvent | undefined>(undefined)

  useEffect(() => {
    // Check if previously dismissed within the cooldown period
    const dismissed = localStorage.getItem(DISMISS_KEY)
    if (dismissed) {
      const ts = parseInt(dismissed, 10)
      if (Date.now() - ts < DISMISS_DAYS * 24 * 60 * 60 * 1000) return
    }

    const ua = window.navigator.userAgent.toLowerCase()
    const isIos = /iphone|ipad|ipod/.test(ua)
    const isStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone
    if (isIos && !isStandalone) {
      setIosGuide(true)
    }

    function onBeforeInstall(e: Event) {
      e.preventDefault()
      deferredPrompt.current = e as BeforeInstallPromptEvent
      setShow(true)
    }

    function onInstalled() {
      setShow(false)
      deferredPrompt.current = undefined
    }

    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt.current) return
    await deferredPrompt.current.prompt()
    const { outcome } = await deferredPrompt.current.userChoice
    if (outcome === 'accepted') {
      setShow(false)
    }
    deferredPrompt.current = undefined
  }, [])

  const handleDismiss = useCallback(() => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()))
    setShow(false)
    setIosGuide(false)
    deferredPrompt.current = undefined
  }, [])

  if (!show && !iosGuide) return null

  return (
    <div className="fixed bottom-20 left-4 right-4 sm:bottom-4 sm:left-auto sm:right-4 sm:w-80 z-50 bg-zurk-800/90 border border-zurk-600/70 rounded-lg shadow-lg backdrop-blur p-4">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-10 h-10 bg-accent-500/15 rounded-lg flex items-center justify-center">
          <span className="text-accent-500 font-semibold text-lg">Z</span>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zurk-100">Install Zurk</p>
          <p className="text-xs text-zurk-300 mt-0.5">
            {iosGuide
              ? 'Tap Share and choose “Add to Home Screen”.'
              : 'Add to your home screen for quick access'}
          </p>
          <div className="flex gap-2 mt-3">
            {!iosGuide && (
              <button
                onClick={handleInstall}
                className="px-3 py-1.5 text-xs font-medium bg-accent-600 hover:bg-accent-400 text-zurk-900 rounded-md transition-colors"
              >
                Install
              </button>
            )}
            <button
              onClick={handleDismiss}
              className="px-3 py-1.5 text-xs font-medium text-zurk-300 hover:text-zurk-100 transition-colors"
            >
              {iosGuide ? 'Got it' : 'Not now'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
