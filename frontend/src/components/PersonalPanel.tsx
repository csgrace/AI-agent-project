import React, { useEffect, useState } from 'react'
import { setLLMConfig, testLLMConnection, fetchLLMStatus, fetchCredentialStatus, setCredentials } from '../api'
import type { LLMConfigPayload, LLMStatus, CredentialStatus, CredentialConfigPayload } from '../api'

interface PersonalPanelProps {
  open: boolean
  onClose: () => void
  onSave: (profile: { name: string; studentId: string; major: string }) => void
  onLLMSave?: () => void
  onStudentIdChange?: (studentId: string) => void
  initialName?: string
  initialStudentId?: string
  initialMajor?: string
}

const PersonalPanel: React.FC<PersonalPanelProps> = ({
  open,
  onClose,
  onSave,
  onLLMSave,
  onStudentIdChange,
  initialName = '',
  initialStudentId = '',
  initialMajor = '',
}) => {
  // ── Profile state ─────────────────────────────────────────────
  const [name, setName] = useState(initialName)
  const [major, setMajor] = useState(initialMajor)

  // ── LLM config state ─────────────────────────────────────────
  const [provider, setProvider] = useState('dashscope')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [fallbackProvider, setFallbackProvider] = useState('')
  const [fallbackApiKey, setFallbackApiKey] = useState('')
  const [fallbackBaseUrl, setFallbackBaseUrl] = useState('')
  const [testMessage, setTestMessage] = useState('')
  const [testOk, setTestOk] = useState<boolean | null>(null)
  const [testing, setTesting] = useState(false)
  const [savingLLM, setSavingLLM] = useState(false)

  // ── Masked key display ──────────────────────────────────────
  const [maskedKey, setMaskedKey] = useState('')
  const [maskedFallbackKey, setMaskedFallbackKey] = useState('')

  // ── Credential state ────────────────────────────────────────
  const [casUsername, setCasUsername] = useState(initialStudentId)
  const [casPassword, setCasPassword] = useState('')
  const [todoistToken, setTodoistToken] = useState('')
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null)
  const [credentialMessage, setCredentialMessage] = useState('')
  const [credentialOk, setCredentialOk] = useState<boolean | null>(null)
  const [savingCredentials, setSavingCredentials] = useState(false)

  // ── Fetch current config from backend when panel opens ──
  useEffect(() => {
    if (!open) return
    setName(initialName)
    setCasUsername(initialStudentId)
    setMajor(initialMajor)
    // Reset key inputs — user must actively type to change
    setApiKey('')
    setFallbackApiKey('')
    setCasPassword('')
    setTodoistToken('')
    setCredentialMessage('')
    setCredentialOk(null)
    setTestMessage('')
    setTestOk(null)
    // Fetch LLM status from backend
    fetchLLMStatus().then((status: LLMStatus) => {
      setProvider(status.provider || 'dashscope')
      setBaseUrl(status.base_url || '')
      setFallbackProvider(status.fallback_provider || '')
      setFallbackBaseUrl(status.fallback_base_url || '')
      setMaskedKey(status.api_key_masked || '')
      setMaskedFallbackKey(status.fallback_api_key_masked || '')
    }).catch(() => {
      setMaskedKey('')
      setMaskedFallbackKey('')
    })
    // Fetch credential status from backend
    fetchCredentialStatus().then((status: CredentialStatus) => {
      setCredentialStatus(status)
    }).catch(() => {
      setCredentialStatus(null)
    })
  }, [open, initialName, initialStudentId, initialMajor])

  const handleSave = async () => {
    console.debug('[PersonalPanel] handleSave', { name, major })

    // ── Save API config FIRST (before closing the panel) ──────
    const hasApiChanges = apiKey.trim() || fallbackApiKey.trim()
    if (hasApiChanges) {
      try {
        const payload: LLMConfigPayload = {
          provider,
          api_key: apiKey.trim() || undefined,
          base_url: baseUrl.trim() || undefined,
          fallback_provider: fallbackProvider.trim() || undefined,
          fallback_api_key: fallbackApiKey.trim() || undefined,
          fallback_base_url: fallbackBaseUrl.trim() || undefined,
          fallback_enabled: !!fallbackApiKey.trim(),
        }
        await setLLMConfig(payload)
        await onLLMSave?.()
        const st = await fetchLLMStatus()
        setMaskedKey(st.api_key_masked || '')
        setMaskedFallbackKey(st.fallback_api_key_masked || '')
      } catch (e: unknown) {
        const errMsg = e instanceof Error ? e.message : String(e)
        console.error('[PersonalPanel] Failed to save API config on close:', e)
        setTestOk(false)
        setTestMessage(`API 配置保存失败: ${errMsg}`)
        return
      }
    }

    // ── Now save profile and close the panel ──────────────────
    onSave({
      name: name.trim(),
      studentId: casUsername.trim(),
      major: major.trim(),
    })
    onClose()
  }

  const handleCancel = () => {
    console.debug('[PersonalPanel] handleCancel')
    onClose()
  }

  const handleTestConnection = async () => {
    if (!apiKey.trim()) {
      setTestOk(false)
      setTestMessage('请输入 API Key')
      return
    }
    setTesting(true)
    setTestMessage('')
    setTestOk(null)
    try {
      const result = await testLLMConnection({
        provider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim() || undefined,
      })
      setTestOk(result.ok)
      setTestMessage(result.message)
    } catch (e: unknown) {
      setTestOk(false)
      setTestMessage(`请求失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setTesting(false)
    }
  }

  const handleSaveLLM = async () => {
    setSavingLLM(true)
    try {
      const payload: LLMConfigPayload = {
        provider,
        // If apiKey is empty, send "" — backend will keep the existing key
        api_key: apiKey.trim() || undefined,
        base_url: baseUrl.trim() || undefined,
        fallback_provider: fallbackProvider.trim() || undefined,
        fallback_api_key: fallbackApiKey.trim() || undefined,
        fallback_base_url: fallbackBaseUrl.trim() || undefined,
        fallback_enabled: !!fallbackApiKey.trim(),
      }
      await setLLMConfig(payload)
      await onLLMSave?.()
      // Re-fetch status to update masked key display
      const status = await fetchLLMStatus()
      setMaskedKey(status.api_key_masked || '')
      setMaskedFallbackKey(status.fallback_api_key_masked || '')
      setApiKey('')
      setFallbackApiKey('')
      setTestMessage('✅ API 配置已保存并生效')
      setTestOk(true)
    } catch (e: unknown) {
      setTestOk(false)
      setTestMessage(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSavingLLM(false)
    }
  }

  const handleSaveCredentials = async () => {
    setSavingCredentials(true)
    setCredentialMessage('')
    setCredentialOk(null)
    try {
      const payload: CredentialConfigPayload = {}
      if (casUsername.trim()) {
        payload.cas_username = casUsername.trim()
      }
      if (casPassword.trim()) {
        payload.cas_password = casPassword.trim()
      }
      if (todoistToken.trim()) {
        payload.todoist_token = todoistToken.trim()
      }
      await setCredentials(payload)
      // Update studentId in App if it changed
      if (casUsername.trim() && casUsername.trim() !== initialStudentId) {
        onStudentIdChange?.(casUsername.trim())
      }
      // Re-fetch status to update masked display
      const status = await fetchCredentialStatus()
      setCredentialStatus(status)
      setCasPassword('')
      setTodoistToken('')
      setCredentialMessage('✅ 凭据已保存并生效')
      setCredentialOk(true)
    } catch (e: unknown) {
      setCredentialOk(false)
      setCredentialMessage(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSavingCredentials(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <div className="absolute inset-0 z-40 bg-slate-950/55 backdrop-blur-sm" onClick={() => { console.debug('[PersonalPanel] overlay clicked'); onClose(); }} />
      <div
        className="relative z-50 w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[32px] border border-white/40 bg-gradient-to-br from-white/95 via-emerald-50/90 to-teal-50/90 p-8 shadow-2xl dark:border-slate-800 dark:from-slate-950 dark:via-slate-900 dark:to-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.18),_transparent_35%),radial-gradient(circle_at_bottom_left,_rgba(45,212,191,0.14),_transparent_30%)]" />

        {/* ── Profile Section ──────────────────────────────── */}
        <div className="relative flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 shadow-lg shadow-emerald-500/20">
              <svg className="h-8 w-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600 dark:text-emerald-400">Profile</p>
              <h3 className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">个人信息</h3>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">这些信息会同步给学业分析和选课推荐模块。</p>
            </div>
          </div>
        </div>

        <div className="relative mt-8 grid gap-4 md:grid-cols-2">
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">姓名</span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：张三"
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">专业</span>
            <input
              type="text"
              value={major}
              onChange={(event) => setMajor(event.target.value)}
              placeholder="例如：计算机科学与技术"
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
        </div>

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="relative mt-10 mb-6 flex items-center gap-4">
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
          <span className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400 dark:text-slate-500">API 配置</span>
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        </div>

        {/* ── LLM Config Section ──────────────────────────── */}
        <div className="relative grid gap-4 md:grid-cols-2">
          {/* Provider */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">服务商</span>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              <option value="dashscope">DashScope (通义千问)</option>
              <option value="openai">OpenAI</option>
              <option value="custom">自定义兼容</option>
            </select>
          </label>

          {/* API Key */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">API Key</span>
            {maskedKey && (
              <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400 font-mono">
                当前密钥: {maskedKey}
              </p>
            )}
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={maskedKey ? '留空则不修改' : 'sk-...'}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          {/* Base URL */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Base URL（可选）</span>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="留空则使用服务商默认地址"
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          {/* Fallback Provider */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">备用服务商（可选）</span>
            <select
              value={fallbackProvider}
              onChange={(e) => setFallbackProvider(e.target.value)}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              <option value="">无备用</option>
              <option value="dashscope">DashScope (通义千问)</option>
              <option value="openai">OpenAI</option>
              <option value="custom">自定义兼容</option>
            </select>
          </label>

          {/* Fallback API Key */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">备用 API Key</span>
            {maskedFallbackKey && (
              <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400 font-mono">
                当前密钥: {maskedFallbackKey}
              </p>
            )}
            <input
              type="password"
              value={fallbackApiKey}
              onChange={(e) => setFallbackApiKey(e.target.value)}
              placeholder={maskedFallbackKey ? '留空则不修改' : '主服务失败时使用'}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          {/* Fallback Base URL */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">备用 Base URL</span>
            <input
              type="text"
              value={fallbackBaseUrl}
              onChange={(e) => setFallbackBaseUrl(e.target.value)}
              placeholder="留空则使用服务商默认地址"
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
        </div>

        {/* Test result */}
        {testMessage && (
          <div className={`relative mt-4 rounded-2xl p-3 text-sm ${testOk ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300' : 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-300'}`}>
            {testMessage}
          </div>
        )}

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="relative mt-10 mb-6 flex items-center gap-4">
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
          <span className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400 dark:text-slate-500">服务凭据</span>
          <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
        </div>

        {/* ── Credentials Section ─────────────────────────── */}
        <div className="relative grid gap-4 md:grid-cols-2">
          {/* CAS 学号 */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
              CAS 学号
              {credentialStatus?.cas_configured && (
                <span className="ml-2 text-emerald-500 dark:text-emerald-400">✓ 已配置</span>
              )}
            </span>
            <input
              type="text"
              value={casUsername}
              onChange={(e) => setCasUsername(e.target.value)}
              placeholder="例如：12345678"
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          {/* CAS 密码 */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
              CAS 密码
              {credentialStatus?.cas_configured ? (
                <span className="ml-2 text-emerald-500 dark:text-emerald-400">已配置</span>
              ) : (
                <span className="ml-2 text-amber-500 dark:text-amber-400">未配置</span>
              )}
            </span>
            <input
              type="password"
              value={casPassword}
              onChange={(e) => setCasPassword(e.target.value)}
              placeholder={credentialStatus?.cas_configured ? '留空则不修改' : '必填'}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>

          {/* Todoist Access Token — full width */}
          <label className="rounded-3xl border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur md:col-span-2 dark:border-slate-800 dark:bg-slate-900/70">
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
              Todoist Access Token
              {credentialStatus?.todoist_configured ? (
                <span className="ml-2 text-emerald-500 dark:text-emerald-400">
                  ✓ {credentialStatus.todoist_token_masked}
                </span>
              ) : (
                <span className="ml-2 text-amber-500 dark:text-amber-400">未配置</span>
              )}
            </span>
            <input
              type="password"
              value={todoistToken}
              onChange={(e) => setTodoistToken(e.target.value)}
              placeholder={credentialStatus?.todoist_configured ? '留空则不修改' : '输入 Todoist Access Token'}
              className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            />
          </label>
        </div>

        {/* Credential result */}
        {credentialMessage && (
          <div className={`relative mt-4 rounded-2xl p-3 text-sm ${credentialOk ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300' : 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-300'}`}>
            {credentialMessage}
          </div>
        )}

        <div className="relative mt-4 flex items-center justify-start gap-2">
          <button
            type="button"
            onClick={handleSaveCredentials}
            disabled={savingCredentials}
            className="rounded-full bg-gradient-to-r from-violet-500 to-purple-600 px-4 py-2 text-xs font-semibold text-white shadow-lg transition hover:shadow-xl disabled:opacity-50"
          >
            {savingCredentials ? '保存中...' : '保存凭据'}
          </button>
        </div>

        {/* ── Buttons ─────────────────────────────────────── */}
        <div className="relative mt-8 flex items-center justify-between gap-3">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing}
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {testing ? '测试中...' : '测试连接'}
            </button>
            <button
              type="button"
              onClick={handleSaveLLM}
              disabled={savingLLM}
              className="rounded-full bg-gradient-to-r from-amber-500 to-orange-500 px-4 py-2 text-xs font-semibold text-white shadow-lg transition hover:shadow-xl disabled:opacity-50"
            >
              {savingLLM ? '保存中...' : '保存 API 配置'}
            </button>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-full bg-gradient-to-r from-emerald-500 to-teal-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 transition hover:shadow-xl"
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PersonalPanel