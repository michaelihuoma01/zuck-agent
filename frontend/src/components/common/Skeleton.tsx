/**
 * Reusable skeleton loading placeholder.
 * Use the variant prop for common patterns, or compose with className for custom layouts.
 */

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div className={`animate-pulse bg-zurk-700/70 rounded ${className}`} />
  )
}

/** Skeleton for a single session row in a list */
export function SessionRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <Skeleton className="h-3 w-28" />
      </div>
      <Skeleton className="h-3 w-14" />
    </div>
  )
}

/** Skeleton for a project card */
export function ProjectCardSkeleton() {
  return (
    <div className="p-4 rounded-xl bg-zurk-800 border border-zurk-700 space-y-3">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-3 w-full" />
      <div className="flex items-center gap-3 mt-3">
        <Skeleton className="h-3 w-36" />
        <Skeleton className="h-3 w-16 ml-auto" />
      </div>
    </div>
  )
}

/** Skeleton for a list of session rows */
export function SessionListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-1">
      {Array.from({ length: count }, (_, i) => (
        <SessionRowSkeleton key={i} />
      ))}
    </div>
  )
}

/** Skeleton for a grid of project cards */
export function ProjectListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <ProjectCardSkeleton key={i} />
      ))}
    </div>
  )
}
