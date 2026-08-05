import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'

const API_BASE = '/api'

interface Question {
  type: string
  question_text: string
  options?: string[]
  correct_answer: string
  difficulty?: string
  explanations?: Record<string, unknown>
}

interface QuizData {
  _type: 'quiz'
  metadata: { file_name: string; question_type: string; total: number; difficulty: string }
  questions: Question[]
}

interface ChatMessage {
  id: number
  content: string
  isUser: boolean
  isTyping?: boolean
  isSystem?: boolean
  toolCalls?: { name: string; args: Record<string, unknown> }[]
  quizData?: QuizData | null
}

const TOOL_STATUS_MAP: Record<string, string> = {
  summarize_document: '正在生成总结',
  generate_questions: '正在生成题目',
  list_supported_formats: '正在获取支持格式',
}

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单', medium: '中等', hard: '困难',
}

const TYPE_LABELS: Record<string, string> = {
  multiple_choice: '单选题', fill_in_blank: '填空题', true_false: '判断题', short_answer: '简答题',
}

// ============================== QuizCard ==============================

interface QuizCardProps {
  question: Question
  index: number
  answer: string
  onAnswer: (val: string) => void
  submitted: boolean
  grading?: { score: number; level: string; feedback: string }
}

function QuizCard({ question, index, answer, onAnswer, submitted, grading }: QuizCardProps) {
  const isMcqOrTf = question.options && question.options.length > 0
  const correct = isMcqOrTf ? submitted && answer.trim().startsWith(question.correct_answer.trim()) : false
  const wrong = isMcqOrTf ? submitted && answer.trim() !== '' && !correct : false

  const borderColor = submitted
    ? correct
      ? 'border-emerald-400'
      : wrong
        ? 'border-red-400'
        : 'border-gray-300 dark:border-gray-600'
    : 'border-gray-200 dark:border-gray-700'

  const renderOptions = () => {
    if (!question.options?.length) return null
    return (
      <div className="space-y-2 mt-3">
        {question.options.map((opt, oi) => {
          const isCorrect = opt.startsWith(question.correct_answer)
          const isSelected = opt.startsWith(answer)
          let cls = 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50'
          let icon = null

          if (submitted && isCorrect) {
            cls = 'border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-900/20'
            icon = <span className="ml-auto text-emerald-500 text-sm font-bold">✓</span>
          } else if (submitted && isSelected && !isCorrect) {
            cls = 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-900/20'
            icon = <span className="ml-auto text-red-500 text-sm font-bold">✗</span>
          } else if (!submitted && isSelected) {
            cls = 'border-emerald-300 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-900/20'
          }

          return (
            <button key={oi} onClick={() => !submitted && onAnswer(opt)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm border transition-all ${cls} ${!submitted ? 'cursor-pointer hover:border-emerald-300 hover:bg-emerald-50/50 dark:hover:border-emerald-600 dark:hover:bg-emerald-900/10' : 'cursor-default'}`}>
              <div className="flex items-center gap-2">
                <span className={`${submitted && isCorrect ? 'text-emerald-700 dark:text-emerald-300 font-medium' : submitted && isSelected && !isCorrect ? 'text-red-700 dark:text-red-300' : 'text-gray-700 dark:text-gray-300'}`}>
                  {opt}
                </span>
                {icon}
              </div>
            </button>
          )
        })}
      </div>
    )
  }

  const renderInput = () => {
    if (question.type === 'fill_in_blank') {
      return (
        <input type="text" value={answer} onChange={e => !submitted && onAnswer(e.target.value)}
          disabled={submitted}
          placeholder="请输入答案..."
          className="mt-3 w-full px-3 py-2 rounded-lg text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none focus:border-emerald-300 focus:ring-2 focus:ring-emerald-200/60 dark:focus:border-emerald-500 dark:placeholder-gray-400 disabled:opacity-60" />
      )
    }
    if (question.type === 'short_answer') {
      return (
        <textarea value={answer} onChange={e => !submitted && onAnswer(e.target.value)}
          disabled={submitted} rows={3}
          placeholder="请输入你的答案..."
          className="mt-3 w-full px-3 py-2 rounded-lg text-sm border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 focus:outline-none focus:border-emerald-300 focus:ring-2 focus:ring-emerald-200/60 dark:focus:border-emerald-500 dark:placeholder-gray-400 resize-none disabled:opacity-60" />
      )
    }
    return null
  }

  return (
    <div className={`rounded-xl border ${borderColor} bg-white dark:bg-gray-800/50 overflow-hidden transition-colors`}>
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
        <span className="font-medium text-sm text-gray-800 dark:text-white">第 {index + 1} 题</span>
        <div className="flex gap-1.5">
          {question.difficulty && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              question.difficulty === 'easy' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                : question.difficulty === 'hard' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                  : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
            }`}>{DIFFICULTY_LABELS[question.difficulty] || question.difficulty}</span>
          )}
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            {TYPE_LABELS[question.type] || question.type}
          </span>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-gray-800 dark:text-white font-medium">{question.question_text}</p>
        {question.options ? renderOptions() : renderInput()}

        {submitted && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 space-y-2">
            {isMcqOrTf ? (
              <>
                <div className={`text-sm font-medium ${correct ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                  {correct ? '✅ 回答正确！' : `❌ 正确答案：${question.correct_answer}`}
                  {wrong && <span className="text-gray-500 font-normal ml-2">你的答案：{answer || '（未作答）'}</span>}
                </div>
                {question.explanations && (
                  <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                    <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {typeof question.explanations === 'object' && question.explanations !== null
                        ? ((question.explanations as Record<string, unknown>).correct as string) || JSON.stringify(question.explanations, null, 2)
                        : String(question.explanations)}
                    </p>
                  </div>
                )}
              </>
            ) : grading ? (
              <>
                <div className={`text-sm font-medium ${grading.level === 'correct' ? 'text-emerald-600' : grading.level === 'partial' ? 'text-yellow-600' : 'text-red-600'}`}>
                  {grading.level === 'correct' ? '✅ 回答正确！' : grading.level === 'partial' ? `⚠️ 部分正确（${grading.score}分）` : `❌ 回答不正确（${grading.score}分）`}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  你的答案：{answer || '（未作答）'}
                </div>
                <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                  <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{grading.feedback}</p>
                </div>
                {question.explanations && (
                  <details className="group">
                    <summary className="text-xs text-gray-400 cursor-pointer hover:text-emerald-600 transition-colors select-none">查看参考答案</summary>
                    <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">正确答案：{question.correct_answer}</p>
                  </details>
                )}
              </>
            ) : (
              <div className="text-sm text-gray-600 dark:text-gray-400">
                你的答案：{answer || '（未作答）'} | 参考答案：{question.correct_answer}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ============================== Main Component ==============================

interface LearningAssistantProps {
  llmAvailable?: boolean;
  onOpenProfile?: () => void;
}

const LearningAssistant: React.FC<LearningAssistantProps> = ({ llmAvailable = true }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [uploadedFile, setUploadedFile] = useState<{ name: string; path: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [processingStatus, setProcessingStatus] = useState<string | null>(null)

  // Quiz state: map of messageId -> { answers, submitted, grading }
  const [quizState, setQuizState] = useState<Record<number, {
    answers: Record<number, string>
    submitted: boolean
    grading: Record<number, { score: number; level: string; feedback: string }>
  }>>({})

  // Typing animation: map of messageId -> currently displayed text length
  const [typingProgress, setTypingProgress] = useState<Record<number, number>>({})
  const typingTimers = useRef<Record<number, ReturnType<typeof setInterval>>>({})

  const chatEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, quizState, typingProgress])

  const startTypingAnimation = (msgId: number, fullText: string) => {
    const speed = 30 // ms per char
    let pos = 0
    if (typingTimers.current[msgId]) clearInterval(typingTimers.current[msgId])
    typingTimers.current[msgId] = setInterval(() => {
      pos += 1
      setTypingProgress(prev => ({ ...prev, [msgId]: Math.min(pos, fullText.length) }))
      if (pos >= fullText.length && typingTimers.current[msgId]) {
        clearInterval(typingTimers.current[msgId])
        delete typingTimers.current[msgId]
      }
    }, speed)
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!['.pptx', '.ppt', '.md'].includes(ext)) {
      setError('不支持的文件格式，请上传 .pptx、.ppt 或 .md 文件')
      return
    }
    setError(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(`${API_BASE}/learning-assistant/upload`, { method: 'POST', body: formData })
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || '上传失败')
      const data = await res.json()
      setUploadedFile({ name: data.file_name, path: data.file_path })
      setMessages(prev => [...prev, { id: Date.now(), content: `已上传文件：**${data.file_name}**`, isUser: false, isSystem: true }])
    } catch (err) {
      setError(err instanceof Error ? err.message : '文件上传失败')
    }
  }

  const sendMessage = async () => {
    const trimmed = inputText.trim()
    if (!trimmed && !uploadedFile) return

    // Pre-check: no API key configured
    if (!llmAvailable) {
      setError('⚠️ 未配置 API Key，请前往个人中心 → API 配置 填入有效的 API 密钥后再试。')
      return
    }

    setError(null)

    const msgText = uploadedFile
      ? `[文件: ${uploadedFile.name}]\n${trimmed || '请总结这个文件'}`
      : trimmed

    const userMsg: ChatMessage = { id: Date.now(), content: trimmed || '请处理这个文件', isUser: true }
    const typingId = Date.now() + 1
    const typingMsg: ChatMessage = { id: typingId, content: '', isUser: false, isTyping: true }
    setMessages(prev => [...prev, userMsg, typingMsg])
    setInputText('')

    let capturedQuiz: QuizData | null = null
    let finalText = ''

    try {
      const res = await fetch(`${API_BASE}/learning-assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msgText, file_context: uploadedFile?.path || null }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        throw new Error(errData?.detail || `请求失败 (${res.status})`)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('无法获取响应流')
      const decoder = new TextDecoder()
      let buffer = ''
      const toolCalls: { name: string; args: Record<string, unknown> }[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6))
              const evt = parsed.event

              if (evt === 'tool_call') {
                toolCalls.push({ name: parsed.tool_name, args: parsed.tool_args || {} })
                const status = TOOL_STATUS_MAP[parsed.tool_name] || `正在${parsed.tool_name}`
                setProcessingStatus(`${status}...`)
              } else if (evt === 'thought') {
                setProcessingStatus('AI 思考中...')
              } else if (evt === 'tool_result') {
                // Check if the tool result contains quiz data
                try {
                  const raw = parsed.tool_output
                  const toolOutput = typeof raw === 'string' ? JSON.parse(raw || '{}') : raw
                  if (toolOutput._type === 'quiz') {
                    if (capturedQuiz) {
                      // Merge questions from multiple generate_questions calls
                      capturedQuiz.questions.push(...toolOutput.questions)
                      capturedQuiz.metadata.total += toolOutput.metadata.total
                    } else {
                      capturedQuiz = toolOutput
                    }
                  }
                } catch { /* not JSON quiz data */ }
                setProcessingStatus('处理完成，正在生成回复...')
              } else if (evt === 'final') {
                finalText = parsed.reply || ''
                setProcessingStatus(null)
              } else if (evt === 'error') {
                finalText = `处理出错：${parsed.message || '未知错误'}`
                setProcessingStatus(null)
              }
            } catch { /* skip */ }
          }
        }
      }

      // Update the typing message with final content
      setMessages(prev => prev.map(msg =>
        msg.id === typingId
          ? {
              ...msg,
              content: finalText || '已完成。',
              isTyping: false,
              toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
              quizData: capturedQuiz,
            }
          : msg
      ))

      if (finalText && !capturedQuiz) {
        startTypingAnimation(typingId, finalText)
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '未知错误'
      const displayMsg = detail.includes('未配置 API Key')
        ? '⚠️ 未配置 API Key，请前往个人中心 → API 配置 填入有效的 API 密钥后再试。'
        : `抱歉，处理请求时出错：${detail}`
      setProcessingStatus(null)
      setMessages(prev => prev.map(msg =>
        msg.id === typingId
          ? { ...msg, content: displayMsg, isTyping: false }
          : msg
      ))
    }
  }

  const resetChat = async () => {
    try { await fetch(`${API_BASE}/learning-assistant/chat/reset`, { method: 'POST' }) } catch { /* ignore */ }
    setMessages([])
    setUploadedFile(null)
    setError(null)
    setQuizState({})
    setTypingProgress({})
    Object.values(typingTimers.current).forEach(t => clearInterval(t))
    typingTimers.current = {}
  }

  const submitQuiz = async (msgId: number, questions: Question[]) => {
    const prev = quizState[msgId] || { answers: {}, submitted: false, grading: {} }
    const grading = { ...prev.grading }

    // Grade short answer questions via AI
    for (let i = 0; i < questions.length; i++) {
      if (questions[i].type === 'short_answer') {
        try {
          const res = await fetch(`${API_BASE}/learning-assistant/grade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              question_text: questions[i].question_text,
              student_answer: prev.answers[i] || '',
              correct_answer: questions[i].correct_answer,
              explanations: questions[i].explanations || null,
            }),
          })
          if (res.ok) {
            grading[i] = await res.json()
          }
        } catch { /* skip grading failure */ }
      }
    }

    setQuizState(p => ({
      ...p,
      [msgId]: { answers: prev.answers, submitted: true, grading },
    }))
  }

  const setQuizAnswer = (msgId: number, qIdx: number, answer: string) => {
    setQuizState(prev => ({
      ...prev,
      [msgId]: { ...prev[msgId], answers: { ...(prev[msgId]?.answers || {}), [qIdx]: answer }, submitted: false },
    }))
  }

  // ===== Render =====

  const renderContent = (msg: ChatMessage) => {
    if (msg.isTyping) {
      return (
        <div className="flex items-center gap-2">
          <span className="inline-flex gap-1">
            <span className="animate-bounce">●</span>
            <span className="animate-bounce" style={{ animationDelay: '0.1s' }}>●</span>
            <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>●</span>
          </span>
          {processingStatus && <span className="text-xs text-gray-500 dark:text-gray-400 animate-pulse">{processingStatus}</span>}
        </div>
      )
    }

    // For quiz messages: show brief text + interactive quiz cards
    if (msg.quizData) {
      const qd = msg.quizData
      const qs = quizState[msg.id] || { answers: {}, submitted: false }

      return (
        <div className="space-y-3">
          <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{msg.content}</div>

          {qd.metadata.total > 0 && (
            <div className="flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>{qd.metadata.total} 道题目</span>
              <span>·</span>
              <span>{TYPE_LABELS[qd.metadata.question_type] || qd.metadata.question_type}</span>
              <span>·</span>
              <span>难度：{DIFFICULTY_LABELS[qd.metadata.difficulty] || qd.metadata.difficulty}</span>
            </div>
          )}

          <div className="space-y-3">
            {qd.questions.map((q, i) => (
              <QuizCard key={i} question={q} index={i}
                answer={qs.answers[i] || ''}
                onAnswer={(val) => setQuizAnswer(msg.id, i, val)}
                submitted={qs.submitted}
                grading={qs.grading?.[i]} />
            ))}
          </div>

          {!qs.submitted && (
            <button onClick={() => submitQuiz(msg.id, qd.questions)}
              disabled={Object.keys(qs.answers).length === 0}
              className="w-full py-2.5 rounded-xl text-sm font-medium bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:from-emerald-600 hover:to-teal-600 shadow-lg shadow-emerald-500/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
              提交答案
            </button>
          )}
        </div>
      )
    }

    // For non-quiz messages: show with typing animation
    const displayText = typingProgress[msg.id] !== undefined
      ? msg.content.slice(0, typingProgress[msg.id])
      : msg.content

    return (
      <div>
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {msg.toolCalls.map((tc, i) => (
              <span key={i} className="px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-50 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
                🔧 {tc.name}
              </span>
            ))}
          </div>
        )}
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const { ref, ...restProps } = props
            return match ? (
              <SyntaxHighlighter style={tomorrow as any} language={match[1]} PreTag="div" {...restProps}>
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code className={className} {...restProps}>{children}</code>
            )
          }
        }}>
          {displayText}
        </ReactMarkdown>
        {(typingProgress[msg.id] !== undefined && typingProgress[msg.id] < msg.content.length) && (
          <span className="inline-flex gap-1 ml-1">
            <span className="animate-pulse">▊</span>
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 h-full min-h-0">
      <div className="h-full flex flex-col bg-white/90 dark:bg-gray-900/80 rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
        {/* Header */}
        <div className="shrink-0 px-5 py-4 border-b border-gray-200/80 dark:border-gray-700/80 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800 dark:text-white tracking-wide">学习助手</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {uploadedFile ? `当前文件：${uploadedFile.name}` : '上传课件，通过对话生成总结或测验题目'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {uploadedFile && (
              <button onClick={() => setUploadedFile(null)}
                className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">清除文件</button>
            )}
            <button onClick={resetChat}
              className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">重置对话</button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
              <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-2 text-gray-800 dark:text-white">学习助手已就绪</h3>
              <p className="text-center max-w-xs text-sm">上传课件文件，然后通过对话生成总结或测验题目。</p>
              <div className="mt-4 flex flex-wrap gap-2 justify-center">
                <span className="px-3 py-1 rounded-full text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">📝 总结文档</span>
                <span className="px-3 py-1 rounded-full text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">❓ 生成题目</span>
                <span className="px-3 py-1 rounded-full text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">📊 思维导图</span>
              </div>
            </div>
          ) : (
            messages.map(msg => (
              <div key={msg.id} className={`flex ${msg.isUser ? 'justify-end' : 'justify-start'}`}>
                {msg.isSystem ? (
                  <div className="inline-block px-4 py-2 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 text-xs max-w-[60%] text-center italic">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : msg.isUser ? (
                  <div className="inline-block px-4 py-2.5 rounded-2xl bg-emerald-100/70 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 text-sm max-w-[80%] break-words text-left backdrop-blur-sm">
                    {msg.content}
                  </div>
                ) : (
                  <div className={msg.quizData
                    ? 'block w-full px-4 py-2.5 rounded-2xl bg-white dark:bg-gray-600 text-gray-800 dark:text-white text-sm shadow-sm'
                    : 'inline-block px-4 py-2.5 rounded-2xl bg-white dark:bg-gray-600 text-gray-800 dark:text-white text-sm max-w-[85%] shadow-sm whitespace-pre-wrap break-words'
                  }>
                    {renderContent(msg)}
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Error */}
        {error && (
          <div className="shrink-0 px-5 py-2 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800">
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Input Area */}
        <div className="shrink-0 border-t border-gray-200/80 dark:border-gray-700/80 p-4">
          {uploadedFile && (
            <div className="mb-2 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="text-xs text-emerald-700 dark:text-emerald-300 font-medium">{uploadedFile.name}</span>
              <button onClick={() => setUploadedFile(null)} className="ml-auto text-emerald-500 hover:text-emerald-700 dark:hover:text-emerald-200">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}
          <div className="relative flex items-center gap-2">
            <button onClick={() => fileInputRef.current?.click()}
              className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 hover:text-emerald-600 dark:hover:text-emerald-300 transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>
            <input ref={fileInputRef} type="file" accept=".pptx,.ppt,.md" onChange={handleFileUpload} className="hidden" />
            <input type="text" value={inputText} onChange={e => setInputText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder={uploadedFile ? '输入指令，如：帮我总结 / 生成5道选择题' : '先上传文件，然后输入指令'}
              className="flex-1 px-4 py-2.5 text-sm rounded-xl focus:outline-none dark:bg-gray-800 dark:text-white border border-gray-200 dark:border-gray-700 focus:border-emerald-300 focus:ring-2 focus:ring-emerald-200/60 dark:focus:border-emerald-500/60 dark:focus:ring-emerald-500/20 dark:placeholder-gray-400" />
            <button onClick={sendMessage} disabled={!inputText.trim() && !uploadedFile}
              className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors disabled:opacity-50 ${
                inputText.trim() || uploadedFile ? 'bg-emerald-500 text-white hover:bg-emerald-600' : 'bg-emerald-100 text-emerald-500'
              }`}>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LearningAssistant
