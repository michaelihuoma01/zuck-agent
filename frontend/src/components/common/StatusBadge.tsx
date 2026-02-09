import type { SessionStatus } from '../../api/types'
import { STATUS_CONFIG } from '../../config/statusConfig'

export default function StatusBadge({ status }: { status: SessionStatus }) {
  const v = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${v.bgColor} ${v.color}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${v.dotColor}`} />
      {v.label}
    </span>
  )
}
