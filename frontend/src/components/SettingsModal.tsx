import { useState } from 'react'

interface SettingsModalProps {
  onClose: () => void
  darkMode: boolean
  onToggleDarkMode: () => void
}

type SettingsTab = 'appearance' | 'data' | 'about'

const SettingsModal: React.FC<SettingsModalProps> = ({ onClose, darkMode, onToggleDarkMode }) => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('appearance')
  const [fontSize, setFontSize] = useState<string>(localStorage.getItem('fontSize') || 'medium')
  const handleFontSizeChange = (size: string) => {
    setFontSize(size)
    localStorage.setItem('fontSize', size)
    // Apply font size to root element
    const root = document.documentElement
    const sizeMap: Record<string, string> = {
      small: '14px',
      medium: '16px',
      large: '18px',
      xlarge: '20px',
    }
    root.style.fontSize = sizeMap[size] || '16px'
  }

  const handleClearCache = () => {
    // Clear all localStorage items related to the app
    const keysToKeep = ['userName', 'userStudentId', 'userMajor', 'userGrade']
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && !keysToKeep.includes(key)) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key))
    alert('缓存已刷新！页面将自动刷新。')
    window.location.reload()
  }

  const tabConfig = [
    { id: 'appearance' as const, label: '外观', icon: '🎨' },
    { id: 'data' as const, label: '数据管理', icon: '💾' },
    { id: 'about' as const, label: '关于', icon: 'ℹ️' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="relative w-full max-w-lg mx-4 max-h-[80vh] rounded-3xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-purple-400 to-pink-500 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">系统设置</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">个性化您的使用体验</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="h-9 w-9 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center justify-center"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex px-6 pt-3 gap-1">
          {tabConfig.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-all flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? 'bg-purple-500 text-white shadow-md'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'appearance' && (
            <div className="space-y-6">
              {/* Dark Mode Toggle */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">主题模式</label>
                <div className="flex items-center justify-between p-4 rounded-2xl bg-gray-50 dark:bg-gray-800">
                  <div className="flex items-center gap-3">
                    {darkMode ? (
                      <span className="text-2xl">🌙</span>
                    ) : (
                      <span className="text-2xl">☀️</span>
                    )}
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {darkMode ? '深色模式' : '浅色模式'}
                      </p>
                      <p className="text-xs text-gray-500">当前主题</p>
                    </div>
                  </div>
                  <button
                    onClick={onToggleDarkMode}
                    className={`relative h-6 w-11 rounded-full transition-colors ${
                      darkMode ? 'bg-purple-500' : 'bg-gray-300'
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
                        darkMode ? 'left-[22px]' : 'left-0.5'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Font Size */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">字体大小</label>
                <div className="grid grid-cols-4 gap-2">
                  {([
                    { id: 'small', label: '小', sample: 'Aa' },
                    { id: 'medium', label: '中', sample: 'Aa' },
                    { id: 'large', label: '大', sample: 'Aa' },
                    { id: 'xlarge', label: '特大', sample: 'Aa' },
                  ] as const).map((size) => (
                    <button
                      key={size.id}
                      onClick={() => handleFontSizeChange(size.id)}
                      className={`p-3 rounded-xl border-2 transition-all flex flex-col items-center gap-1 ${
                        fontSize === size.id
                          ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                      }`}
                    >
                      <span className={`font-serif ${
                        size.id === 'small' ? 'text-sm' :
                        size.id === 'medium' ? 'text-base' :
                        size.id === 'large' ? 'text-lg' : 'text-xl'
                      }`}>
                        {size.sample}
                      </span>
                      <span className="text-xs text-gray-600 dark:text-gray-400">{size.label}</span>
                    </button>
                  ))}
                </div>
              </div>

            </div>
          )}

          {activeTab === 'data' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                管理本地缓存数据，清除缓存后页面将自动刷新。
              </p>

              {/* User Info Display */}
              <div className="p-4 rounded-2xl bg-gray-50 dark:bg-gray-800 space-y-3">
                <h4 className="text-sm font-medium text-gray-900 dark:text-white">当前用户信息</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">姓名</span>
                    <span className="text-gray-900 dark:text-white">{localStorage.getItem('userName') || '未设置'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">学号</span>
                    <span className="text-gray-900 dark:text-white">{localStorage.getItem('userStudentId') || '未设置'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">专业</span>
                    <span className="text-gray-900 dark:text-white">{localStorage.getItem('userMajor') || '未设置'}</span>
                  </div>
                </div>
              </div>

              {/* Clear Cache Button */}
              <button
                onClick={handleClearCache}
                className="w-full py-3 rounded-xl border-2 border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 font-medium text-sm hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
              >
                🗑️ 清除缓存（保留用户信息）
              </button>

              <p className="text-xs text-gray-400 text-center">
                注意：清除缓存会删除所有本地设置，包括外观偏好等
              </p>
            </div>
          )}

          {activeTab === 'about' && (
            <div className="space-y-6 text-center">
              <div className="pt-4">
                <div className="mx-auto h-16 w-16 rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow-lg">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                </div>
              </div>

              <div>
                <h3 className="text-xl font-bold text-gray-900 dark:text-white">智能校园助手</h3>
                <p className="text-sm text-gray-500 mt-1">版本 1.0.0</p>
              </div>

              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                基于 AI 的智能课程推荐系统，帮助学生根据培养方案和个人偏好生成最优课表。
              </p>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="p-3 rounded-xl bg-gray-50 dark:bg-gray-800">
                  <p className="text-xs text-gray-500">前端技术</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">React + Tailwind</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 dark:bg-gray-800">
                  <p className="text-xs text-gray-500">后端技术</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">FastAPI + LLM</p>
                </div>
              </div>

              <p className="text-xs text-gray-400 pt-2">
                © 2026 26s-22 项目组 · All rights reserved
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsModal
