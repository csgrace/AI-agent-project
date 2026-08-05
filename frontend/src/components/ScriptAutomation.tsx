import { useState, useRef, useCallback, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  streamScriptChat,
  resetScriptAgent,
  fetchScriptChatHistory,
  killScriptExecution,
  fetchScriptSandboxDir,
  updateScriptSandboxDir,
} from '../api'

// ── Types ──────────────────────────────────────────────────────

interface TerminalLine {
  stream: 'stdout' | 'stderr'
  text: string
}

interface TerminalSession {
  executionId: string
  name: string
  lines: TerminalLine[]
  status: 'running' | 'completed' | 'killed'
  returncode?: number
}

interface ChatMessage {
  id: number
  content: string
  isUser: boolean
  isTyping?: boolean
  type?: 'text' | 'thought' | 'tool' | 'terminal'
  toolCall?: { name: string; args: Record<string, unknown> }
  terminalSession?: TerminalSession
}

// ── Component ───────────────────────────────────────────────────

interface ScriptAutomationProps {
  llmAvailable?: boolean;
  onOpenProfile?: () => void;
}

const ScriptAutomation: React.FC<ScriptAutomationProps> = ({ llmAvailable = true }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // ── Sandbox working directory state ──────────────────────────
  const [sandboxDir, setSandboxDir] = useState('')
  const [sandboxExists, setSandboxExists] = useState(false)
  const [showDirInput, setShowDirInput] = useState(false)
  const [newDir, setNewDir] = useState('')
  const [dirError, setDirError] = useState('')
  const [isUpdatingDir, setIsUpdatingDir] = useState(false)

  // Track the current terminal session being built from SSE events
  const terminalRef = useRef<TerminalSession | null>(null)
  // Track the message ID of the terminal panel so we can update it by ID
  // (avoids the fragility of updateLastMessage which depends on array ordering)
  const terminalMsgIdRef = useRef<number | null>(null)

  // ── Restore chat history from backend on mount ─────────────
  useEffect(() => {
    fetchScriptChatHistory()
      .then(data => {
        if (data.ok && data.messages.length > 0) {
          const restored: ChatMessage[] = data.messages.map((msg, i) => ({
            id: i,
            content: msg.content,
            isUser: msg.role === 'user',
            type: 'text' as const,
          }));
          setMessages(restored);
        }
      })
      .catch(() => {});
  }, []);

  // ── Fetch sandbox directory on mount ───────────────────────
  useEffect(() => {
    fetchScriptSandboxDir()
      .then(data => {
        setSandboxDir(data.directory);
        setSandboxExists(data.exists);
      })
      .catch(() => {});
  }, []);

  // ── DEBUG: log every messages state change ──────────────────
  useEffect(() => {
    const snapshot = messages.map(m => ({
      id: m.id,
      type: m.type ?? 'undefined',
      isUser: m.isUser,
      hasTerminalSession: m.terminalSession != null,
      terminalLines: m.terminalSession?.lines?.length ?? 0,
      terminalStatus: m.terminalSession?.status ?? 'N/A',
      contentPreview: typeof m.content === 'string' ? m.content.slice(0, 50) : 'N/A',
    }))
    console.log('[DEBUG messages] count=' + messages.length, snapshot)
  }, [messages])
  // ── END DEBUG ───────────────────────────────────────────────

  const scrollToBottom = () => {
    setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 50)
  }

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages(prev => [...prev, msg])
    scrollToBottom()
  }, [])

  // Update a specific message by its id — used to update the AI placeholder
  // message that was added before streaming events (thought/tool/terminal)
  // may have pushed it out of the last position.
  const updateMessageById = useCallback((id: number, updater: (prev: ChatMessage) => ChatMessage) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === id)
      if (idx === -1) return prev
      const copy = [...prev]
      copy[idx] = updater(copy[idx])
      return copy
    })
  }, [])

  const handleSend = async () => {
    const userText = input.trim()
    if (!userText || isLoading) return

    // Pre-check: no API key configured
    if (!llmAvailable) {
      addMessage({
        id: Date.now(),
        content: '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。',
        isUser: false,
        type: 'text' as const,
      })
      return
    }

    setInput('')
    setIsLoading(true)

    // Add user message
    addMessage({ id: Date.now(), content: userText, isUser: true })

    // Add AI typing placeholder
    const aiMsgId = Date.now() + 1
    addMessage({ id: aiMsgId, content: '', isUser: false, isTyping: true })
    console.log('[DEBUG handleSend] START aiMsgId=' + aiMsgId + ' userMsgId=' + (aiMsgId - 1))

    try {
      for await (const sseEvent of streamScriptChat(userText)) {
        const eventType = sseEvent.event
        let data: Record<string, unknown>
        try {
          data = JSON.parse(sseEvent.data)
        } catch {
          console.log('[DEBUG SSE] skip unparseable event:', sseEvent.event)
          continue
        }

        // ── DEBUG: log every incoming event ──────────────────
        console.log('[DEBUG SSE] event=' + eventType,
          eventType === 'script_execution'
            ? 'stage=' + data.stage + ' id=' + data.execution_id
            : eventType === 'script_output'
              ? 'stream=' + data.stream + ' msg=' + (typeof data.message === 'string' ? (data.message as string).slice(0, 60) : '')
              : eventType === 'final'
                ? 'reply=' + (typeof data.reply === 'string' ? (data.reply as string).slice(0, 60) : '')
                : eventType === 'tool_result'
                  ? 'output_len=' + (typeof data.tool_output === 'string' ? (data.tool_output as string).length : 0)
                  : '',
          'terminalRef=' + (terminalRef.current ? ('present status=' + terminalRef.current.status + ' lines=' + terminalRef.current.lines.length) : 'null'),
          'terminalMsgIdRef=' + terminalMsgIdRef.current
        )
        // ── END DEBUG ────────────────────────────────────────

        if (eventType === 'thought') {
          const thoughtText = data.text as string || ''
          if (thoughtText) {
            addMessage({
              id: Date.now() + Math.random(),
              content: thoughtText,
              isUser: false,
              type: 'thought',
            })
          }
        } else if (eventType === 'tool_call') {
          const toolName = data.tool_name as string || ''
          addMessage({
            id: Date.now() + Math.random(),
            content: '',
            isUser: false,
            type: 'tool',
            toolCall: { name: toolName, args: data.tool_args as Record<string, unknown> || {} },
          })
        } else if (eventType === 'tool_result') {
          const output = data.tool_output as string || ''
          if (output) {
            addMessage({
              id: Date.now() + Math.random(),
              content: `工具返回:\n${output.slice(0, 300)}${output.length > 300 ? '…' : ''}`,
              isUser: false,
              type: 'text',
            })
          }
        } else if (eventType === 'script_execution') {
          const executionId = data.execution_id as string
          const stage = data.stage as string
          const name = data.name as string || ''

          if (stage === 'running') {
            // Create a new terminal session
            terminalRef.current = {
              executionId,
              name,
              lines: [],
              status: 'running',
            }
            const msgId = Date.now() + Math.random()
            terminalMsgIdRef.current = msgId
            console.log('[DEBUG ACTION] CREATE terminal msgId=' + msgId + ' executionId=' + executionId + ' name=' + name)
            addMessage({
              id: msgId,
              content: '',
              isUser: false,
              type: 'terminal',
              terminalSession: { ...terminalRef.current },
            })
          } else if (stage === 'completed' && terminalRef.current && terminalMsgIdRef.current !== null) {
            // Mark terminal as completed
            // ⚠️  CRITICAL: capture a snapshot BEFORE clearing refs, because
            // updateMessageById's callback runs async (React batches state updates)
            // and by then terminalRef.current is already null.
            terminalRef.current.status = 'completed'
            terminalRef.current.returncode = data.returncode as number
            const snapshot = { ...terminalRef.current }
            const msgId = terminalMsgIdRef.current
            console.log('[DEBUG ACTION] COMPLETE terminal msgId=' + msgId + ' lines=' + snapshot.lines.length + ' returncode=' + data.returncode)
            updateMessageById(msgId, msg => ({
              ...msg,
              terminalSession: snapshot,
            }))
            terminalRef.current = null
            terminalMsgIdRef.current = null
          } else if (stage === 'completed') {
            console.log('[DEBUG ACTION] COMPLETE SKIPPED — terminalRef=' + (terminalRef.current ? 'present' : 'null') + ' terminalMsgIdRef=' + terminalMsgIdRef.current)
          }
        } else if (eventType === 'script_output') {
          // Append output line to current terminal session
          if (terminalRef.current && terminalMsgIdRef.current !== null) {
            const stream = (data.stream as 'stdout' | 'stderr') || 'stdout'
            const message = data.message as string || ''
            terminalRef.current.lines.push({ stream, text: message })
            // Capture snapshot for the async React callback
            const snapshot = { ...terminalRef.current }
            const msgId = terminalMsgIdRef.current
            updateMessageById(msgId, msg => ({
              ...msg,
              terminalSession: snapshot,
            }))
          } else {
            console.log('[DEBUG ACTION] script_output SKIPPED — terminalRef=' + (terminalRef.current ? 'present' : 'null') + ' terminalMsgIdRef=' + terminalMsgIdRef.current)
          }
        } else if (eventType === 'tool_progress') {
          const msg = data.message as string || ''
          if (msg) {
            addMessage({
              id: Date.now() + Math.random(),
              content: msg,
              isUser: false,
              type: 'text',
            })
          }
        } else if (eventType === 'final') {
          const reply = data.reply as string || ''

          // Remove the old placeholder (added at the top before streaming),
          // then insert a fresh message at the end so the final reply
          // appears after all intermediate tool/terminal messages.
          const replyMsgId = Date.now() + Math.random()
          console.log('[DEBUG ACTION] FINAL — removing aiMsgId=' + aiMsgId + ' adding replyMsgId=' + replyMsgId)
          setMessages(prev => prev.filter(msg => msg.id !== aiMsgId))
          addMessage({ id: replyMsgId, content: '', isUser: false, isTyping: true })

          // Typewriter effect for final reply
          let currentIndex = 0
          const typingSpeed = 15
          const typeEffect = () => {
            if (currentIndex < reply.length) {
              const currentText = reply.substring(0, currentIndex + 1)
              updateMessageById(replyMsgId, msg =>
                ({ ...msg, content: currentText, isTyping: false, type: 'text' as const })
              )
              currentIndex++
              setTimeout(typeEffect, typingSpeed)
            } else {
              updateMessageById(replyMsgId, msg =>
                ({ ...msg, content: reply, isTyping: false, type: 'text' as const })
              )
            }
          }
          // Only type if there's actual text
          if (reply) {
            typeEffect()
          } else {
            updateMessageById(replyMsgId, msg =>
              ({ ...msg, content: '已完成。', isTyping: false, type: 'text' as const })
            )
          }
        } else if (eventType === 'error') {
          const errorMsg = data.message as string || '处理请求时出错'
          const displayMsg = errorMsg.includes('未配置 API Key')
            ? '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。'
            : `❌ ${errorMsg}`
          setMessages(prev => prev.filter(msg => msg.id !== aiMsgId))
          addMessage({
            id: Date.now() + Math.random(),
            content: displayMsg,
            isUser: false,
            type: 'text' as const,
          })
        }
      }
    } catch (error) {
      console.error('Script Chat API error:', error)
      const errMsg = error instanceof Error ? error.message : ''
      const displayMsg = errMsg.includes('未配置 API Key')
        ? '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。'
        : '抱歉，处理请求时出错了。请确认后端服务是否已启动。'
      setMessages(prev => prev.filter(msg => msg.id !== aiMsgId))
      addMessage({
        id: Date.now() + Math.random(),
        content: displayMsg,
        isUser: false,
        type: 'text' as const,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleKill = async (executionId: string) => {
    try {
      await killScriptExecution(executionId)
      // Update local terminal state to killed, using the stored message ID
      if (terminalMsgIdRef.current !== null) {
        updateMessageById(terminalMsgIdRef.current, msg => {
          if (msg.type === 'terminal' && msg.terminalSession?.executionId === executionId) {
            return {
              ...msg,
              terminalSession: {
                ...msg.terminalSession,
                status: 'killed' as const,
              },
            }
          }
          return msg
        })
      }
    } catch (err) {
      addMessage({
        id: Date.now() + Math.random(),
        content: `⚠️ 终止失败: ${err instanceof Error ? err.message : '未知错误'}`,
        isUser: false,
        type: 'text',
      })
    }
  }

  const handleReset = async () => {
    try {
      await resetScriptAgent()
      setMessages([])
    } catch (err) {
      addMessage({
        id: Date.now() + Math.random(),
        content: `⚠️ 重置失败: ${err instanceof Error ? err.message : '未知错误'}`,
        isUser: false,
        type: 'text',
      })
    }
  }

  const handleChangeDir = async () => {
    const dir = newDir.trim()
    if (!dir) {
      setDirError('请输入目录路径')
      return
    }
    setIsUpdatingDir(true)
    setDirError('')
    try {
      const result = await updateScriptSandboxDir(dir)
      setSandboxDir(result.directory)
      setSandboxExists(true)
      setShowDirInput(false)
      setNewDir('')
      setMessages([])  // 清空对话，因为后端已重建 Agent
      addMessage({
        id: Date.now() + Math.random(),
        content: `✅ 工作目录已切换至：\`${result.directory}\`\n对话已重置。`,
        isUser: false,
        type: 'text',
      })
    } catch (err) {
      setDirError(err instanceof Error ? err.message : '设置目录失败')
    } finally {
      setIsUpdatingDir(false)
    }
  }

  const handleCancelDir = () => {
    setShowDirInput(false)
    setNewDir('')
    setDirError('')
  }

  // ── Render helpers ────────────────────────────────────────────

  const renderTerminal = (session: TerminalSession) => {
    const isActive = session.status === 'running'
    const isKilled = session.status === 'killed'

    return (
      <div className={`rounded-xl overflow-hidden border ${
        isKilled
          ? 'border-red-500/60'
          : isActive
            ? 'border-emerald-500/40'
            : 'border-gray-600/40'
      }`}>
        {/* Title bar */}
        <div className={`flex items-center justify-between px-4 py-2 text-xs font-mono ${
          isKilled
            ? 'bg-red-900/40 text-red-300'
            : isActive
              ? 'bg-emerald-900/30 text-emerald-300'
              : 'bg-gray-800 text-gray-400'
        }`}>
          <div className="flex items-center gap-2">
            {/* Status indicator */}
            <span className={`inline-block w-2 h-2 rounded-full ${
              isKilled
                ? 'bg-red-500'
                : isActive
                  ? 'bg-emerald-400 animate-pulse'
                  : 'bg-gray-500'
            }`} />
            <span className="font-semibold">{session.name}.py</span>
            {isKilled && <span className="text-red-400 font-bold">[已终止]</span>}
            {session.returncode !== undefined && !isKilled && (
              <span className="text-gray-500">退出码 {session.returncode}</span>
            )}
          </div>
          {/* Kill button (only when running) */}
          {isActive && (
            <button
              onClick={() => handleKill(session.executionId)}
              className="flex items-center gap-1 px-2 py-0.5 rounded text-red-300 bg-red-900/30 hover:bg-red-800/50 transition-colors"
              title="终止执行"
            >
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 8 8">
                <rect width="8" height="8" rx="1" />
              </svg>
              <span>终止</span>
            </button>
          )}
        </div>
        {/* Terminal content */}
        <div className="bg-gray-950 p-3 max-h-64 overflow-y-auto font-mono text-sm leading-relaxed">
          {session.lines.length === 0 && isActive && (
            <div className="text-gray-600 italic">等待输出…</div>
          )}
          {session.lines.map((line, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap break-all ${
                line.stream === 'stderr' ? 'text-red-400' : 'text-gray-200'
              }`}
            >
              {line.text}
            </div>
          ))}
          {isActive && session.lines.length > 0 && (
            <span className="inline-block w-2 h-4 bg-emerald-400 animate-pulse ml-0.5 align-middle" />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 h-full min-h-0">
      <div className="h-full flex flex-col bg-white/90 dark:bg-gray-900/80 rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
        {/* Header */}
        <div className="shrink-0 px-5 py-4 border-b border-gray-200/80 dark:border-gray-700/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center">
              <svg className="w-5 h-5 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 000-2.828L4 4m16 12l-4.586-4.586a2 2 0 010-2.828L20 4" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-800 dark:text-white tracking-wide">脚本自动化</h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">让 AI 帮你创建、管理和执行 Python 脚本</p>
            </div>
          </div>
          <button
            onClick={handleReset}
            disabled={isLoading}
            className="px-3 py-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
          >
            重置对话
          </button>
        </div>

        {/* Sandbox directory bar */}
        <div className="shrink-0 px-5 py-2.5 border-b border-gray-200/60 dark:border-gray-700/60 bg-gray-50/60 dark:bg-gray-800/60">
        {!showDirInput ? (
          <div className="flex items-center gap-2 text-xs">
            <svg className="w-4 h-4 shrink-0 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <span className="text-gray-500 dark:text-gray-400 shrink-0">工作目录:</span>
            <code className={`px-1.5 py-0.5 rounded font-mono text-[11px] truncate max-w-[320px] ${
              sandboxExists
                ? 'bg-gray-200/70 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
                : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
            }`}>
              {sandboxDir || '（未设置）'}
            </code>
            {!sandboxExists && sandboxDir && (
              <span className="text-yellow-600 dark:text-yellow-400 text-[10px]">路径不存在</span>
            )}
            <button
              onClick={() => { setShowDirInput(true); setNewDir(sandboxDir); setDirError(''); }}
              className="ml-auto px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-[11px] leading-none"
            >
              更换目录
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 shrink-0 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <input
              type="text"
              value={newDir}
              onChange={e => setNewDir(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !isUpdatingDir) handleChangeDir(); if (e.key === 'Escape') handleCancelDir(); }}
              placeholder="请输入沙箱工作目录的绝对路径"
              disabled={isUpdatingDir}
              className="flex-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 text-xs font-mono text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:ring-2 focus:ring-emerald-500/40 disabled:opacity-50"
              autoFocus
            />
            <button
              onClick={handleChangeDir}
              disabled={isUpdatingDir || !newDir.trim()}
              className="px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white disabled:text-gray-500 transition-colors text-xs font-medium"
            >
              {isUpdatingDir ? '设置中…' : '确定'}
            </button>
            <button
              onClick={handleCancelDir}
              disabled={isUpdatingDir}
              className="px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 transition-colors text-xs"
            >
              取消
            </button>
            {dirError && (
              <span className="text-red-500 dark:text-red-400 text-[11px] ml-1">{dirError}</span>
            )}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
            <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 000-2.828L4 4m16 12l-4.586-4.586a2 2 0 010-2.828L20 4" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold mb-2 text-gray-800 dark:text-white">脚本自动化已就绪</h3>
            <p className="text-center max-w-xs text-sm">告诉我你想做什么，我可以帮你创建和运行脚本</p>
            <div className="mt-4 flex flex-wrap gap-2 justify-center">
              <span className="px-3 py-1 rounded-full text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">🐍 创建脚本</span>
              <span className="px-3 py-1 rounded-full text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">⚡ 执行脚本</span>
              <span className="px-3 py-1 rounded-full text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">📁 管理文件</span>
            </div>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.isUser ? 'justify-end' : 'justify-start'}`}>
            {msg.isUser ? (
              <div className="inline-block max-w-[80%] px-4 py-2.5 rounded-2xl bg-emerald-100/70 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 text-sm break-words">
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            ) : (
              <div className="inline-block max-w-[85%] px-4 py-2.5 rounded-2xl bg-white dark:bg-gray-600 text-gray-800 dark:text-white text-sm shadow-sm">
                {/* AI thought */}
                {msg.type === 'thought' && (
                  <div className="flex items-start gap-2 text-xs text-gray-500 dark:text-gray-400 italic">
                    <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    <span>{msg.content}</span>
                  </div>
                )}

                {/* Tool call */}
                {msg.type === 'tool' && msg.toolCall && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317a1 1 0 011.35-.936l1.94.776a1 1 0 00.768 0l1.94-.776a1 1 0 011.35.936l.132 2.077a1 1 0 00.548.82l1.78.89a1 1 0 01.486 1.486l-1.15 1.734a1 1 0 000 .924l1.15 1.734a1 1 0 01-.486 1.486l-1.78.89a1 1 0 00-.548.82l-.132 2.077a1 1 0 01-1.35.936l-1.94-.776a1 1 0 00-.768 0l-1.94.776a1 1 0 01-1.35-.936l-.132-2.077a1 1 0 00-.548-.82l-1.78-.89a1 1 0 01-.486-1.486l1.15-1.734a1 1 0 000-.924l-1.15-1.734a1 1 0 01.486-1.486l1.78-.89a1 1 0 00.548-.82l.132-2.077z" />
                    </svg>
                    <code className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-xs font-mono">
                      {msg.toolCall.name}
                    </code>
                    <span className="text-gray-400">工具调用</span>
                  </div>
                )}

                {/* Terminal panel */}
                {msg.type === 'terminal' && msg.terminalSession && (
                  renderTerminal(msg.terminalSession)
                )}

                {/* Regular text / AI reply */}
                {(msg.type === 'text' || msg.type === undefined) && (
                  <div className={`prose prose-sm dark:prose-invert max-w-none ${
                    msg.isTyping ? 'border-r-2 border-emerald-400 animate-pulse' : ''
                  }`}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || '')
                          const codeStr = String(children).replace(/\n$/, '')
                          if (match) {
                            return (
                              <SyntaxHighlighter
                                style={tomorrow}
                                language={match[1]}
                                PreTag="div"
                                customStyle={{ fontSize: '0.8rem', borderRadius: '0.5rem' }}
                              >
                                {codeStr}
                              </SyntaxHighlighter>
                            )
                          }
                          return (
                            <code className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-xs" {...props}>
                              {children}
                            </code>
                          )
                        },
                      }}
                    >
                      {msg.content || '思考中…'}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-gray-200/80 dark:border-gray-700/80 p-4">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="告诉 AI 你想做什么..."
            rows={1}
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 text-sm rounded-xl focus:outline-none dark:bg-gray-800 dark:text-white border border-gray-200 dark:border-gray-700 focus:border-emerald-300 focus:ring-2 focus:ring-emerald-200/60 dark:focus:border-emerald-500/60 dark:focus:ring-emerald-500/20 dark:placeholder-gray-400 resize-none disabled:opacity-50"
            style={{ minHeight: '2.5rem', maxHeight: '8rem' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors disabled:opacity-50 bg-emerald-500 text-white hover:bg-emerald-600 disabled:bg-gray-300 dark:disabled:bg-gray-700"
          >
            {isLoading ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            )}
          </button>
        </div>
      </div>
      </div>
    </div>
  )
}

export default ScriptAutomation
