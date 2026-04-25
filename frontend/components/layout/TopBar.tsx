'use client'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { LogOut, User } from 'lucide-react'

export default function TopBar() {
  const { user, logout } = useAuth()

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-700 bg-gray-800 px-6">
      <div />
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-700">
            <User className="h-4 w-4 text-gray-400" />
          </div>
          <span className="text-sm text-gray-300">{user?.email || user?.username || 'User'}</span>
        </div>
        <Button variant="ghost" size="sm" onClick={logout} className="text-gray-400 hover:text-white">
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>
    </header>
  )
}
