import { NavLink } from 'react-router-dom'
import { useSessions } from '../../hooks/useSessions'

function NavItem({
  to,
  label,
  icon,
  indicator,
}: {
  to: string
  label: string
  icon: React.ReactNode
  indicator?: boolean
}) {
  return (
    <NavLink
      to={to}
      className="flex flex-col items-center justify-center gap-1 text-[10px] font-medium"
    >
      {({ isActive }) => (
        <>
          <span
            className={`w-9 h-9 flex items-center justify-center rounded-xl transition-colors ${
              isActive
                ? 'bg-zurk-700/70 text-accent-600'
                : 'text-zurk-400 hover:text-zurk-200'
            }`}
          >
            <span className="w-5 h-5 relative">
              {icon}
              {indicator && (
                <span className="absolute -top-1 -right-1 w-1 h-1 rounded-sm bg-status-running" />
              )}
            </span>
          </span>
          <span className={isActive ? 'text-accent-600' : 'text-zurk-400'}>
            {label}
          </span>
        </>
      )}
    </NavLink>
  )
}

export default function MobileBottomNav() {
  const { data: sessionData } = useSessions()
  const activeCount =
    sessionData?.sessions.filter(
      (s) => s.status === 'running' || s.status === 'waiting_approval',
    ).length ?? 0

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-zurk-700/70 bg-zurk-800/90 backdrop-blur md:hidden pb-[calc(env(safe-area-inset-bottom)+18px)]">
      <div className="max-w-md mx-auto px-2 py-3.5 grid grid-cols-3 gap-3">
        <NavItem
          to="/"
          label="Home"
          indicator={activeCount > 0}
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.25 12 11.204 3.045a1.5 1.5 0 0 1 2.121 0L21.75 12m-1.5 0v7.125A2.625 2.625 0 0 1 17.625 21H6.375A2.625 2.625 0 0 1 3.75 19.125V12"
              />
            </svg>
          }
        />
        <NavItem
          to="/projects"
          label="Projects"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"
              />
            </svg>
          }
        />
        <NavItem
          to="/settings"
          label="Settings"
          icon={
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10.5 6h3m-1.5 12h.008M6.75 6h.008m10.492 1.636a2.25 2.25 0 0 1 2.122 1.743l.046.238a2.25 2.25 0 0 1-.646 2.069l-.168.168a2.25 2.25 0 0 0 0 3.182l.168.168c.527.527.78 1.256.646 1.997l-.046.238a2.25 2.25 0 0 1-1.743 1.743l-.238.046a2.25 2.25 0 0 1-1.997-.646l-.168-.168a2.25 2.25 0 0 0-3.182 0l-.168.168a2.25 2.25 0 0 1-1.997.646l-.238-.046a2.25 2.25 0 0 1-1.743-1.743l-.046-.238a2.25 2.25 0 0 1 .646-1.997l.168-.168a2.25 2.25 0 0 0 0-3.182l-.168-.168a2.25 2.25 0 0 1-.646-2.069l.046-.238A2.25 2.25 0 0 1 6.36 7.636l.238-.046a2.25 2.25 0 0 1 1.997.646l.168.168a2.25 2.25 0 0 0 3.182 0l.168-.168a2.25 2.25 0 0 1 1.997-.646l.238.046Z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
            </svg>
          }
        />
      </div>
    </div>
  )
}
