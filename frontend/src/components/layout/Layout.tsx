import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'

export default function Layout() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="md:pl-sidebar">
        <Header />
        <main className="p-5 sm:p-6 pb-32 sm:pb-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
