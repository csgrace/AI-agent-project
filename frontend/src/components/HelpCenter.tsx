import { useState } from 'react'

interface HelpCenterProps {
  onClose: () => void
}

interface FaqItem {
  question: string
  answer: string
}

const faqData: FaqItem[] = [
  {
    question: '如何获取课程推荐？',
    answer: '选择目标学期，系统会根据您的专业、已修课程和培养方案自动生成推荐课表。您还可以在"个人中心"设置专业方向和个人偏好。',
  },
  {
    question: '推荐课程依据什么生成？',
    answer: '系统综合以下因素生成推荐：1) 培养方案的毕业要求；2) 您已修读的课程；3) 课程时间冲突检测；4) 您的职业方向和兴趣偏好。',
  },
  {
    question: '什么是"理论型/实践型/均衡型"方案？',
    answer: '理论型方案侧重数学、专业基础课等理论课程；实践型方案增加实验、项目课比重；均衡型方案两者兼顾。您可以根据个人发展方向选择。',
  },
  {
    question: '推荐课表中有课程显示"无具体时间"？',
    answer: '部分课程的上课时间可能尚未公布或数据暂未收录。这些课程会被标记为"待确认"，您可以在选课时关注系统更新。',
  },
  {
    question: '如何查看毕业要求完成情况？',
    answer: '在"学业状态"页面可以查看各类课程的学分完成情况，包括思政类、体育类、专业必修课等各个类别的进度。',
  },
  {
    question: '时间冲突的课程如何处理？',
    answer: '系统会自动检测时间冲突，避免推荐时间重叠的课程。如果您手动添加了冲突课程，系统会显示警告提示。',
  },
]

const quickStartSteps = [
  { step: 1, title: '填写个人信息', desc: '点击右上角"个人中心"，填写您的姓名、学号和专业' },
  { step: 2, title: '选择目标学期', desc: '在"选课推荐"页面选择您要规划的学期' },
  { step: 3, title: '生成推荐方案', desc: '点击"生成推荐"按钮，系统会提供多种方案供选择' },
  { step: 4, title: '对比并选择', desc: '查看不同方案的课程安排，选择最适合您的课表' },
]

const shortcuts = [
  { keys: 'Ctrl + 1', action: '日程规划' },
  { keys: 'Ctrl + 2', action: '校园信息助手' },
  { keys: 'Ctrl + 3', action: '学习助手' },
  { keys: 'Ctrl + 4', action: '脚本自动化' },
  { keys: 'Ctrl + 5', action: '选课推荐' },
  { keys: 'Ctrl + D', action: '切换深色/浅色模式' },
  { keys: 'Esc', action: '关闭弹窗/面板' },
]

type TabType = 'faq' | 'guide' | 'shortcuts'

const HelpCenter: React.FC<HelpCenterProps> = ({ onClose }) => {
  const [activeTab, setActiveTab] = useState<TabType>('faq')
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl mx-4 max-h-[85vh] rounded-3xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">帮助中心</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">使用指南与常见问题</p>
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
          {([
            { id: 'faq', label: '常见问题' },
            { id: 'guide', label: '快速入门' },
            { id: 'shortcuts', label: '快捷键' },
          ] as const).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'faq' && (
            <div className="space-y-3">
              {faqData.map((item, index) => (
                <div
                  key={index}
                  className="rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden"
                >
                  <button
                    onClick={() => setExpandedFaq(expandedFaq === index ? null : index)}
                    className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                  >
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {item.question}
                    </span>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className={`h-4 w-4 text-gray-400 transition-transform ${expandedFaq === index ? 'rotate-180' : ''}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {expandedFaq === index && (
                    <div className="px-4 pb-3 text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                      {item.answer}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {activeTab === 'guide' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                按照以下步骤快速开始使用智能校园助手：
              </p>
              {quickStartSteps.map((item) => (
                <div key={item.step} className="flex gap-4">
                  <div className="shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-sm font-bold">
                    {item.step}
                  </div>
                  <div className="flex-1 pt-1">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{item.title}</h4>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'shortcuts' && (
            <div className="space-y-2">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                以下快捷键可帮助您更高效地使用系统：
              </p>
              {shortcuts.map((item, index) => (
                <div key={index} className="flex items-center justify-between px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{item.action}</span>
                  <kbd className="px-2.5 py-1 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 text-xs font-mono text-gray-600 dark:text-gray-400 shadow-sm">
                    {item.keys}
                  </kbd>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
            版本 1.0.0 · 有问题请联系技术支持
          </p>
        </div>
      </div>
    </div>
  )
}

export default HelpCenter
