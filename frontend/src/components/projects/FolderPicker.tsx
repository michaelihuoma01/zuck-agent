import { useState } from 'react'
import { useBrowseDirectory } from '../../hooks/useProjects'
import Button from '../common/Button'

interface FolderPickerProps {
  onSelect: (path: string) => void
  onClose: () => void
}

export default function FolderPicker({ onSelect, onClose }: FolderPickerProps) {
  const [currentPath, setCurrentPath] = useState<string | undefined>(undefined)
  const { data, isLoading, error } = useBrowseDirectory(currentPath)

  const handleSelect = () => {
    if (data?.current_path) {
      onSelect(data.current_path)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-2 sm:mx-4 bg-zurk-800 border border-zurk-700/70 rounded-xl shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="px-4 py-3 border-b border-zurk-700/50">
          <h3 className="text-sm font-semibold text-zurk-100">
            Select Directory
          </h3>
        </div>

        {/* Breadcrumbs */}
        {data?.breadcrumbs && data.breadcrumbs.length > 0 && (
          <div className="px-4 py-2 border-b border-zurk-700/30 flex items-center gap-1 text-xs overflow-x-auto">
            {data.breadcrumbs.map((crumb, i) => (
              <span key={crumb.path} className="flex items-center gap-1 shrink-0">
                {i > 0 && <span className="text-zurk-600">/</span>}
                <button
                  onClick={() => setCurrentPath(crumb.path)}
                  className="text-accent-400 hover:text-accent-300 transition-colors"
                >
                  {crumb.name}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Shortcuts (only at home level) */}
        {data?.shortcuts && data.shortcuts.length > 0 && (
          <div className="px-4 py-2 border-b border-zurk-700/30 flex flex-wrap gap-2">
            {data.shortcuts.map((shortcut) => (
              <button
                key={shortcut.path}
                onClick={() => setCurrentPath(shortcut.path)}
                className="text-xs px-2 py-1 rounded-md bg-zurk-700/50 text-zurk-300 hover:bg-zurk-600/50 hover:text-zurk-100 transition-colors"
              >
                {shortcut.name}
              </button>
            ))}
          </div>
        )}

        {/* Directory list */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {isLoading && (
            <div className="px-4 py-8 text-center text-zurk-500 text-sm">
              Loading...
            </div>
          )}

          {error && (
            <div className="px-4 py-8 text-center text-status-error text-sm">
              {error instanceof Error ? error.message : 'Failed to browse directory'}
            </div>
          )}

          {data && !isLoading && (
            <div className="py-1">
              {/* Back button */}
              {data.parent_path && (
                <button
                  onClick={() => setCurrentPath(data.parent_path ?? undefined)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-zurk-700/50 transition-colors text-left"
                >
                  <svg className="w-4 h-4 text-zurk-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
                  </svg>
                  <span className="text-sm text-zurk-400">..</span>
                </button>
              )}

              {data.entries.length === 0 && (
                <div className="px-4 py-6 text-center text-zurk-500 text-xs">
                  No subdirectories
                </div>
              )}

              {data.entries.map((entry) => (
                <button
                  key={entry.path}
                  onClick={() => setCurrentPath(entry.path)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-zurk-700/50 transition-colors text-left group"
                >
                  {/* Folder icon */}
                  <svg
                    className={`w-4 h-4 shrink-0 ${
                      entry.project_indicators.length > 0
                        ? 'text-accent-400'
                        : 'text-zurk-500'
                    }`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
                  </svg>

                  <div className="flex-1 min-w-0 flex items-center gap-2">
                    <span className={`text-sm truncate ${
                      entry.project_indicators.length > 0
                        ? 'text-zurk-50 font-medium'
                        : 'text-zurk-200'
                    }`}>
                      {entry.name}
                    </span>
                    {entry.project_indicators.length > 0 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent-500/10 text-accent-400 shrink-0">
                        {entry.project_indicators[0] === '.git' ? 'git' : entry.project_indicators[0]}
                      </span>
                    )}
                  </div>

                  {/* Chevron if has children */}
                  {entry.has_children && (
                    <svg className="w-3 h-3 text-zurk-600 group-hover:text-zurk-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-zurk-700/50">
          <div className="text-[10px] text-zurk-600 font-mono truncate mb-2">
            {data?.current_path ?? '~'}
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSelect}
              disabled={!data?.current_path}
            >
              Select
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
