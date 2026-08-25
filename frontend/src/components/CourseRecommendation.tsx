import { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchCourseSchedule,
  fetchCourseTerms,
  fetchRecommendationExplanation,
  streamCoursePlan,
  type CourseMeeting,
  type RecommendationPlan,
  type TermInfo,
} from '../api'

interface CourseRecommendationProps {
  initialMajor?: string
  initialGrade?: string
}

interface RecommendationExplanation {
  based_on: string[];      // 依据（如：培养方案要求、已修读情况、时间冲突检查）
  matched_courses: Array<{
    course_code?: string | null;
    course_name: string;
    credits?: number | null;
    status?: string | null;
    source?: string | null;
    reason: string;        // 推荐理由
  }>;
  requirement_summary: string;  // 培养方案完成情况总结
}

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const academicTermLabels = ['大一上', '大一下', '大二上', '大二下', '大三上', '大三下', '大四上', '大四下']

const slotTimes = [
  { slot: 1, time: '08:00-08:50' },
  { slot: 2, time: '09:00-09:50' },
  { slot: 3, time: '10:20-11:10' },
  { slot: 4, time: '11:20-12:10' },
  { slot: 5, time: '14:00-14:50' },
  { slot: 6, time: '15:00-15:50' },
  { slot: 7, time: '16:20-17:10' },
  { slot: 8, time: '17:20-18:10' },
  { slot: 9, time: '19:00-19:50' },
  { slot: 10, time: '20:00-20:50' },
  { slot: 11, time: '21:00-21:50' },
]

const statusLabel: Record<string, string> = {
  completed: '已完成',
  current: '当前学期',
  future: '未修读',
}

type AcademicTermOption = {
  termId: string
  label: string
  sourceLabel: string
}

const colorFromText = (input: string) => {
  let hash = 0
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i)
    hash |= 0
  }

  const hue = Math.abs(hash) % 360
  return {
    backgroundColor: `hsla(${hue}, 70%, 78%, 0.25)`,
    borderColor: `hsla(${hue}, 70%, 40%, 0.55)`,
    color: `hsl(${hue}, 60%, 22%)`,
  }
}

const baseCourseName = (name: string) => name.split('（')[0].split('(')[0].trim()

const simpleTermLabel = (terms: TermInfo[], termId: string) => {
  if (!terms || terms.length === 0) return ''

  const sorted = [...terms].sort((a, b) => (a.year - b.year) || (a.semester - b.semester))
  const index = sorted.findIndex((term) => term.term_id === termId)
  const position = index >= 0 ? index : 0
  const gradeNumber = Math.floor(position / 2) + 1
  const grade = ['一', '二', '三', '四'][gradeNumber - 1] || gradeNumber.toString()
  const semester = position % 2 === 0 ? '上' : '下'
  return `大${grade}${semester}`
}

const buildAcademicTermOptions = (terms: TermInfo[]): AcademicTermOption[] => {
  const sorted = [...terms].sort((a, b) => (a.year - b.year) || (a.semester - b.semester))

  // 辅助：从 term 中提取年份（优先 term_id，其次 label，最后 year 字段）
  const getYear = (term: TermInfo): string => {
    const idMatch = term.term_id.match(/\d{4}/)
    if (idMatch) return idMatch[0]
    const labelMatch = term.label.match(/\d{4}/)
    if (labelMatch) return labelMatch[0]
    return term.year.toString()
  }

  // 辅助：从 term 中提取季节字符（优先 term_id，其次 label）
  const getSeasonChar = (term: TermInfo): string => {
    if (term.term_id.includes('春')) return '春'
    if (term.term_id.includes('秋')) return '秋'
    if (term.label.includes('春季')) return '春'
    if (term.label.includes('秋季')) return '秋'
    return '?'
  }

  // 找到当前学期索引，只返回当前及之后的学期
  const currentIndex = sorted.findIndex((term) => term.status === 'current')

  // 如果没有找到当前学期，基于最新已知学期继续向后补齐，避免下拉为空
  if (currentIndex === -1) {
    if (sorted.length === 0) return []

    const startIndex = sorted.length - 1
    const futureTerms = [sorted[startIndex]]

    while (futureTerms.length < 8) {
      const last = futureTerms[futureTerms.length - 1]
      if (!last) break

      let nextYear = last.year
      let nextSemester = last.semester + 1
      if (nextSemester > 2) {
        nextSemester = 1
        nextYear += 1
      }

      futureTerms.push({
        term_id: `${nextYear}-${nextSemester === 1 ? '春' : '秋'}`,
        year: nextYear,
        semester: nextSemester,
        label: `${nextYear}年${nextSemester === 1 ? '春季' : '秋季'}学期`,
        status: 'future',
      } as TermInfo)
    }

    return futureTerms.map((term, index) => ({
      termId: term.term_id,
      label: academicTermLabels[startIndex + index] || `第${startIndex + index + 1}学期`,
      sourceLabel: `${getYear(term)}${getSeasonChar(term)}`,
    }))
  }

  // 生成到大四下学期（共8个学期，从当前开始）
  const remaining = 8 - currentIndex
  const futureTerms = sorted.slice(currentIndex, currentIndex + remaining)

  // 如果不够，自动生成学期
  while (futureTerms.length < remaining) {
    const last = futureTerms[futureTerms.length - 1]
    if (!last) break
    let nextYear = last.year
    let nextSemester = last.semester + 1
    if (nextSemester > 2) {
      nextSemester = 1
      nextYear += 1
    }
    futureTerms.push({
      term_id: `${nextYear}-${nextSemester === 1 ? '春' : '秋'}`,
      year: nextYear,
      semester: nextSemester,
      label: `${nextYear}年${nextSemester === 1 ? '春季' : '秋季'}学期`,
      status: 'future',
    } as TermInfo)
  }

  return futureTerms.map((term, idx) => ({
    termId: term.term_id,
    label: academicTermLabels[currentIndex + idx] || `第${currentIndex + idx + 1}学期`,
    sourceLabel: `${getYear(term)}${getSeasonChar(term)}`,
  }))
}

const CourseRecommendation: React.FC<CourseRecommendationProps> = ({ initialMajor = '', initialGrade = '' }) => {
  const [terms, setTerms] = useState<TermInfo[]>([])
  const [selectedTerm, setSelectedTerm] = useState<string>('')
  const [scheduleMeetings, setScheduleMeetings] = useState<CourseMeeting[]>([])
  const [plan, setPlan] = useState<RecommendationPlan | null>(null)
  const [loading, setLoading] = useState(false)
const [planning, setPlanning] = useState(false)
const [, setPlanProgress] = useState<string>('')
const [planSteps, setPlanSteps] = useState<string[]>([])
const [agentStep, setAgentStep] = useState<{ current: number; label: string }>({ current: 0, label: '' })
const [message, setMessage] = useState('')
const [error, setError] = useState('')
  const [termMenuOpen, setTermMenuOpen] = useState(false)
  const [recommendationModalOpen, setRecommendationModalOpen] = useState(false)
  const [recommendationTermId, setRecommendationTermId] = useState('')
  const [recommendationNote, setRecommendationNote] = useState('')
  const [recommendationExplanation, setRecommendationExplanation] = useState<RecommendationExplanation | null>(null)
  const [showExplanation, setShowExplanation] = useState(false)
  const [recommendationError, setRecommendationError] = useState('')
  const [academicAnalysisOpen, setAcademicAnalysisOpen] = useState(false)
  const [academicData, setAcademicData] = useState<any>(null)
  const [loadingAcademic, setLoadingAcademic] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [modalTitle, setModalTitle] = useState('')
  const [modalCourses, setModalCourses] = useState<string[]>([])
  const [avoidSlots, setAvoidSlots] = useState<{ weekday: number; start: number; end: number }[]>([])
  const [newAvoidWeekday, setNewAvoidWeekday] = useState(1)
  const [newAvoidStart, setNewAvoidStart] = useState(1)
  const [newAvoidEnd, setNewAvoidEnd] = useState(2)

  const weekdayLabels = ['', '周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const slotNumbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

  const addAvoidSlot = () => {
    setAvoidSlots((prev) => [...prev, { weekday: newAvoidWeekday, start: newAvoidStart, end: newAvoidEnd }])
  }

  const removeAvoidSlot = (index: number) => {
    setAvoidSlots((prev) => prev.filter((_, i) => i !== index))
  }

  const avoidTimeText = avoidSlots
    .map((slot) => `${weekdayLabels[slot.weekday]}第${slot.start}-${slot.end}节`)
    .join('；')
  const avoidTimeSlots = avoidTimeText
  

  const termMenuRef = useRef<HTMLDivElement | null>(null)

  const [minCredits, setMinCredits] = useState(0)
  const [maxCredits, setMaxCredits] = useState(18)

  const currentMajor = initialMajor || localStorage.getItem('userMajor') || ''
  const currentGrade = initialGrade || localStorage.getItem('userGrade') || '大三'

  useEffect(() => {
    const cached = localStorage.getItem('academicStatus')
    if (!cached) return
    try {
      setAcademicData(JSON.parse(cached))
    } catch {
      // ignore cache parse errors
    }
  }, [])

  // If the user's major changes, invalidate cached academic data so we re-fetch
  useEffect(() => {
    if (!currentMajor) return
    const cached = localStorage.getItem('academicStatus')
    if (!cached) return
    try {
      const parsed = JSON.parse(cached)
      if (parsed && parsed.major && parsed.major !== currentMajor) {
        localStorage.removeItem('academicStatus')
        setAcademicData(null)
      }
    } catch {
      // ignore parse errors
    }
  }, [currentMajor])

  useEffect(() => {
    let active = true

    const loadTerms = async () => {
      setLoading(true)
      setError('')
      setMessage('')

      try {
        const payload = await fetchCourseTerms()
        if (!active) return

        const loadedTerms = payload.terms || []
        setTerms(loadedTerms)
        setMessage(payload.message || '')

        if (loadedTerms.length > 0) {
          const current = loadedTerms.find((term) => term.status === 'current')
          setSelectedTerm(current?.term_id || loadedTerms[0].term_id)
        }
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : '学期加载失败')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadTerms()

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedTerm) return

    const loadSchedule = async () => {
      setLoading(true)
      setError('')
      setPlan(null)

      try {
        const schedule = await fetchCourseSchedule(selectedTerm)
        setScheduleMeetings(schedule.meetings || [])
      } catch (err) {
        setError(err instanceof Error ? err.message : '课表加载失败')
        setScheduleMeetings([])
      } finally {
        setLoading(false)
      }
    }

    loadSchedule()
  }, [selectedTerm])

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!termMenuRef.current) return
      if (!termMenuRef.current.contains(event.target as Node)) {
        setTermMenuOpen(false)
      }
    }

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setTermMenuOpen(false)
        setRecommendationModalOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)

    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [])

  const selectedTermInfo = useMemo(
    () => terms.find((term) => term.term_id === selectedTerm) || null,
    [terms, selectedTerm]
  )

  const academicTermOptions = useMemo(() => buildAcademicTermOptions(terms), [terms])

  const recommendationTermOptions = useMemo(
    () => academicTermOptions.filter((option) => {
      const term = terms.find((item) => item.term_id === option.termId)
      return !term || term.status === 'current' || term.status === 'future'
    }),
    [academicTermOptions, terms]
  )

  const allMeetings = plan ? plan.meetings : scheduleMeetings
  const meetings = allMeetings.filter((m) => m.day_of_week && m.start_slot && m.end_slot)
  const missingScheduleMeetings = allMeetings.filter((m) => !m.day_of_week || !m.start_slot || !m.end_slot)

  const openRecommendationModal = () => {
    setRecommendationError('')

    const defaultTermId =
      recommendationTermOptions.find((option) => option.termId === selectedTerm)?.termId ||
      recommendationTermOptions[0]?.termId ||
      selectedTerm

    setRecommendationTermId(defaultTermId)
    setRecommendationModalOpen(true)
  }

  const openAcademicAnalysis = async (forceRefresh = false) => {
    setAcademicAnalysisOpen(true)
    if (!forceRefresh && academicData) return
    setLoadingAcademic(true)
    try {
      const queryMajor = currentMajor.trim()
      if (forceRefresh) {
        await fetch('/api/course-recommendation/refresh-completed', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ major: queryMajor }),
        })
      }
      const res = await fetch(
        `/api/course-recommendation/academic-status?major=${encodeURIComponent(queryMajor)}&refresh=${forceRefresh ? 'true' : 'false'}`
      )
      const data = await res.json()
      // If some categories have unknown requirements, try fetching graduation requirements
      try {
        const hasUnknown = (data.categories || []).some((c: any) => c.required === '?' || c.required == null)
        if (hasUnknown && queryMajor) {
          const reqRes = await fetch(`/api/course-recommendation/graduation-requirements?major=${encodeURIComponent(queryMajor)}`)
          if (reqRes.ok) {
            const reqJson = await reqRes.json()
            const requirements = reqJson.requirements || {}
            // Update categories with parsed requirements
            const updatedCategories = (data.categories || []).map((c: any) => {
              const reqVal = requirements[c.category]
              const numeric = typeof reqVal === 'number' ? reqVal : (typeof reqVal === 'string' && reqVal.trim() !== '' && !isNaN(Number(reqVal)) ? Number(reqVal) : null)
              const required = numeric != null ? numeric : c.required
              const remaining = numeric != null ? Math.max(0, numeric - (Number(c.completed) || 0)) : (c.remaining ?? '?')
              return { ...c, required, remaining }
            })
            data.categories = updatedCategories
            // If total required was unknown, compute from numeric requirements
            const numericReqs = Object.values(requirements).filter((v: any) => typeof v === 'number')
            if ((!data.required_credits || data.required_credits === '?') && numericReqs.length > 0) {
              data.required_credits = numericReqs.reduce((a: number, b: number) => a + b, 0)
            }
          }
        }
      } catch (e) {
        // ignore graduation requirements fetch errors
      }

      setAcademicData(data)
      localStorage.setItem('academicStatus', JSON.stringify(data))
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingAcademic(false)
    }
  }

  
  const handleGenerateRecommendation = async () => {
    const targetTermId = recommendationTermId || selectedTerm
    if (!targetTermId) {
      setRecommendationError('请先选择推荐学期')
      return
    }
    if (minCredits < 0 || maxCredits < 0) {
      setRecommendationError('学分上下限必须为非负数')
      return
    }
    if (minCredits > 20) {
      setRecommendationError('建议最低学分不能超过20')
      return
    }
    if (maxCredits > 25) {
      setRecommendationError('建议最高学分不能超过25')
      return
    }
    if (minCredits > maxCredits) {
      setRecommendationError('建议最低学分不能大于建议最高学分')
      return
    }

    setPlanning(true)
    setRecommendationError('')
    setError('')
    setRecommendationExplanation(null)
    setShowExplanation(false)
setPlanProgress('')
setPlanSteps([])
setAgentStep({ current: 0, label: '' })

    try {
      const stream = streamCoursePlan({
        term_id: targetTermId,
        major: currentMajor.trim() || undefined,
        interests: [recommendationNote.trim(), `年级:${currentGrade}`].filter(Boolean),
        career_goal: undefined,
        recommendation_note: recommendationNote.trim() || undefined,
        avoid_time_slots: avoidTimeSlots || undefined,
        min_credits: minCredits,
        max_credits: maxCredits,
        use_llm: true,
      })

      let finalPlan: RecommendationPlan | null = null

      for await (const evt of stream) {
        switch (evt.event) {
          case 'status': {
            try {
              const data = JSON.parse(evt.data) as { message?: string }
              if (data.message) {
                setPlanProgress(data.message)
                setPlanSteps(prev => [...prev.slice(-19), data.message!])
                // Parse step number from "第 N 步:" format
                const stepMatch = data.message.match(/^第\s*(\d+)\s*步[:：]\s*(.+)/)
                if (stepMatch) {
                  setAgentStep({
                    current: parseInt(stepMatch[1], 10),
                    label: stepMatch[2].trim()
                  })
                }
              }
            } catch { /* ignore */ }
            break
          }
          case 'thought': {
            try {
              const data = JSON.parse(evt.data) as { text?: string }
              if (data.text) {
                setPlanProgress(`🤔 ${data.text}`)
              }
            } catch { /* ignore */ }
            break
          }
          case 'tool_progress': {
            try {
              const data = JSON.parse(evt.data) as { label?: string; tool?: string; summary?: string }
              if (data.summary) {
                setPlanProgress(`   → ${data.summary}`)
              } else if (data.label) {
                setPlanProgress(`🔧 ${data.label}`)
              }
            } catch { /* ignore */ }
            break
          }
          case 'done': {
            try {
              const data = JSON.parse(evt.data) as { status?: string; plan?: RecommendationPlan }
              if (data.status && data.status !== 'success') {
                throw new Error('选课方案未通过全部约束校验')
              }
              if (data.plan) {
                finalPlan = data.plan as RecommendationPlan
              }
            } catch { /* ignore */ }
            break
          }
          case 'error': {
            try {
              const data = JSON.parse(evt.data) as { detail?: string }
              setRecommendationError(data.detail || '生成失败')
            } catch { /* ignore */ }
            break
          }
        }
      }

      if (!finalPlan) {
        throw new Error('未能获取到推荐结果')
      }

      console.log('推荐返回数据:', finalPlan)
      console.log('meetings数量:', finalPlan.meetings?.length)
      console.log('第一个meeting:', finalPlan.meetings?.[0])

      setPlan(finalPlan)
      
      // 获取推荐解释
      try {
        const explanationCourses = [
          ...(finalPlan.recommended_courses || []),
          ...(finalPlan.postponed_courses || []),
        ].filter((course, index, self) => {
          const courseKey = `${course.course_id || ''}::${course.course_name}`
          return index === self.findIndex((item) => `${item.course_id || ''}::${item.course_name}` === courseKey)
        })

        const explanation = await fetchRecommendationExplanation({
          term_id: targetTermId,
          recommended_courses: explanationCourses,
          postponed_courses: finalPlan.postponed_courses?.map((course) => ({
            course_id: course.course_id,
            course_name: course.course_name,
            credits: course.credits,
            status: course.status,
            source: course.source,
          })),
          user_major: currentMajor.trim() || undefined,
          user_note: recommendationNote.trim() || undefined,
        })

        setRecommendationExplanation(explanation)
      } catch (e) {
        // ignore explanation errors
      }

      setMessage(`已生成 ${finalPlan.term.label} 的课表推荐。`)
      setRecommendationModalOpen(false)
    } catch (err) {
      setRecommendationError(err instanceof Error ? err.message : '课表推荐生成失败')
    } finally {
      setPlanning(false)
    }
  }

  return (
    <div className="cr-root relative h-full w-full overflow-hidden">
      <div
        className="absolute inset-0 dark:opacity-0"
        style={{
          background:
            'radial-gradient(circle at top, #eef2ff 0%, transparent 55%), radial-gradient(circle at bottom, #d1fae5 0%, transparent 50%)',
        }}
      />
      <div className="cr-orb cr-orb--one dark:opacity-0" />
      <div className="cr-orb cr-orb--two dark:opacity-0" />

      <div className="relative z-10 flex h-full flex-col gap-6 px-6 py-6">
        <div className="flex-1 min-h-0">
          <section className="flex h-full min-h-0 flex-col gap-4 rounded-[28px] border border-white bg-white/80 p-5 shadow-xl overflow-y-auto dark:border-slate-800 dark:bg-slate-950/80">
            <div className="relative z-20 flex items-center justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">周课表视图</h3>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">课程以节次呈现，支持已修读与未来规划</p>
              </div>

              <div className="flex items-center gap-3">
                <div
                  ref={termMenuRef}
                  className="relative z-20 flex items-center gap-3 rounded-full border border-gray-100 bg-white/90 px-3 py-1 shadow dark:border-slate-700 dark:bg-slate-900/90"
                >
                  <span className="text-xs text-gray-500 dark:text-gray-300">学期</span>
                  <button
                    type="button"
                    onClick={() => setTermMenuOpen((prev) => !prev)}
                    className="inline-flex min-w-[160px] items-center gap-2 rounded-full border border-transparent bg-white px-3 py-1 text-sm font-semibold text-gray-800 hover:bg-gray-50 focus:outline-none dark:bg-slate-900 dark:text-gray-100 dark:hover:bg-slate-800"
                    aria-expanded={termMenuOpen}
                    aria-haspopup="listbox"
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold">
                        {plan 
                          ? (academicTermOptions.find(opt => opt.termId === plan.term.term_id)?.label || plan.term.label)
                          : (simpleTermLabel(terms, selectedTerm) || selectedTermInfo?.label || '请选择学期')
                        }
                      </span>
                      {plan && <span className="rounded-full border border-blue-200 bg-blue-100 px-2 py-0.5 text-xs text-blue-700">待规划</span>}
                      {!plan && selectedTermInfo && (
                        <span className={`rounded-full border px-2 py-0.5 text-xs ${
                          selectedTermInfo.status === 'current' 
                            ? 'border-yellow-400 bg-yellow-100 text-yellow-700' 
                            : 'border-emerald-200 bg-emerald-100 text-emerald-700'
                        }`}>
                          {statusLabel[selectedTermInfo.status]}
                        </span>
                      )}
                    </div>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="text-gray-500"
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>

                  {termMenuOpen && (
                    <div
                      role="listbox"
                      className="absolute right-0 top-full mt-2 max-h-72 w-56 overflow-auto rounded-2xl border border-gray-100 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-900"
                    >
                      {terms.map((term) => (
                        <button
                          key={term.term_id}
                          type="button"
                          role="option"
                          onClick={() => {
                            setSelectedTerm(term.term_id)
                            setTermMenuOpen(false)
                          }}
                          className={`w-full px-4 py-2 text-left text-sm transition ${
                            term.term_id === selectedTerm
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200'
                              : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-slate-800'
                          }`}
                        >
                          {simpleTermLabel(terms, term.term_id) || term.label}
                        </button>
                      ))}
                    </div>
                  )}

                </div>

                <button
                  type="button"
                  onClick={openRecommendationModal}
                  disabled={loading || planning || terms.length === 0}
                  className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  课表推荐
                </button>
                <button
                  type="button"
                  onClick={() => openAcademicAnalysis(false)}
                  className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-emerald-700"
                >
                  学业情况
                </button>
                {/* 课程规划已移除 */}
              </div>
            </div>

            {recommendationExplanation && (
              <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-semibold text-blue-800 dark:text-blue-300">📋 推荐依据</h4>
                    <div className="flex flex-wrap gap-2">
                      {recommendationExplanation.based_on.map((item, idx) => (
                        <span key={idx} className="rounded-full bg-blue-200 px-2 py-0.5 text-xs text-blue-800">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button onClick={() => setShowExplanation(!showExplanation)} className="text-xs text-blue-600">
                    {showExplanation ? '收起' : '展开'}
                  </button>
                </div>

                <div className="mt-2 rounded-lg bg-white/50 p-2 text-sm text-blue-700 dark:bg-white/10 dark:text-blue-300">
                  <strong>您的选课需求 ：</strong><br />
                  {recommendationNote && <>• 想修读：{recommendationNote}<br /></>}
                  {avoidTimeSlots && <>• 避开时间段：{avoidTimeSlots}<br /></>}
                  {(minCredits || maxCredits) && <>• 学分区间：{minCredits} - {maxCredits} 学分</>}
                </div>

                {showExplanation && (
                  <>
                    <p className="mt-3 text-sm text-blue-700 dark:text-blue-300">
                      {recommendationExplanation.requirement_summary}
                    </p>
                    <div className="mt-3 space-y-2 text-base text-blue-600 dark:text-blue-400">
                      {(() => {
                        const uniqueMatched = recommendationExplanation.matched_courses.filter(
                          (c, idx, self) => idx === self.findIndex((t) => `${t.course_code || ''}::${t.course_name}` === `${c.course_code || ''}::${c.course_name}`)
                        )
                        return uniqueMatched.map((c, idx) => {
                          return (
                            <div key={idx} className="flex items-start gap-2">
                              <span className="font-semibold">{idx + 1}.</span>
                              <div className="flex-1">
                                <span className="font-semibold">{c.course_name}</span>
                                {c.credits != null && <span className="ml-1 text-xs text-gray-500 dark:text-gray-400">({c.credits}学分)</span>}
                                <span className="ml-1">: {c.reason}</span>
                                {c.status === 'postponed' && <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">（后置名单，无课表时间）</span>}
                              </div>
                            </div>
                          )
                        })
                      })()}
                    </div>
                  </>
                )}
              </div>
            )}

            {plan && plan.rationale && (
              <div className="rounded-2xl bg-gray-50 px-4 py-3 text-sm text-gray-600 dark:bg-slate-900 dark:text-gray-300">
                推荐理由：{plan.rationale}
              </div>
            )}

            {loading && <p className="text-sm text-gray-500 dark:text-gray-400">正在加载课表...</p>}
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            {!error && message && <p className="text-sm text-amber-700 dark:text-amber-300">{message}</p>}
            {!loading && !error && meetings.length === 0 && (
              <p className="text-sm text-gray-500 dark:text-gray-400">暂无课表数据，请先配置 TIS 接口并抓取。</p>
            )}

            <div className="flex-1 min-h-0 rounded-2xl border border-gray-100 bg-white dark:border-slate-800 dark:bg-slate-950">
              <div
                className="grid text-xs"
                style={{
                  gridTemplateColumns: '140px repeat(7, minmax(0, 1fr))',
                  gridTemplateRows: '48px repeat(11, 80px)',
                }}
              >
                <div className="col-span-1 row-span-1 flex items-center justify-center text-base font-semibold text-gray-400 dark:text-gray-500">
                  时间
                </div>

                {weekdays.map((day, index) => (
                  <div
                    key={day}
                    className="col-span-1 row-span-1 flex items-center justify-center border-l border-gray-100 text-base font-semibold text-gray-700 dark:border-slate-800 dark:text-gray-200"
                    style={{ gridColumnStart: index + 2, gridRowStart: 1 }}
                  >
                    {day}
                  </div>
                ))}

                {slotTimes.map((slot) => (
                  <div
                    key={slot.slot}
                    className="col-span-1 row-span-1 flex flex-col items-start justify-center border-t border-gray-100 px-4 text-sm text-gray-500 dark:border-slate-800 dark:text-gray-400 min-h-[4rem]"
                    style={{ gridColumnStart: 1, gridRowStart: slot.slot + 1 }}
                  >
                    <span className="text-base font-semibold text-gray-700 dark:text-gray-200">第{slot.slot}节</span>
                    <span className="text-sm opacity-90">{slot.time}</span>
                  </div>
                ))}

                {weekdays.map((_, dayIndex) =>
                  slotTimes.map((slot) => (
                    <div
                      key={`${dayIndex + 1}-${slot.slot}`}
                      className="border-l border-t border-gray-50 dark:border-slate-800"
                      style={{
                        gridColumnStart: dayIndex + 2,
                        gridRowStart: slot.slot + 1,
                      }}
                    />
                  ))
                )}

                {missingScheduleMeetings.length > 0 && (
                  <div style={{ gridColumnStart: 1, gridColumnEnd: 'span 7' }} className="px-3 py-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-lg mb-2">
                    ⚠️ 以下课程暂无具体上课时间，已列入推荐名单但未在课表中定位：
                    {missingScheduleMeetings.map((m, i) => (
                      <span key={i} className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 font-medium">
                        {m.course_name}
                        {m.credits != null && <span className="opacity-70">{m.credits}学分</span>}
                      </span>
                    ))}
                  </div>
                )}

                {meetings.map((meeting, index) => {
                  const span = Math.max(1, meeting.end_slot! - meeting.start_slot! + 1)
                  const colorKey = baseCourseName(meeting.course_name) || meeting.course_name
                  const colorStyle = colorFromText(colorKey)
                  return (
                    <div
                      key={`${meeting.course_name}-${index}`}
                      className="cr-meeting-card mx-2 my-1 rounded-xl border px-3 py-2 text-[11px] shadow-sm backdrop-blur"
                      style={{
                        gridColumnStart: meeting.day_of_week! + 1,
                        gridRowStart: meeting.start_slot! + 1,
                        gridRowEnd: `span ${span}`,
                        ['--cr-bg' as string]: colorStyle.backgroundColor,
                        ['--cr-border' as string]: colorStyle.borderColor,
                        ['--cr-text' as string]: colorStyle.color,
                      }}
                    >
                      <p className="text-[14px] font-semibold leading-snug">{meeting.course_name}</p>
                      <p className="mt-1 text-[12px] opacity-90">
                        {meeting.location || '待定'} {meeting.instructor ? `· ${meeting.instructor}` : ''}
                      </p>
                      {meeting.weeks && <p className="mt-1 text-[12px] opacity-80">{meeting.weeks}</p>}
                    </div>
                  )
                })}
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Course planning UI removed */}

      {academicAnalysisOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4 py-6">
          <div className="w-full max-w-5xl max-h-[82vh] overflow-auto rounded-[28px] bg-white p-6 shadow-2xl dark:bg-gray-900">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100">🎓 学业修读情况</h3>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => openAcademicAnalysis(true)}
                  className="rounded-full p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-800 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-gray-100"
                  aria-label="刷新学业情况"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                </button>
                <button onClick={() => setAcademicAnalysisOpen(false)} className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">✕</button>
              </div>
            </div>
            {loadingAcademic ? (
              <div className="py-8 text-center">
                <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
                <p className="mt-2 text-gray-500">正在分析您的学业数据...</p>
              </div>
            ) : academicData ? (
              <>
                <div className="mb-4 grid gap-3 rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-900/20 dark:text-emerald-100 md:grid-cols-4">
                  <p>🎓 专业：{academicData.major || currentMajor}</p>
                  <p>📚 已修总学分：{academicData.completed_credits} / {academicData.required_credits} </p>
                  <p>📚 已修课程：{academicData.course_count} 门</p>
                  <p>⏱️ 总学时：{academicData.total_hours} 学时</p>
                </div>
                <table className="w-full text-sm text-gray-700 dark:text-gray-100">
                  <thead className="bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-100">
                    <tr>
                      <th className="px-3 py-2 text-left">课程类别</th>
                      <th className="px-3 py-2 text-left">要求学分</th>
                      <th className="px-3 py-2 text-left">已修学分</th>
                      <th className="px-3 py-2 text-left">仍需学分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(academicData.categories || []).map((cat: any, idx: number) => (
                      <tr key={idx} className="border-b border-gray-200 dark:border-gray-700">
                        <td className="px-3 py-2">{cat.category}</td>
                        <td className="px-3 py-2">{cat.required ?? '?'}</td>
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => {
                              const coursesList = (cat.courses || []).map((course: any) => `${course.name}${course.credits ? ` (${course.credits}学分)` : ''}`)
                              setModalTitle(`${cat.category} 已修课程`)
                              setModalCourses(coursesList)
                              setModalVisible(true)
                            }}
                            className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-200"
                          >
                            {cat.completed}
                          </button>
                        </td>
                        <td className="px-3 py-2">{cat.remaining ?? '?'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : null}
          </div>
        </div>
      )}

      {modalVisible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 py-6 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{modalTitle}</h3>
              <button
                type="button"
                onClick={() => setModalVisible(false)}
                className="text-2xl leading-none text-gray-500 transition hover:text-gray-700 dark:hover:text-gray-300"
                aria-label="关闭课程列表弹窗"
              >
                ✕
              </button>
            </div>
            <div className="max-h-96 overflow-y-auto text-sm text-gray-700 dark:text-gray-200">
              {modalCourses.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400">暂无课程明细</p>
              ) : (
                <ul className="list-disc space-y-1 pl-5">
                  {modalCourses.map((course, idx) => (
                    <li key={`${course}-${idx}`}>{course}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {recommendationModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 py-6 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setRecommendationModalOpen(false)
            }
          }}
        >
          <div className="w-full max-w-5xl rounded-[32px] border border-white/20 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-950">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-xl font-semibold text-gray-900 dark:text-gray-100">课表推荐</h4>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  选择目标学期并补充你的偏好，智能体会结合已修课程和培养方案生成推荐。
                </p>
              </div>

              <button
                type="button"
                onClick={() => setRecommendationModalOpen(false)}
                className="rounded-full px-3 py-1 text-sm text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-slate-900 dark:hover:text-gray-200"
                aria-label="关闭弹窗"
              >
                ✕
              </button>
            </div>

            {recommendationError && (
              <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-200">
                {recommendationError}
              </p>
            )}

            <div className="mt-6 grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
              <div className="rounded-3xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-800 dark:bg-slate-900/70">
                <label className="text-sm font-semibold text-gray-700 dark:text-gray-200">推荐学期</label>
                <select
                  value={recommendationTermId}
                  onChange={(e) => setRecommendationTermId(e.target.value)}
                  disabled={recommendationTermOptions.length === 0}
                  className="mt-2 w-full rounded-xl border border-gray-200 bg-gray-100 px-3 py-2 text-sm text-gray-700 outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-100"
                >
                  <option value="" disabled>
                    {recommendationTermOptions.length === 0 ? '暂无可选学期' : '请选择学期'}
                  </option>
                  {recommendationTermOptions.map((option) => (
                    <option key={option.termId} value={option.termId}>
                      {option.label} · {option.sourceLabel}
                    </option>
                  ))}
                </select>
                
                <label className="mt-3 block text-sm font-semibold text-gray-700 dark:text-gray-200">我的专业</label>
                <input
                  type="text"
                  value={currentMajor}
                  readOnly
                  placeholder="如：计算机科学与技术"
                  className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-100 px-3 py-2 text-sm text-gray-600 outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-gray-200"
                />
                <p className="mt-2 text-xs text-gray-500">来自个人信息设置，会自动用于培养方案匹配</p>
              </div>

              <div className="rounded-3xl border border-gray-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
                <label className="text-sm font-semibold text-gray-700 dark:text-gray-200">📝 我的需求</label>

                <div className="mt-3 space-y-3">
                  <div>
                    <label className="text-xs text-gray-500 dark:text-gray-400">我想要修读的课程</label>
                    <input
                      type="text"
                      value={recommendationNote}
                      onChange={(e) => setRecommendationNote(e.target.value)}
                      placeholder="例如：软件工程、人工智能"
                      className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-emerald-500 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-gray-500 dark:text-gray-400">建议最低学分（最多20）</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        value={minCredits}
                        onChange={(e) => setMinCredits(Number(e.target.value || 0))}
                        min={0}
                        max={20}
                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-emerald-500 text-gray-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 dark:text-gray-400">建议最高学分（最多25）</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        value={maxCredits}
                        onChange={(e) => setMaxCredits(Number(e.target.value || 0))}
                        min={0}
                        max={25}
                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-emerald-500 text-gray-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    <label className="text-xs text-gray-500 dark:text-gray-400">我不希望___时间段有课</label>
                    <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                      <select
                        value={newAvoidWeekday}
                        onChange={(e) => setNewAvoidWeekday(Number(e.target.value))}
                        className="w-24 rounded-xl border border-gray-200 bg-gray-50 px-2 py-1 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                      >
                        {weekdayLabels.slice(1).map((day, idx) => (
                          <option key={day} value={idx + 1}>{day}</option>
                        ))}
                      </select>
                      <select
                        value={newAvoidStart}
                        onChange={(e) => setNewAvoidStart(Number(e.target.value))}
                        className="w-20 rounded-xl border border-gray-200 bg-gray-50 px-2 py-1 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                      >
                        {slotNumbers.map((slot) => <option key={slot} value={slot}>第{slot}节</option>)}
                      </select>
                      <span className="text-sm text-gray-500 dark:text-gray-400">至</span>
                      <select
                        value={newAvoidEnd}
                        onChange={(e) => setNewAvoidEnd(Number(e.target.value))}
                        className="w-20 rounded-xl border border-gray-200 bg-gray-50 px-2 py-1 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                      >
                        {slotNumbers.map((slot) => <option key={slot} value={slot}>第{slot}节</option>)}
                      </select>
                      <button
                        type="button"
                        onClick={addAvoidSlot}
                        className="whitespace-nowrap rounded-full bg-emerald-500 px-2 py-1 text-xs text-white"
                      >
                        + 添加
                      </button>
                    </div>
                    {avoidSlots.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {avoidSlots.map((slot, idx) => (
                          <span
                            key={`${slot.weekday}-${slot.start}-${slot.end}-${idx}`}
                            className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-1 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-300"
                          >
                            {weekdayLabels[slot.weekday]}第{slot.start}-{slot.end}节
                            <button
                              type="button"
                              onClick={() => removeAvoidSlot(idx)}
                              className="ml-1 font-bold"
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                </div>

                <p className="mt-3 text-xs text-gray-400">AI 会根据你的需求，结合培养方案和全校课表智能推荐</p>
              </div>
            </div>

            {/* Live agent progress panel */}
            {planning && planSteps.length > 0 && (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/80 p-3 dark:border-emerald-800 dark:bg-emerald-950/40">
                <div className="flex items-center gap-2 mb-2">
                  <div className="relative flex h-3 w-3">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500"></span>
                  </div>
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    Agent 推理中
                    {agentStep.current > 0 && (
                      <span className="ml-1.5 inline-flex items-center rounded-full bg-emerald-200/80 dark:bg-emerald-800/60 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800 dark:text-emerald-200">
                        第 {agentStep.current} 步
                      </span>
                    )}
                  </span>
                </div>
                {/* Current step highlight */}
                {agentStep.label && (
                  <div className="mb-2 rounded-lg bg-emerald-100/90 dark:bg-emerald-900/70 px-2 py-1.5 text-xs font-medium text-emerald-900 dark:text-emerald-100 truncate">
                    🔧 {agentStep.label}
                  </div>
                )}
                {/* Step history */}
                <div className="max-h-28 overflow-y-auto space-y-0.5 text-[11px] text-emerald-800/80 dark:text-emerald-200/70">
                  {planSteps.map((step, i) => {
                    const isLast = i === planSteps.length - 1
                    return (
                      <div key={i} className={`flex items-center gap-1.5 ${isLast ? 'font-semibold text-emerald-900 dark:text-emerald-100' : ''}`}>
                        <span className={isLast ? 'text-emerald-600 dark:text-emerald-400' : 'text-emerald-500'}>›</span>
                        <span className="truncate">{step}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setRecommendationModalOpen(false)}
                disabled={planning}
                className="rounded-full border border-gray-200 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-200 dark:hover:bg-slate-800 disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleGenerateRecommendation}
                disabled={planning || recommendationTermOptions.length === 0}
                className="rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {planning ? '生成中...' : '生成课表推荐'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CourseRecommendation
