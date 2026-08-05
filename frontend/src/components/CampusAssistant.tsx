import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { streamCampusQa } from '../api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

interface QaCitation {
  source_name: string;
  source_path?: string;
  chunk_id?: string;
  text?: string;
  score: number;
  start_char?: number;
  end_char?: number;
  page_count?: number;
  page_number?: number;
}

interface QaResponse {
  answer: string;
  confidence: number;
  answerable: boolean;
  needs_clarification: boolean;
  citations: QaCitation[];
  detected_course_scope?: string | null;
  keywords?: { [source: string]: string[] } | null;
  stream_complete?: boolean;
}

interface CitationSummary {
  source_name: string;
  source_path?: string;
  score: number;
  count: number;
  preview: string;
}

interface CampusMessage {
  id: number;
  content: string;
  isUser: boolean;
  isTyping?: boolean;
  statusText?: string;
}

const summarizeCitations = (citations: QaCitation[]): CitationSummary[] => {
  const grouped = new Map<string, CitationSummary>()

  citations.forEach((citation) => {
    const current = grouped.get(citation.source_name)
    const preview = (citation.text || '').trim().replace(/\s+/g, ' ')

    if (!current) {
      grouped.set(citation.source_name, {
        source_name: citation.source_name,
        source_path: citation.source_path,
        score: citation.score,
        count: 1,
        preview: preview.slice(0, 180),
      })
      return
    }

    current.score = Math.max(current.score, citation.score)
    current.count += 1
    if (!current.preview && preview) {
      current.preview = preview.slice(0, 180)
    }
    if (!current.source_path && citation.source_path) {
      current.source_path = citation.source_path
    }
  })

  return Array.from(grouped.values()).sort((a, b) => b.score - a.score)
}

const formatConfidence = (confidence: number): string => `${Math.round(confidence * 100)}%`

const buildDocumentPreviewApiUrl = (citation: CitationSummary): string => {
  const params = new URLSearchParams()
  if (citation.source_path) {
    params.set('source_path', citation.source_path)
  }
  if (citation.source_name) {
    params.set('source_name', citation.source_name)
  }
  return `${API_BASE_URL}/api/qa/documents/raw?${params.toString()}`
}

const CONFIDENCE_HELP_TEXT =
  '当前版本的置信度是检索稳定度分数，由后端按权重融合"最高相似度、平均相似度、问题与片段的文本相关性"计算得到。它只反映这次检索是否稳，不等于答案正确率。'

const sanitizeAnswerText = (text: string): string => {
  return text
    .replace(/\[[^\]\n]*\.pdf\]/gi, '')
    .replace(/\[(source|citation|来源)[^\]\n]*\]/gi, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

const extractKeywordTags = (text: string | undefined, limit: number = 3): string[] => {
  const normalized = (text || '').toLowerCase()
  if (!normalized) return []

  const tokens = normalized.match(/[a-z]{4,}|[\u4e00-\u9fff]{2,6}/g) || []
  const counts = new Map<string, number>()
  for (const token of tokens) {
    counts.set(token, (counts.get(token) || 0) + 1)
  }

  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([token]) => token)
}

interface CampusAssistantProps {
  llmAvailable?: boolean;
  onOpenProfile?: () => void;
}

const CampusAssistant: React.FC<CampusAssistantProps> = ({ llmAvailable = true }) => {
  const [campusMessages, setCampusMessages] = useState<CampusMessage[]>([]);
  const [campusInputText, setCampusInputText] = useState('');
  const [campusQaResult, setCampusQaResult] = useState<QaResponse | null>(null);
  const [selectedCitationGroup, setSelectedCitationGroup] = useState<CitationSummary | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [pdfPreviewLoading, setPdfPreviewLoading] = useState(false);
  const [pdfPreviewError, setPdfPreviewError] = useState<string | null>(null);
  const [confidenceTooltip, setConfidenceTooltip] = useState<{ x: number; y: number; visible: boolean }>({ x: 0, y: 0, visible: false });
  const campusChatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    campusChatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [campusMessages]);

  const showConfidenceTooltip = (el: HTMLElement | null) => {
    if (!el) return
    const rect = el.getBoundingClientRect()
    setConfidenceTooltip({ x: rect.left + rect.width / 2, y: rect.top, visible: true })
  }
  const hideConfidenceTooltip = () => setConfidenceTooltip(prev => ({ ...prev, visible: false }))

  useEffect(() => {
    if (!confidenceTooltip.visible) return
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node
      const tooltipEl = document.getElementById('confidence-help')
      if (tooltipEl && tooltipEl.contains(target)) return
      hideConfidenceTooltip()
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [confidenceTooltip.visible])

  useEffect(() => {
    if (!selectedCitationGroup) {
      setPdfPreviewUrl(null)
      setPdfPreviewLoading(false)
      setPdfPreviewError(null)
      return
    }

    const previewApiUrl = buildDocumentPreviewApiUrl(selectedCitationGroup)
    let isActive = true
    let objectUrl: string | null = null

    setPdfPreviewLoading(true)
    setPdfPreviewError(null)
    setPdfPreviewUrl(null)

    fetch(previewApiUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`PDF 获取失败：${response.status}`)
        return response.blob()
      })
      .then((blob) => {
        if (!isActive) return
        objectUrl = URL.createObjectURL(blob)
        setPdfPreviewUrl(objectUrl)
        setPdfPreviewLoading(false)
      })
      .catch((error) => {
        if (!isActive) return
        const message = error instanceof Error ? error.message : 'PDF 预览失败'
        setPdfPreviewError(message)
        setPdfPreviewLoading(false)
      })

    return () => {
      isActive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selectedCitationGroup])

  const selectedCitationItems = campusQaResult && selectedCitationGroup
    ? campusQaResult.citations.filter((citation: QaCitation) => citation.source_name === selectedCitationGroup.source_name)
    : []

  const isLLMOnly = Boolean(campusQaResult && (!campusQaResult.citations || campusQaResult.citations.length === 0))

  const modalKeywords = (campusQaResult && selectedCitationGroup && (campusQaResult as any).keywords && (campusQaResult as any).keywords[selectedCitationGroup.source_name])
    ? (campusQaResult as any).keywords[selectedCitationGroup.source_name]
    : (selectedCitationItems.length ? extractKeywordTags(selectedCitationItems.map(c => c.text).join(' '), 5) : [])

  const sendCampusMessage = async () => {
    const trimmedInput = campusInputText.trim()
    if (trimmedInput === '') return

    // Pre-check: no API key configured
    if (!llmAvailable) {
      setCampusMessages((prev) => [...prev, {
        id: Date.now(),
        content: '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。',
        isUser: false,
      }])
      return
    }

    const userMessage: CampusMessage = { id: Date.now(), content: trimmedInput, isUser: true }
    const typingMessage: CampusMessage = { id: Date.now() + 1, content: '', isUser: false, isTyping: true }

    setCampusMessages((prev) => [...prev, userMessage, typingMessage])
    setCampusInputText('')
    setCampusQaResult(null)
    setSelectedCitationGroup(null)

    try {
      let accumulatedContent = ''
      let typingActive = true

      for await (const sseEvent of streamCampusQa(trimmedInput)) {
        switch (sseEvent.event) {
          case 'status':
            setCampusMessages((prev) =>
              prev.map((msg) => msg.id === typingMessage.id ? { ...msg, statusText: sseEvent.data } : msg)
            )
            break

          case 'token':
            if (typingActive) {
              typingActive = false
              setCampusMessages((prev) =>
                prev.map((msg) => msg.id === typingMessage.id ? { ...msg, isTyping: false, statusText: undefined } : msg)
              )
            }
            accumulatedContent += sseEvent.data
            setCampusMessages((prev) =>
              prev.map((msg) => msg.id === typingMessage.id ? { ...msg, content: accumulatedContent } : msg)
            )
            break

          case 'metadata':
            try {
              const payload = JSON.parse(sseEvent.data) as {
                answer?: string
                citations?: QaCitation[]
                confidence?: number
                answerable?: boolean
                needs_clarification?: boolean
                detected_course_scope?: string | null
                keywords?: { [source: string]: string[] } | null
                stream_complete?: boolean
              }
              setCampusQaResult({
                answer: sanitizeAnswerText(payload.answer || accumulatedContent),
                confidence: payload.confidence ?? 0,
                answerable: payload.answerable ?? false,
                needs_clarification: payload.needs_clarification ?? false,
                citations: payload.citations || [],
                detected_course_scope: payload.detected_course_scope ?? null,
                keywords: payload.keywords ?? null,
                stream_complete: payload.stream_complete ?? true,
              })
              setSelectedCitationGroup(null)
            } catch {
              // metadata parse failed, ignore
            }
            break

          case 'error':
            setCampusMessages((prev) =>
              prev.map((msg) => msg.id === typingMessage.id
                ? { ...msg, content: `抱歉，处理您的请求时出错了：${sseEvent.data}`, isTyping: false }
                : msg
              )
            )
            break

          case 'done':
            setCampusMessages((prev) =>
              prev.map((msg) => msg.id === typingMessage.id ? { ...msg, isTyping: false } : msg)
            )
            if (!accumulatedContent) {
              setCampusMessages((prev) =>
                prev.map((msg) => msg.id === typingMessage.id
                  ? { ...msg, content: '未返回有效答案。', isTyping: false }
                  : msg
                )
              )
            }
            break
        }
      }
    } catch (error) {
      console.error('聊天API错误:', error)
      const detail = error instanceof Error ? error.message : '未知错误'
      const displayMsg = detail.includes('未配置 API Key')
        ? '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。'
        : `抱歉，处理您的请求时出错了：${detail}\n请确认后端服务已启动。`
      setCampusQaResult(null)
      setSelectedCitationGroup(null)
      setCampusMessages((prev) =>
        prev.map((msg) => msg.id === typingMessage.id ? { ...msg, content: displayMsg, isTyping: false } : msg)
      )
    }
  }

  return (
    <>
      <div className="p-6 h-full min-h-0">
        <div className="flex flex-row gap-6 h-full min-h-0 overflow-hidden">
          <section className="flex flex-col flex-1 min-w-0 min-h-0">
            <div className="flex flex-col flex-1 min-h-0 bg-white/90 dark:bg-gray-900/80 rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
              <div className="flex-1 min-h-0 overflow-y-auto p-4">
                {campusMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
                    <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mb-4">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <h3 className="text-lg font-semibold mb-2 text-gray-800 dark:text-white">校园知识助手已连接</h3>
                    <p className="text-center max-w-xs">您好！我可以基于南科手册，帮你快速定位信息并形成清晰答案。</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {campusMessages.map((message: CampusMessage) => (
                      <div key={message.id} className={`flex ${message.isUser ? 'justify-end' : 'justify-start'}`}>
                        {message.isUser ? (
                          <div className="inline-block px-4 py-2.5 rounded-2xl bg-emerald-100/70 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 text-sm max-w-[80%] break-words text-left backdrop-blur-sm">
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                          </div>
                        ) : (
                          <div className="inline-block px-4 py-2.5 rounded-2xl bg-white dark:bg-gray-600 text-gray-800 dark:text-white text-sm max-w-[80%] shadow-sm whitespace-pre-wrap break-words">
                            {message.isTyping ? (
                              message.statusText ? (
                                <span className="text-gray-500 dark:text-gray-400 italic">{message.statusText}</span>
                              ) : (
                                <span className="inline-flex gap-1">
                                  <span className="animate-bounce">●</span>
                                  <span className="animate-bounce" style={{ animationDelay: '0.1s' }}>●</span>
                                  <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>●</span>
                                </span>
                              )
                            ) : (
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
                                {message.content}
                              </ReactMarkdown>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="border-t border-gray-200/80 dark:border-gray-700/80 p-4">
                <div className="relative">
                  <textarea rows={2} value={campusInputText} onChange={(e) => setCampusInputText(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && sendCampusMessage()}
                    placeholder="输入校园问题，例如：如何申请校内vpn"
                    className="w-full px-4 py-2.5 text-xs rounded-xl focus:outline-none dark:bg-gray-800 dark:text-white pr-12 resize-none border border-transparent focus:border-green-300 focus:ring-2 focus:ring-green-200/60 dark:focus:border-green-500/60 dark:focus:ring-green-500/20 dark:placeholder-gray-400" />
                  <button onClick={sendCampusMessage} disabled={!campusInputText.trim()}
                    className={`absolute right-3 top-1/2 transform -translate-y-1/2 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-50 ${campusInputText.trim() ? 'bg-green-500 text-white hover:bg-green-600' : 'bg-green-100 text-green-500 hover:bg-green-200'}`}>
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </section>

          <aside className="flex flex-col w-[340px] shrink-0 min-h-0 bg-white/90 dark:bg-gray-900/80 rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
            <div className="border-b border-gray-200/80 dark:border-gray-700/80 p-4">
              <h2 className="text-lg font-semibold tracking-wide text-gray-800 dark:text-white">来源与置信度</h2>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
              {campusQaResult ? (
                isLLMOnly ? (
                  <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900/40">
                    <div className="text-sm font-medium text-gray-700 dark:text-gray-300">通用大模型正在为您回答，未使用 PDF/文档作为直接引用来源。</div>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900/40">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-gray-500 dark:text-gray-400">当前置信度</div>
                          <div className="relative inline-flex">
                            <button type="button" className="cursor-pointer text-2xl font-semibold text-gray-900 dark:text-white hover:text-green-600 dark:hover:text-green-400 transition-colors"
                              onClick={(e) => { e.stopPropagation(); if (confidenceTooltip.visible) { hideConfidenceTooltip() } else { showConfidenceTooltip(e.currentTarget as HTMLElement) } }}>
                              {formatConfidence(campusQaResult.confidence)}
                            </button>
                          </div>
                        </div>
                        <div className={`px-3 py-1 rounded-full text-xs font-medium ${campusQaResult.answerable ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'}`}>
                          {campusQaResult.answerable ? '可直接回答' : '需要补充'}
                        </div>
                      </div>
                      {campusQaResult.detected_course_scope && (
                        <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">课程范围：{campusQaResult.detected_course_scope}</div>
                      )}
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">回答来源列表</h3>
                        <span className="text-xs text-gray-400 dark:text-gray-500">{campusQaResult.citations.length} 条引用</span>
                      </div>
                      <div className="space-y-3">
                        {summarizeCitations(campusQaResult.citations).map((citation: CitationSummary) => (
                          <button key={citation.source_name} type="button" onClick={() => setSelectedCitationGroup(citation)}
                            className="w-full rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-white dark:bg-gray-900 text-left transition-colors hover:border-green-300 hover:bg-green-50/60 dark:hover:border-green-500/60 dark:hover:bg-green-900/10">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="font-medium text-gray-800 dark:text-white truncate">{citation.source_name}</div>
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{citation.count} 个相关片段</div>
                              </div>
                              <div className="shrink-0 px-2 py-1 rounded-full text-xs font-semibold bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300">
                                {formatConfidence(citation.score)}
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )
              ) : (
                <div className="flex flex-col items-center justify-center h-full min-h-[240px] text-gray-500 dark:text-gray-400 text-center px-4">
                  <div className="w-14 h-14 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold mb-2 text-gray-800 dark:text-white">暂无引用</h3>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>

      {selectedCitationGroup && campusQaResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-full max-w-6xl overflow-hidden rounded-2xl bg-white dark:bg-gray-900 shadow-2xl">
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-start justify-between gap-4 border-b border-gray-200 dark:border-gray-800 p-4">
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white truncate">{selectedCitationGroup.source_name}</h3>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">相关片段 {selectedCitationGroup.count} 个 · 最高相关度 {formatConfidence(selectedCitationGroup.score)}</p>
                </div>
                <button type="button" onClick={() => setSelectedCitationGroup(null)} className="rounded-full p-3 text-2xl leading-none text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white" aria-label="关闭预览">×</button>
              </div>
              <div className="flex-1 min-h-0 bg-gray-100 dark:bg-black p-4 overflow-auto">
                {pdfPreviewLoading ? (
                  <div className="flex h-full items-center justify-center p-8 text-sm text-gray-500 dark:text-gray-400">正在加载预览...</div>
                ) : pdfPreviewError ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center text-sm text-gray-500 dark:text-gray-400">
                    <div>{pdfPreviewError}</div>
                    <div className="max-w-md leading-6">如果预览不可用，您可以下载原始文件或查看下方片段文本。</div>
                  </div>
                ) : pdfPreviewUrl ? (
                  <iframe title={selectedCitationGroup.source_name} src={pdfPreviewUrl} className="h-[70vh] w-full rounded-md mb-4" />
                ) : (
                  <div className="flex h-36 items-center justify-center p-8 text-sm text-gray-500 dark:text-gray-400 rounded-md border border-dashed border-gray-200 dark:border-gray-800 mb-4">当前没有可预览的内容，下面显示片段文本。</div>
                )}
              </div>
            </div>
            <aside className="w-64 border-l border-transparent p-4 bg-gradient-to-b from-white/60 to-slate-50 dark:from-gray-900/60 dark:to-slate-900 rounded-tr-2xl rounded-br-2xl">
              <div className="mb-4 bg-white/80 dark:bg-gray-800/70 p-3 rounded-lg shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 flex items-center justify-center bg-green-50 dark:bg-green-900/30 rounded-lg">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-600 dark:text-green-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-sm text-slate-500">置信度</div>
                    <div className="text-xl font-semibold mt-1">{formatConfidence(selectedCitationGroup?.score ?? 0)}</div>
                  </div>
                </div>
                <div className="text-xs text-slate-400 mt-2">
                  <button className="text-xs text-slate-400 underline-offset-2 hover:underline"
                    onClick={(e) => { e.stopPropagation(); if (confidenceTooltip.visible) { hideConfidenceTooltip() } else { showConfidenceTooltip(e.currentTarget as HTMLElement) } }}>
                    检索稳定度，非答案准确率
                  </button>
                </div>
              </div>
              <div className="mt-3">
                <div className="text-sm text-slate-500 mb-2">关键词</div>
                <div className="flex flex-wrap gap-2">
                  {modalKeywords.length ? modalKeywords.map((k: string, i: number) => (
                    <span key={i} className="px-3 py-1 rounded-full text-sm font-medium bg-gradient-to-r from-emerald-200 to-emerald-50 dark:from-emerald-800 dark:to-emerald-700 text-emerald-900 dark:text-emerald-100 shadow-sm hover:scale-105 transform transition">{k}</span>
                  )) : (
                    <div className="text-sm text-slate-400">无</div>
                  )}
                </div>
              </div>
            </aside>
          </div>
        </div>
      )}

      {confidenceTooltip.visible && (
        <div id="confidence-help" role="tooltip"
          className="fixed z-50 w-80 -translate-x-1/2 rounded-2xl bg-gradient-to-br from-white to-emerald-50 dark:from-gray-900 dark:to-emerald-900/20 p-3 text-sm leading-6 text-gray-700 dark:text-gray-300 shadow-2xl"
          style={{ left: confidenceTooltip.x, top: confidenceTooltip.y - 12 }}>
          <div className="flex items-start gap-3">
            <div className="flex-none w-9 h-9 rounded-lg bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-emerald-600 dark:text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 18.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13z" />
              </svg>
            </div>
            <div className="flex-1">
              <div className="font-medium text-sm text-gray-900 dark:text-gray-100">关于置信度</div>
              <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{CONFIDENCE_HELP_TEXT}</div>
              <div className="mt-2 rounded-md bg-white/60 dark:bg-gray-800/60 px-3 py-2 font-mono text-xs text-gray-600 dark:text-gray-400 border border-gray-100 dark:border-gray-800">后端按权重计算：0.45 × 最高相似度 + 0.20 × 平均相似度 + 0.25 × 片段相关性顶部 + 0.10 × 平均相关性</div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default CampusAssistant;