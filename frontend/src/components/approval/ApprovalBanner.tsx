import { useState, useCallback, useRef, useEffect } from 'react'
import type { PendingApproval } from '../../api/types'
import { useApprovalShortcuts } from '../../hooks/useApprovalShortcuts'
import Button from '../common/Button'
import DiffViewer from './DiffViewer'
import BashCommandPreview from './BashCommandPreview'

interface ApprovalBannerProps {
  approval: PendingApproval
  onApprove: (feedback?: string) => void
  onDeny: (feedback?: string) => void
  loading?: boolean
}

const riskColors = {
  high: 'border-status-error/50 bg-status-error/5',
  medium: 'border-status-waiting/50 bg-status-waiting/5',
  low: 'border-zurk-600 bg-zurk-700/50',
}

const riskLabels = {
  high: 'High Risk',
  medium: 'Medium Risk',
  low: 'Low Risk',
}

export default function ApprovalBanner({
  approval,
  onApprove,
  onDeny,
  loading = false,
}: ApprovalBannerProps) {
  const [feedback, setFeedback] = useState('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [diffCollapsed, setDiffCollapsed] = useState(false)
  const feedbackRef = useRef<HTMLTextAreaElement>(null)
  const risk = approval.risk_level ?? 'low'

  // Reset state when a new approval arrives
  const prevToolUseId = useRef(approval.tool_use_id)
  useEffect(() => {
    if (approval.tool_use_id !== prevToolUseId.current) {
      prevToolUseId.current = approval.tool_use_id
      setFeedback('')
      setShowFeedback(false)
      setDiffCollapsed(false)
    }
  }, [approval.tool_use_id])

  const isBash = approval.tool_name === 'Bash'
  const hasDiff = !!approval.diff
  const command = isBash ? String(approval.tool_input?.command ?? '') : ''
  const bashDescription = isBash ? (approval.tool_input?.description as string | undefined) : undefined

  // Focus feedback textarea when it appears
  useEffect(() => {
    if (showFeedback) feedbackRef.current?.focus()
  }, [showFeedback])

  const handleApprove = useCallback(() => {
    if (loading) return
    onApprove(feedback || undefined)
  }, [feedback, loading, onApprove])

  const handleDeny = useCallback(() => {
    if (loading) return
    if (!showFeedback) {
      setShowFeedback(true)
      return
    }
    onDeny(feedback || undefined)
  }, [feedback, loading, showFeedback, onDeny])

  const handleEscape = useCallback(() => {
    if (showFeedback) {
      setShowFeedback(false)
    } else {
      setDiffCollapsed(true)
    }
  }, [showFeedback])

  // Keyboard shortcuts: a=approve, d=deny, Escape=collapse
  useApprovalShortcuts({
    onApprove: handleApprove,
    onDeny: handleDeny,
    onEscape: handleEscape,
    enabled: !loading,
  })

  return (
    <div className={`mx-2 sm:mx-4 my-3 border rounded-xl overflow-hidden ${riskColors[risk]}`}>
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="px-3 sm:px-4 py-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <span className="text-sm font-medium text-zurk-100 shrink-0">
            Approval Required
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded-full font-medium shrink-0 ${
              risk === 'high'
                ? 'bg-status-error/20 text-status-error'
                : risk === 'medium'
                  ? 'bg-status-waiting/20 text-status-waiting'
                  : 'bg-zurk-600 text-zurk-300'
            }`}
          >
            {riskLabels[risk]}
          </span>
        </div>
        <span className="text-xs font-mono text-accent-500 shrink-0">{approval.tool_name}</span>
      </div>

      {/* ── Preview: DiffViewer or BashCommandPreview ─────────────── */}
      <div className="px-2 sm:px-4 mb-3">
        {isBash && command ? (
          <BashCommandPreview
            command={command}
            description={bashDescription}
            riskLevel={risk}
          />
        ) : hasDiff ? (
          <DiffViewer
            diff={approval.diff!}
            stats={approval.diff_stats}
            tier={approval.diff_tier}
            totalBytes={approval.total_bytes}
            totalLines={approval.total_lines}
            defaultCollapsed={diffCollapsed}
          />
        ) : (
          /* Generic tool input preview */
          <div className="rounded-lg border border-zurk-600/40 bg-zurk-900 overflow-hidden">
            <div className="px-3 py-2 text-xs text-zurk-400 font-mono">
              {approval.tool_name}
            </div>
            <pre className="border-t border-zurk-700/50 text-xs font-mono text-zurk-300 p-3 max-h-48 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(approval.tool_input, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* ── Feedback textarea (toggle) ────────────────────────────── */}
      {showFeedback && (
        <div className="px-2 sm:px-4 mb-3">
          <textarea
            ref={feedbackRef}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Feedback for Claude (e.g. 'use a different approach')..."
            rows={2}
            className="w-full bg-zurk-900 border border-zurk-600 rounded-lg px-3 py-2 text-sm
              text-zurk-100 placeholder:text-zurk-500 resize-none
              focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          />
        </div>
      )}

      {/* ── Actions ───────────────────────────────────────────────── */}
      <div className="px-2 sm:px-4 py-3 flex items-center gap-2 border-t border-zurk-600/50">
        {/* Mobile: full-width stacked buttons. Desktop: inline */}
        <div className="flex gap-2 w-full sm:w-auto">
          <Button
            variant="primary"
            size="md"
            onClick={handleApprove}
            loading={loading}
            className="flex-1 sm:flex-none min-h-[44px] sm:min-h-0"
          >
            Approve
          </Button>
          <Button
            variant="danger"
            size="md"
            onClick={handleDeny}
            loading={loading}
            className="flex-1 sm:flex-none min-h-[44px] sm:min-h-0"
          >
            Deny
          </Button>
        </div>
        {!showFeedback && (
          <button
            onClick={() => setShowFeedback(true)}
            className="text-xs text-zurk-400 hover:text-zurk-200 ml-auto hidden sm:block"
          >
            Add feedback
          </button>
        )}
        {/* Keyboard hint — hidden on mobile */}
        <span className="text-[10px] text-zurk-600 ml-auto hidden sm:block">
          a approve · d deny · esc close
        </span>
      </div>
    </div>
  )
}
