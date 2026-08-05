import React from 'react';

interface StatusBarProps {
  darkMode: boolean;
  toggleDarkMode: () => void;
  onOpenProfile?: () => void;
  llmAvailable?: boolean;
}

const StatusBar: React.FC<StatusBarProps> = ({ darkMode, toggleDarkMode, onOpenProfile, llmAvailable = true }) => {
  return (
    <div className="flex justify-between items-center px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow-sm shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-white">
            <path d="M12 2a10 10 0 0 0-10 10c0 5.52 4.48 10 10 10s10-4.48 10-10c0-5.52-4.48-10-10-10zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
            <path d="M12 6v6l4 2" />
          </svg>
        </div>
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-black tracking-tight text-gray-900 dark:text-gray-100 truncate">智能校园助手</h1>
          <p className="mt-0.5 text-[10px] text-gray-500 dark:text-gray-400 truncate uppercase tracking-widest">Campus AI Assistant</p>
        </div>
        {!llmAvailable && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 dark:bg-red-900/30 px-2.5 py-1 text-[10px] font-bold text-red-600 dark:text-red-400 whitespace-nowrap">
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            未配置 API
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={toggleDarkMode}
          className="h-9 w-9 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center justify-center shrink-0"
          aria-label={darkMode ? '切换到浅色模式' : '切换到深色模式'}
        >
          {darkMode ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-yellow-400">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600 dark:text-gray-300">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
        <button onClick={onOpenProfile} className="inline-flex items-center px-4 py-2 text-xs leading-none font-bold border border-green-200 dark:border-green-800 rounded-full bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 transition-all text-green-600 dark:text-green-400 shadow-sm">
          个人中心
        </button>
      </div>
    </div>
  );
};

export default StatusBar;