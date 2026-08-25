import { useState, useEffect, useCallback } from 'react'
import StatusBar from './components/StatusBar'
import SchedulePlanner from './components/SchedulePlanner'
import CampusAssistant from './components/CampusAssistant'
import LearningAssistant from './components/LearningAssistant'
import ScriptAutomation from './components/ScriptAutomation'
import CourseRecommendation from './components/CourseRecommendation'
import PersonalPanel from './components/PersonalPanel'
import HelpCenter from './components/HelpCenter'
import SettingsModal from './components/SettingsModal'
import { fetchLLMStatus } from './api'

function App() {
  const [darkMode, setDarkMode] = useState(localStorage.getItem('darkMode') === 'true')
  const [activeTab, setActiveTab] = useState('calendar')
  const [showProfile, setShowProfile] = useState(false)
  const [showHelpCenter, setShowHelpCenter] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [userName, setUserName] = useState(localStorage.getItem('userName') || '')
  const [userStudentId, setUserStudentId] = useState(localStorage.getItem('userStudentId') || '')
  const [userMajor, setUserMajor] = useState(localStorage.getItem('userMajor') || '')
  const [userGrade] = useState(localStorage.getItem('userGrade') || '大三')
  const [llmAvailable, setLlmAvailable] = useState(true)
  // ── Dark mode ──────────────────────────────────────────────────
  useEffect(() => {
    // Only use system preference if user hasn't set a preference
    const storedDarkMode = localStorage.getItem('darkMode')
    if (storedDarkMode === null && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setDarkMode(true)
      localStorage.setItem('darkMode', 'true')
    }
  }, [])

  const toggleDarkMode = useCallback(() => {
    setDarkMode((prev) => {
      const newValue = !prev
      localStorage.setItem('darkMode', String(newValue))
      return newValue
    })
  }, [])

  // ── Check LLM availability from backend on page load ──────────
  useEffect(() => {
    fetchLLMStatus()
      .then((status) => setLlmAvailable(status.llm_available))
      .catch(() => {})
  }, [])

  // ── Handlers ───────────────────────────────────────────────────
  const handlePersonalSave = (profile: { name: string; studentId: string; major: string }) => {
    console.debug('[App] handlePersonalSave', profile)
    setUserName(profile.name)
    setUserStudentId(profile.studentId)
    setUserMajor(profile.major)
    localStorage.setItem('userName', profile.name)
    localStorage.setItem('userStudentId', profile.studentId)
    localStorage.setItem('userMajor', profile.major)
    setShowProfile(false)
  }

  const handleLLMSave = () => {
    // Config saved on backend; re-check availability
    // Return the promise so callers can await it
    return fetchLLMStatus()
      .then((status) => {
        setLlmAvailable(status.llm_available)
      })
      .catch(() => {})
  }

  const handleOpenProfile = () => setShowProfile(true)

  // ── Keyboard shortcuts ─────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+1~5 - Switch between main tabs
      if (e.ctrlKey && ['1', '2', '3', '4', '5'].includes(e.key)) {
        e.preventDefault()
        const tabMap: Record<string, string> = {
          '1': 'calendar',
          '2': 'campus',
          '3': 'learning',
          '4': 'script',
          '5': 'course',
        }
        setActiveTab(tabMap[e.key])
      }
      // Ctrl+D - Toggle dark mode
      if (e.ctrlKey && e.key === 'd') {
        e.preventDefault()
        toggleDarkMode()
      }
      // Esc - Close all modals
      if (e.key === 'Escape') {
        setShowHelpCenter(false)
        setShowSettings(false)
        setShowProfile(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggleDarkMode])

  return (
    <div className={`h-screen overflow-hidden flex flex-col ${darkMode ? 'dark' : ''} bg-gray-100 dark:bg-slate-950`}>
      <StatusBar darkMode={darkMode} toggleDarkMode={toggleDarkMode} onOpenProfile={handleOpenProfile} llmAvailable={llmAvailable} />
      <PersonalPanel
        open={showProfile}
        onClose={() => setShowProfile(false)}
        onSave={handlePersonalSave}
        onLLMSave={handleLLMSave}
        onStudentIdChange={(studentId) => {
          setUserStudentId(studentId)
          localStorage.setItem('userStudentId', studentId)
        }}
        initialName={userName}
        initialStudentId={userStudentId}
        initialMajor={userMajor}
      />
      
      <div className="flex flex-1 min-h-0 overflow-hidden p-4 bg-gray-200/60 dark:bg-slate-900">
        <div className="w-[280px] rounded-[30px] border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/70 p-5 flex flex-col shadow-inner">
          <div className="mb-6">
            <h2 className="text-[10px] uppercase font-bold text-gray-400 dark:text-gray-500 tracking-widest mb-4 px-2">主菜单</h2>
            <ul className="space-y-2">
              <li>
                <button onClick={() => setActiveTab('calendar')}
                  className={`w-full text-left px-4 py-3.5 rounded-2xl transition-all flex items-center gap-3 ${activeTab === 'calendar' ? 'bg-green-500 text-white dark:bg-green-600 font-semibold shadow-lg shadow-green-300/30 dark:shadow-green-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10m-11 9h12a2 2 0 002-2V7a2 2 0 00-2-2H6a2 2 0 00-2 2v11a2 2 0 002 2z" />
                  </svg>
                  <span className="text-sm font-medium leading-none">日程规划</span>
                </button>
              </li>
              <li>
                <button onClick={() => setActiveTab('campus')}
                  className={`w-full text-left px-4 py-3.5 rounded-2xl transition-all flex items-center gap-3 ${activeTab === 'campus' ? 'bg-green-500 text-white dark:bg-green-600 font-semibold shadow-lg shadow-green-300/30 dark:shadow-green-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3v2.25m4.5-2.25v2.25M6 18.75h12A2.25 2.25 0 0020.25 16.5V9A2.25 2.25 0 0018 6.75H6A2.25 2.25 0 003.75 9v7.5A2.25 2.25 0 006 18.75z" />
                    <circle cx="9" cy="12" r="1" />
                    <circle cx="15" cy="12" r="1" />
                  </svg>
                  <span className="text-sm font-medium leading-none">校园信息助手</span>
                </button>
              </li>
              <li>
                <button onClick={() => setActiveTab('learning')}
                  className={`w-full text-left px-4 py-3.5 rounded-2xl transition-all flex items-center gap-3 ${activeTab === 'learning' ? 'bg-green-500 text-white dark:bg-green-600 font-semibold shadow-lg shadow-green-300/30 dark:shadow-green-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  <span className="text-sm font-medium leading-none">学习助手</span>
                </button>
              </li>
              <li>
                <button onClick={() => setActiveTab('script')}
                  className={`w-full text-left px-4 py-3.5 rounded-2xl transition-all flex items-center gap-3 ${activeTab === 'script' ? 'bg-green-500 text-white dark:bg-green-600 font-semibold shadow-lg shadow-green-300/30 dark:shadow-green-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 000-2.828L4 4m16 12l-4.586-4.586a2 2 0 010-2.828L20 4" />
                  </svg>
                  <span className="text-sm font-medium leading-none">脚本自动化</span>
                </button>
              </li>
              <li>
                <button onClick={() => setActiveTab('course')}
                  className={`w-full text-left px-4 py-3.5 rounded-2xl transition-all flex items-center gap-3 ${activeTab === 'course' ? 'bg-green-500 text-white dark:bg-green-600 font-semibold shadow-lg shadow-green-300/30 dark:shadow-green-900/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800/70 text-gray-700 dark:text-gray-300'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a8 8 0 018 8h-2a6 6 0 00-6-6V6zm0 12v2m0-2a8 8 0 01-8-8h2a6 6 0 006 6v2zm10-8h2m-2 0a8 8 0 00-8-8V4m-8 8H2m2 0a8 8 0 018-8v2" />
                  </svg>
                  <span className="text-sm font-medium leading-none">选课推荐</span>
                </button>
              </li>
            </ul>
          </div>
          <div className="mt-auto">
            <h2 className="text-[10px] uppercase font-bold text-gray-400 dark:text-gray-500 tracking-widest mb-4 px-2">辅助功能</h2>
            <ul className="space-y-2">
              <li>
                <button
                  onClick={() => setShowHelpCenter(true)}
                  className="w-full text-left px-4 py-3 rounded-2xl transition-colors hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                >
                  <span className="inline-flex items-center gap-2 text-sm font-medium">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9a3 3 0 115.544 1.5c-.901.83-1.272 1.27-1.272 2.25M12 17h.01" />
                    </svg>
                    帮助中心
                  </span>
                </button>
              </li>
              <li>
                <button
                  onClick={() => setShowSettings(true)}
                  className="w-full text-left px-4 py-3 rounded-2xl transition-colors hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                >
                  <span className="inline-flex items-center gap-2 text-sm font-medium">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317a1 1 0 011.35-.936l1.94.776a1 1 0 00.768 0l1.94-.776a1 1 0 011.35.936l.132 2.077a1 1 0 00.548.82l1.78.89a1 1 0 01.486 1.486l-1.15 1.734a1 1 0 000 .924l1.15 1.734a1 1 0 01-.486 1.486l-1.78.89a1 1 0 00-.548.82l-.132 2.077a1 1 0 01-1.35.936l-1.94-.776a1 1 0 00-.768 0l-1.94.776a1 1 0 01-1.35-.936l-.132-2.077a1 1 0 00-.548-.82l-1.78-.89a1 1 0 01-.486-1.486l1.15-1.734a1 1 0 000-.924l-1.15-1.734a1 1 0 01.486-1.486l1.78-.89a1 1 0 00.548-.82l.132-2.077z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                    系统设置
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </div>

        <div className="flex-1 min-h-0 ml-4 rounded-[30px] border border-gray-200/80 dark:border-gray-700 bg-gray-100/80 dark:bg-slate-950 overflow-hidden relative">
          <div className={activeTab === 'calendar' ? 'h-full' : 'h-full hidden'}><SchedulePlanner llmAvailable={llmAvailable} onOpenProfile={handleOpenProfile} /></div>
          <div className={activeTab === 'campus' ? 'h-full' : 'h-full hidden'}><CampusAssistant llmAvailable={llmAvailable} onOpenProfile={handleOpenProfile} /></div>
          <div className={activeTab === 'learning' ? 'h-full' : 'h-full hidden'}><LearningAssistant llmAvailable={llmAvailable} onOpenProfile={handleOpenProfile} /></div>
          <div className={activeTab === 'script' ? 'h-full' : 'h-full hidden'}><ScriptAutomation llmAvailable={llmAvailable} onOpenProfile={handleOpenProfile} /></div>
          <div className={activeTab === 'course' ? 'h-full' : 'h-full hidden'}><CourseRecommendation initialMajor={userMajor} initialGrade={userGrade} /></div>
        </div>
      </div>

      {/* Help Center Modal */}
      {showHelpCenter && <HelpCenter onClose={() => setShowHelpCenter(false)} />}

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal
          onClose={() => setShowSettings(false)}
          darkMode={darkMode}
          onToggleDarkMode={toggleDarkMode}
        />
      )}

    </div>
  )
}

export default App;