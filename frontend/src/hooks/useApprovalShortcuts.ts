import { useEffect, useCallback } from 'react'

interface ApprovalShortcutHandlers {
  onApprove: () => void
  onDeny: () => void
  onEscape: () => void
  enabled: boolean
}

/**
 * Keyboard shortcuts for the approval workflow.
 *
 * - `a` — Approve (when no input is focused)
 * - `d` — Deny / open feedback (when no input is focused)
 * - `Escape` — Collapse expanded diff
 *
 * All single-key shortcuts are suppressed when an input, textarea,
 * or select element is focused.
 */
export function useApprovalShortcuts({
  onApprove,
  onDeny,
  onEscape,
  enabled,
}: ApprovalShortcutHandlers) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return

      // Escape works even when focused on an input
      if (e.key === 'Escape') {
        onEscape()
        return
      }

      // Skip when modifier keys are held (Ctrl+A = select all, not approve)
      if (e.ctrlKey || e.metaKey || e.altKey) return

      // Skip single-key shortcuts when user is typing
      const el = document.activeElement
      const tag = (el?.tagName ?? '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (el && 'isContentEditable' in el && (el as HTMLElement).isContentEditable) return

      if (e.key === 'a') {
        e.preventDefault()
        onApprove()
      } else if (e.key === 'd') {
        e.preventDefault()
        onDeny()
      }
    },
    [enabled, onApprove, onDeny, onEscape],
  )

  useEffect(() => {
    if (!enabled) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [enabled, handleKeyDown])
}
