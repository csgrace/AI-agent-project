import { useState, useMemo, useEffect, useRef } from 'react';

// 事件类型定义
export interface CalendarEvent {
  id: string;
  title: string;
  description?: string;
  source: string;
  scheduled_start: Date;
  deadline: Date;
  duration?: number;
  computed_end_time?: Date;
  location?: string;
  priority?: string;
  status?: string;
  category: string;
  color_tag: string;
  recurring_rule?: Record<string, unknown>;
  metadata: Record<string, unknown>;
  tags: string[];
  created_at?: Date;
  updated_at?: Date;
  duration_minutes: number;
  is_feasible: boolean;
  is_overdue: boolean;
  is_recurring: boolean;
  is_draft_modified?: boolean;
}

interface ModernCalendarProps {
  events: CalendarEvent[];
  onAddEvent: () => void;
  onSelectEvent: (event: CalendarEvent | null) => void;
  draftDirty?: string | null;
  onCommitDraft?: () => void;
  onResetDraft?: () => void;
}

const ModernCalendar: React.FC<ModernCalendarProps> = ({ 
  events, 
  onAddEvent, 
  onSelectEvent,
}) => {
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const [showEventList, setShowEventList] = useState(false);
  const calendarRef = useRef<HTMLDivElement>(null);
  const eventListRef = useRef<HTMLDivElement>(null);

  // 处理展开/收起动画
  useEffect(() => {
    if (selectedDate) {
      setIsAnimating(true);
      // 延迟显示事件列表，让日历先压缩
      const timer = setTimeout(() => {
        setShowEventList(true);
        setIsAnimating(false);
      }, 250);
      return () => clearTimeout(timer);
    } else {
      setShowEventList(false);
      setIsAnimating(true);
      const timer = setTimeout(() => {
        setIsAnimating(false);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [selectedDate]);

  // 获取月份的天数
  const getDaysInMonth = (month: number, year: number) => {
    return new Date(year, month + 1, 0).getDate();
  };

  // 获取月份的第一天是星期几
  const getFirstDayOfMonth = (month: number, year: number) => {
    return new Date(year, month, 1).getDay();
  };

  // 获取某一天的节假日事件（university来源）
  const getHolidaysForDay = (day: number, month: number, year: number) => {
    return events.filter(event => {
      const eventDate = event.scheduled_start.getDate();
      const eventMonth = event.scheduled_start.getMonth();
      const eventYear = event.scheduled_start.getFullYear();
      return eventDate === day && eventMonth === month && eventYear === year && event.source === 'university';
    });
  };

  // 获取某一天的任务事件（blackboard和todoist来源）
  const getTasksForDay = (day: number, month: number, year: number) => {
    return events.filter(event => {
      const eventDate = event.scheduled_start.getDate();
      const eventMonth = event.scheduled_start.getMonth();
      const eventYear = event.scheduled_start.getFullYear();
      return eventDate === day && eventMonth === month && eventYear === year && 
             (event.source === 'blackboard' || event.source === 'todoist' || event.source === 'personal' || event.source === 'course');
    });
  };

  // 检查某天是否有任务
  const hasTasksOnDay = (day: number, month: number, year: number) => {
    return getTasksForDay(day, month, year).length > 0;
  };

  // 生成日历数据
  const calendarData = useMemo(() => {
    const daysInMonth = getDaysInMonth(currentMonth, currentYear);
    const firstDayOfMonth = getFirstDayOfMonth(currentMonth, currentYear);
    const calendar = [];

    // 添加上个月的占位天数
    const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
    const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;
    const prevMonthDays = getDaysInMonth(prevMonth, prevYear);
    
    for (let i = 0; i < firstDayOfMonth; i++) {
      const day = prevMonthDays - firstDayOfMonth + i + 1;
      calendar.push({ day, isCurrentMonth: false, month: prevMonth, year: prevYear });
    }

    // 添加当前月的天数
    for (let i = 1; i <= daysInMonth; i++) {
      calendar.push({ day: i, isCurrentMonth: true, month: currentMonth, year: currentYear });
    }

    // 添加下个月的占位天数
    const nextMonth = currentMonth === 11 ? 0 : currentMonth + 1;
    const nextYear = currentMonth === 11 ? currentYear + 1 : currentYear;
    const remainingDays = 42 - calendar.length;
    
    for (let i = 1; i <= remainingDays; i++) {
      calendar.push({ day: i, isCurrentMonth: false, month: nextMonth, year: nextYear });
    }

    return calendar;
  }, [currentMonth, currentYear]);

  // 选中日期的任务
  const selectedDateTasks = useMemo(() => {
    if (!selectedDate) return [];
    return getTasksForDay(
      selectedDate.getDate(), 
      selectedDate.getMonth(), 
      selectedDate.getFullYear()
    );
  }, [selectedDate, events]);

  // 月份名称
  const monthNames = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'];
  const weekNames = ['日', '一', '二', '三', '四', '五', '六'];

  // 切换到上个月
  const prevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear(currentYear - 1);
    } else {
      setCurrentMonth(currentMonth - 1);
    }
    setSelectedDate(null);
  };

  // 切换到下个月
  const nextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear(currentYear + 1);
    } else {
      setCurrentMonth(currentMonth + 1);
    }
    setSelectedDate(null);
  };

  // 回到今天
  const goToToday = () => {
    const today = new Date();
    setCurrentMonth(today.getMonth());
    setCurrentYear(today.getFullYear());
    setSelectedDate(null);
  };

  // 处理日期点击
  const handleDateClick = (day: number, month: number, year: number, isCurrentMonth: boolean) => {
    if (!isCurrentMonth) return;
    
    const clickedDate = new Date(year, month, day);
    
    if (selectedDate && 
        selectedDate.getDate() === day && 
        selectedDate.getMonth() === month && 
        selectedDate.getFullYear() === year) {
      setSelectedDate(null);
    } else {
      setSelectedDate(clickedDate);
    }
  };

  // 获取优先级样式
  const getPriorityStyle = (priority?: string) => {
    switch (priority) {
      case 'high':
        return 'border-l-red-500 bg-red-50 dark:bg-red-950/30';
      case 'medium':
        return 'border-l-yellow-500 bg-yellow-50 dark:bg-yellow-950/30';
      case 'low':
        return 'border-l-green-500 bg-green-50 dark:bg-green-950/30';
      default:
        return 'border-l-gray-400 bg-gray-50 dark:bg-gray-800';
    }
  };

  // 获取来源标签
  const getSourceLabel = (source: string) => {
    switch (source) {
      case 'blackboard':
        return { label: 'Blackboard', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300' };
      case 'todoist':
        return { label: 'Todoist', color: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' };
      case 'personal':
        return { label: '个人', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300' };
      case 'course':
        return { label: '课程', color: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300' };
      default:
        return { label: source, color: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300' };
    }
  };

  const isExpanded = selectedDate !== null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 h-full flex flex-col overflow-hidden">
      {/* 日历标题栏 */}
      <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-4">
            <h3 className="text-2xl font-semibold text-gray-900 dark:text-white">
              {currentYear}年{monthNames[currentMonth]}
            </h3>
            <div className="flex items-center gap-1">
              <button 
                onClick={prevMonth}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-600 dark:text-gray-300"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button 
                onClick={goToToday}
                className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                今天
              </button>
              <button 
                onClick={nextMonth}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-600 dark:text-gray-300"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={onAddEvent}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors text-sm font-medium"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              添加事件
            </button>
          </div>
        </div>
      </div>
      
      {/* 日历主体 - 带动画的高度变化 */}
      <div 
        ref={calendarRef}
        className={`
          transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]
          ${isExpanded ? 'flex-shrink-0' : 'flex-1'}
        `}
        style={{
          transform: isAnimating ? 'scale(0.995)' : 'scale(1)',
          transition: 'transform 0.3s ease-out, flex 0.5s cubic-bezier(0.4,0,0.2,1)'
        }}
      >
        {/* 星期标题 */}
        <div className="grid grid-cols-7 px-4 pt-4">
          {weekNames.map((day, idx) => (
            <div 
              key={day} 
              className="text-center text-xs font-medium text-gray-400 dark:text-gray-500 py-2"
              style={{
                opacity: isExpanded ? 0.7 : 1,
                transform: isExpanded ? 'scale(0.95)' : 'scale(1)',
                transition: `all 0.3s ease ${idx * 0.02}s`
              }}
            >
              {day}
            </div>
          ))}
        </div>
        
        {/* 日历格子 */}
        <div 
          className={`
            grid grid-cols-7 gap-1 px-4 pb-4 
            transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]
          `}
          style={{
            maxHeight: isExpanded ? '280px' : '500px',
          }}
        >
          {calendarData.map((item, index) => {
            const holidays = getHolidaysForDay(item.day, item.month, item.year);
            const hasTasks = hasTasksOnDay(item.day, item.month, item.year);
            const isToday = new Date().getDate() === item.day && 
                          new Date().getMonth() === item.month && 
                          new Date().getFullYear() === item.year;
            const isSelected = selectedDate && 
                              selectedDate.getDate() === item.day && 
                              selectedDate.getMonth() === item.month && 
                              selectedDate.getFullYear() === item.year;
            
            // 计算动画延迟 - 从选中的日期向外扩散
            const row = Math.floor(index / 7);
            const col = index % 7;
            const delay = isExpanded 
              ? (row * 0.02 + col * 0.01) 
              : ((5 - row) * 0.02 + (6 - col) * 0.01);
            
            return (
              <div 
                key={index}
                onClick={() => handleDateClick(item.day, item.month, item.year, item.isCurrentMonth)}
                className={`
                  relative rounded-xl cursor-pointer
                  ${item.isCurrentMonth 
                    ? 'hover:bg-gray-50 dark:hover:bg-gray-700/50 hover:scale-105' 
                    : 'opacity-30'
                  }
                  ${isSelected 
                    ? 'bg-emerald-50 dark:bg-emerald-900/20 ring-2 ring-emerald-500 scale-105 z-10' 
                    : ''
                  }
                `}
                style={{
                  padding: isExpanded ? '6px' : '8px',
                  minHeight: isExpanded ? '40px' : '70px',
                  transition: `all 0.4s cubic-bezier(0.4,0,0.2,1) ${delay}s`,
                  transform: isSelected ? 'scale(1.05)' : 'scale(1)',
                }}
              >
                {/* 日期数字 */}
                <div className="flex items-center justify-between">
                  <span 
                    className={`
                      font-medium transition-all duration-300
                      ${isToday 
                        ? 'flex items-center justify-center bg-emerald-500 text-white rounded-full shadow-lg shadow-emerald-500/30' 
                        : isSelected
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-gray-700 dark:text-gray-300'
                      }
                    `}
                    style={{
                      fontSize: isExpanded ? '12px' : '14px',
                      width: isToday ? (isExpanded ? '24px' : '28px') : 'auto',
                      height: isToday ? (isExpanded ? '24px' : '28px') : 'auto',
                      transition: 'all 0.4s cubic-bezier(0.4,0,0.2,1)'
                    }}
                  >
                    {item.day}
                  </span>
                  
                  {/* 任务指示点 - 带脉冲动画 */}
                  {hasTasks && item.isCurrentMonth && (
                    <span 
                      className="relative"
                      style={{
                        opacity: 1,
                        transform: 'scale(1)',
                        transition: `all 0.3s ease ${delay + 0.1}s`
                      }}
                    >
                      <span className="absolute inset-0 w-2 h-2 bg-emerald-400 rounded-full animate-ping opacity-75" />
                      <span className="relative block w-2 h-2 bg-emerald-500 rounded-full" />
                    </span>
                  )}
                </div>
                
                {/* 节假日标签（仅在非展开状态显示） - 带淡出动画 */}
                <div 
                  className="mt-1 space-y-1 overflow-hidden"
                  style={{
                    opacity: isExpanded ? 0 : 1,
                    maxHeight: isExpanded ? '0px' : '60px',
                    transform: isExpanded ? 'translateY(-10px)' : 'translateY(0)',
                    transition: `all 0.3s ease ${isExpanded ? '0s' : `${delay + 0.2}s`}`
                  }}
                >
                  {holidays.length > 0 && item.isCurrentMonth && holidays.slice(0, 2).map((holiday, hIdx) => (
                    <div 
                      key={holiday.id}
                      className="text-xs px-1.5 py-0.5 bg-rose-100 dark:bg-rose-900/40 text-rose-600 dark:text-rose-300 rounded truncate"
                      style={{
                        opacity: isExpanded ? 0 : 1,
                        transform: isExpanded ? 'scale(0.8)' : 'scale(1)',
                        transition: `all 0.2s ease ${hIdx * 0.05}s`
                      }}
                    >
                      {holiday.title}
                    </div>
                  ))}
                  {holidays.length > 2 && (
                    <div className="text-xs text-gray-400 dark:text-gray-500">
                      +{holidays.length - 2} 更多
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 选中日期的事件列表 - 带动画 */}
      <div
        ref={eventListRef}
        className={`
          flex flex-col border-t border-gray-100 dark:border-gray-700 overflow-hidden
          transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]
          ${isExpanded ? 'flex-1 min-h-0' : 'max-h-0'}
        `}
        style={{
          opacity: showEventList ? 1 : 0,
          transform: showEventList ? 'translateY(0)' : 'translateY(20px)',
          transition: 'opacity 0.4s ease, transform 0.4s ease, max-height 0.5s cubic-bezier(0.4,0,0.2,1), flex 0.5s cubic-bezier(0.4,0,0.2,1)'
        }}
      >
        {selectedDate && (
          <div className="p-4 flex flex-col min-h-0 flex-1">
            {/* 标题栏 - 带滑入动画 */}
            <div 
              className="flex items-center justify-between mb-3"
              style={{
                opacity: showEventList ? 1 : 0,
                transform: showEventList ? 'translateX(0)' : 'translateX(-20px)',
                transition: 'all 0.4s ease 0.1s'
              }}
            >
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
                {selectedDate.getMonth() + 1}月{selectedDate.getDate()}日的事项
              </h4>
              <button 
                onClick={() => setSelectedDate(null)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-200 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:rotate-90"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
              {selectedDateTasks.length > 0 ? (
                selectedDateTasks.map((task, taskIndex) => {
                  const sourceInfo = getSourceLabel(task.source);
                  return (
                    <div 
                      key={task.id}
                      onClick={() => onSelectEvent(task)}
                      className={`
                        p-3 rounded-xl border-l-4 cursor-pointer
                        hover:shadow-md active:scale-[0.98]
                        ${getPriorityStyle(task.priority)}
                        ${task.is_draft_modified ? 'ring-2 ring-amber-400/50 dark:ring-amber-500/50 relative' : ''}
                      `}
                      style={{
                        opacity: showEventList ? 1 : 0,
                        transform: showEventList ? 'translateX(0)' : 'translateX(30px)',
                        transition: `all 0.4s cubic-bezier(0.4,0,0.2,1) ${0.15 + taskIndex * 0.08}s`
                      }}
                    >
                      {task.is_draft_modified && (
                        <span className="absolute top-1 right-1 px-1.5 py-0.5 bg-amber-400 dark:bg-amber-500 text-white text-[10px] rounded font-bold leading-none">
                          草稿
                        </span>
                      )}
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <h5 className="font-medium text-gray-900 dark:text-white truncate">
                            {task.title}
                          </h5>
                          {task.description && (
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                              {task.description}
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-2 flex-wrap">
                            <span 
                              className={`text-xs px-2 py-0.5 rounded-full transition-transform hover:scale-105 ${sourceInfo.color}`}
                            >
                              {sourceInfo.label}
                            </span>
                            <span className="text-xs text-gray-400 dark:text-gray-500">
                              {task.scheduled_start.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                            {task.location && (
                              <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                {task.location}
                              </span>
                            )}
                          </div>
                        </div>
                        <svg 
                          className="w-5 h-5 text-gray-400 flex-shrink-0 transition-transform duration-200 group-hover:translate-x-1" 
                          fill="none" 
                          stroke="currentColor" 
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div 
                  className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-500 py-8"
                  style={{
                    opacity: showEventList ? 1 : 0,
                    transform: showEventList ? 'scale(1)' : 'scale(0.9)',
                    transition: 'all 0.4s ease 0.2s'
                  }}
                >
                  <svg 
                    className="w-12 h-12 mb-3 opacity-50" 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                    style={{
                      animation: showEventList ? 'float 3s ease-in-out infinite' : 'none'
                    }}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <p className="text-sm">这一天没有事项</p>
                  <button 
                    onClick={onAddEvent}
                    className="mt-3 text-sm text-emerald-500 hover:text-emerald-600 font-medium transition-all hover:scale-105"
                  >
                    添加新事件
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* 添加浮动动画的CSS */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  );
};

export default ModernCalendar;
