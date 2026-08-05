import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism'
import ModernCalendar from './ModernCalendar'
import {
  fetchCalendar,
  fetchDraftCalendar,
  createEvent,
  updateEvent,
  deleteEvent,
  commitDraft,
  resetDraft,
  streamChat,
  resetAgent,
  fetchChatHistory,
  type CalendarEvent as BackendEvent,
  type CreateEventRequest,
  type UpdateEventRequest,
} from '../api'

export interface UICalendarEvent {
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

function backendEventToUI(raw: BackendEvent, isDraftModified = false): UICalendarEvent {
  return {
    id: raw.id,
    title: raw.title,
    description: raw.description,
    source: raw.source,
    scheduled_start: new Date(raw.scheduled_start),
    deadline: new Date(raw.deadline),
    duration: raw.duration,
    computed_end_time: raw.computed_end_time ? new Date(raw.computed_end_time) : undefined,
    location: raw.location,
    priority: raw.priority,
    status: raw.status,
    category: raw.category,
    color_tag: raw.color_tag,
    recurring_rule: raw.recurring_rule,
    metadata: raw.metadata || {},
    tags: raw.tags || [],
    created_at: raw.created_at ? new Date(raw.created_at) : undefined,
    updated_at: raw.updated_at ? new Date(raw.updated_at) : undefined,
    duration_minutes: raw.duration_minutes || 0,
    is_feasible: raw.is_feasible ?? true,
    is_overdue: raw.is_overdue ?? false,
    is_recurring: raw.is_recurring ?? false,
    is_draft_modified: isDraftModified,
  };
}

// `uiEventToBackendFormat` removed — unused in current codebase

const colorOptions = [
  { name: 'red', label: '红色', bg: 'bg-red-500' },
  { name: 'orange', label: '橙色', bg: 'bg-orange-500' },
  { name: 'yellow', label: '黄色', bg: 'bg-yellow-400' },
  { name: 'green', label: '绿色', bg: 'bg-emerald-500' },
  { name: 'blue', label: '蓝色', bg: 'bg-blue-500' },
  { name: 'purple', label: '紫色', bg: 'bg-purple-500' },
  { name: 'pink', label: '粉色', bg: 'bg-pink-500' },
  { name: 'grey', label: '灰色', bg: 'bg-gray-500' },
];

const EventForm: React.FC<{
  event?: UICalendarEvent;
  onSubmit: (data: { scheduled_start: Date; deadline: Date; title: string; description?: string; location?: string; priority?: string; status?: string; color_tag: string; tags: string[] }) => void;
  onCancel: () => void;
  onAfterCancel?: () => void;
}> = ({ event, onSubmit, onCancel, onAfterCancel }) => {
  const [title, setTitle] = useState(event?.title || '');
  const getLocalTimeString = (date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  const [startTime, setStartTime] = useState(event?.scheduled_start || new Date());
  const [endTime, setEndTime] = useState(event?.deadline || new Date(new Date().getTime() + 60 * 60 * 1000));
  const [showMoreOptions, setShowMoreOptions] = useState(false);
  const [description, setDescription] = useState(event?.description || '');
  const [location, setLocation] = useState(event?.location || '');
  const [priority, setPriority] = useState(event?.priority || 'medium');
  const [status, setStatus] = useState(event?.status || 'pending');
  const [colorTag, setColorTag] = useState(event?.color_tag || 'blue');
  const [tags, setTags] = useState<string[]>(event?.tags || []);
  const [newTag, setNewTag] = useState('');
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setIsVisible(true));
  }, []);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(() => {
      onCancel();
      if (onAfterCancel) {
        onAfterCancel();
      }
    }, 300);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsVisible(false);
    setTimeout(() => {
      onSubmit({
        title,
        description: description || undefined,
        scheduled_start: startTime,
        deadline: endTime,
        location: location || undefined,
        priority,
        status,
        color_tag: colorTag,
        tags,
      });
    }, 300);
  };

  const handleAddTag = () => {
    if (newTag && !tags.includes(newTag)) {
      setTags([...tags, newTag]);
      setNewTag('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag));
  };

  return (
    <div 
      className={`bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-2xl mx-auto w-full
        transform transition-all duration-300 ease-out
        ${isVisible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'}`}
      style={{ maxHeight: '90vh', overflow: 'auto' }}
    >
      <div className="sticky top-0 bg-white dark:bg-gray-800 px-6 py-5 border-b border-gray-100 dark:border-gray-700 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${event ? 'bg-blue-100 dark:bg-blue-900/30' : 'bg-emerald-100 dark:bg-emerald-900/30'}`}>
              <svg className={`w-5 h-5 ${event ? 'text-blue-600 dark:text-blue-400' : 'text-emerald-600 dark:text-emerald-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {event ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                )}
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white">{event ? '编辑事件' : '添加新事件'}</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">{event ? '修改事件的详细信息' : '创建一个新的日程事件'}</p>
            </div>
          </div>
          <button onClick={handleClose} className="p-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-200 hover:rotate-90 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-6">
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
            </svg>
            事件标题
          </label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="输入事件标题..."
            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white placeholder-gray-400 transition-all duration-200 hover:border-gray-300 dark:hover:border-gray-500" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              开始时间
            </label>
            <input type="datetime-local" value={getLocalTimeString(startTime)} onChange={(e) => setStartTime(new Date(e.target.value))} required
              className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white transition-all duration-200 hover:border-gray-300 dark:hover:border-gray-500" />
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              截止时间
            </label>
            <input type="datetime-local" value={getLocalTimeString(endTime)} onChange={(e) => setEndTime(new Date(e.target.value))} required
              className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white transition-all duration-200 hover:border-gray-300 dark:hover:border-gray-500" />
          </div>
        </div>

        <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
          <button type="button" onClick={() => setShowMoreOptions(!showMoreOptions)}
            className="flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors group">
            <svg className={`w-4 h-4 transition-transform duration-300 ${showMoreOptions ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            <span>{showMoreOptions ? '收起详细选项' : '展开详细选项'}</span>
          </button>

          <div className={`overflow-hidden transition-all duration-400 ease-out ${showMoreOptions ? 'max-h-[800px] opacity-100 mt-4' : 'max-h-0 opacity-0'}`}>
            <div className="space-y-5 bg-gray-50 dark:bg-gray-700/30 rounded-xl p-4">
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">描述</label>
                <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="添加事件描述..."
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white placeholder-gray-400 resize-none" />
              </div>
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">地点</label>
                <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="添加地点..."
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white placeholder-gray-400" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">优先级</label>
                  <div className="flex gap-2">
                    {[
                      { value: 'high', label: '高', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800' },
                      { value: 'medium', label: '中', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800' },
                      { value: 'low', label: '低', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800' },
                    ].map(opt => (
                      <button key={opt.value} type="button" onClick={() => setPriority(opt.value)}
                        className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-all duration-200 ${priority === opt.value ? `${opt.color} ring-2 ring-offset-1 ring-current scale-105` : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'}`}>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">状态</label>
                  <select value={status} onChange={(e) => setStatus(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white">
                    <option value="pending">待处理</option>
                    <option value="in_progress">进行中</option>
                    <option value="completed">已完成</option>
                    <option value="cancelled">已取消</option>
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">颜色标签</label>
                <div className="flex flex-wrap gap-3">
                  {colorOptions.map((color) => (
                    <button key={color.name} type="button" onClick={() => setColorTag(color.name)}
                      className={`w-9 h-9 rounded-full ${color.bg} transition-all duration-300 ${colorTag === color.name ? 'ring-2 ring-offset-2 ring-gray-400 dark:ring-gray-300 scale-110' : 'hover:scale-110 opacity-70 hover:opacity-100'}`}
                      title={color.label} />
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">标签</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {tags.map((tag) => (
                    <span key={tag} className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">
                      {tag}
                      <button type="button" onClick={() => handleRemoveTag(tag)} className="ml-1 w-4 h-4 rounded-full hover:bg-emerald-200 dark:hover:bg-emerald-800 flex items-center justify-center">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input type="text" value={newTag} onChange={(e) => setNewTag(e.target.value)} onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())} placeholder="输入标签名称..."
                    className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-gray-700 dark:text-white placeholder-gray-400" />
                  <button type="button" onClick={handleAddTag} disabled={!newTag}
                    className="px-4 py-2.5 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-xl hover:bg-emerald-200 dark:hover:bg-emerald-900/50 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed">
                    添加
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex gap-3 pt-4 border-t border-gray-100 dark:border-gray-700">
          <button type="button" onClick={handleClose} className="flex-1 px-6 py-3 border border-gray-200 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200 text-gray-700 dark:text-gray-300 font-medium">取消</button>
          <button type="submit" disabled={!title}
            className="flex-1 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-xl hover:from-emerald-600 hover:to-teal-600 transition-all duration-200 font-medium shadow-lg shadow-emerald-500/25 disabled:opacity-50 disabled:cursor-not-allowed">
            {event ? '保存更改' : '创建事件'}
          </button>
        </div>
      </form>
    </div>
  );
};

const EventDetail: React.FC<{
  event: UICalendarEvent;
  onEdit: () => void;
  onDelete: () => void;
  onClose: () => void;
}> = ({ event, onEdit, onDelete, onClose }) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setIsVisible(true));
  }, []);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(onClose, 300);
  };

  return (
    <div 
      className={`bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-2xl mx-auto w-full
        transform transition-all duration-300 ease-out
        ${isVisible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'}`}
      style={{ maxHeight: '90vh', overflow: 'auto' }}
    >
      <div className="sticky top-0 bg-white dark:bg-gray-800 px-6 py-5 border-b border-gray-100 dark:border-gray-700 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-blue-100 dark:bg-blue-900/30">
              <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white">事件详情</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">查看事件的详细信息</p>
            </div>
          </div>
          <button onClick={handleClose} className="p-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-200 hover:rotate-90 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div className="p-6 space-y-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">事件标题</label>
          <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.title}</div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">开始时间</label>
            <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.scheduled_start.toLocaleString()}</div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">截止时间</label>
            <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.deadline.toLocaleString()}</div>
          </div>
        </div>
        {event.duration && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">持续时长</label>
            <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.duration} 分钟</div>
          </div>
        )}
        <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
          <div className="space-y-5 bg-gray-50 dark:bg-gray-700/30 rounded-xl p-4">
            {event.description && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">描述</label>
                <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white min-h-[80px]">{event.description}</div>
              </div>
            )}
            {event.location && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">地点</label>
                <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.location}</div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">优先级</label>
                <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.priority === 'high' ? '高' : event.priority === 'medium' ? '中' : '低'}</div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">状态</label>
                <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.status === 'pending' ? '待处理' : event.status === 'in_progress' ? '进行中' : event.status === 'completed' ? '已完成' : '已取消'}</div>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">来源</label>
              <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.source === 'university' ? '校历' : event.source === 'blackboard' ? 'Blackboard' : event.source === 'personal' ? '个人' : event.source}</div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">类别</label>
              <div className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-white">{event.category === 'solid' ? '固定事件' : event.category === 'schedulable' ? '可调度' : event.category === 'background' ? '背景' : event.category}</div>
            </div>
            {event.tags && event.tags.length > 0 && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">标签</label>
                <div className="flex flex-wrap gap-2">
                  {event.tags.map((tag) => (
                    <span key={tag} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">{tag}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-3 pt-4 border-t border-gray-100 dark:border-gray-700">
          <button type="button" onClick={handleClose} className="flex-1 px-6 py-3 border border-gray-200 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200 text-gray-700 dark:text-gray-300 font-medium">关闭</button>
          <button type="button" onClick={onEdit} className="flex-1 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-xl hover:from-emerald-600 hover:to-teal-600 transition-all duration-200 font-medium shadow-lg shadow-emerald-500/25">编辑</button>
          <button type="button" onClick={onDelete} className="flex-1 px-6 py-3 bg-gradient-to-r from-red-500 to-rose-500 text-white rounded-xl hover:from-red-600 hover:to-rose-600 transition-all duration-200 font-medium shadow-lg shadow-red-500/25">删除</button>
        </div>
      </div>
    </div>
  );
};

interface ScheduleMessage {
  id: number;
  content: string;
  isUser: boolean;
  isTyping?: boolean;
  type?: 'text' | 'tool' | 'thought';
  toolCall?: {
    name: string;
    args: Record<string, unknown>;
  };
  requiresCommit?: boolean;
}

interface SchedulePlannerProps {
  llmAvailable?: boolean;
  onOpenProfile?: () => void;
}

const SchedulePlanner: React.FC<SchedulePlannerProps> = ({ llmAvailable = true }) => {
  const [scheduleMessages, setScheduleMessages] = useState<ScheduleMessage[]>([]);
  const [scheduleInputText, setScheduleInputText] = useState('');
  const [events, setEvents] = useState<UICalendarEvent[]>([]);
  const [draftDirty, setDraftDirty] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState<boolean>(false);
  const [calendarDiff, setCalendarDiff] = useState<{
    new_events: any[];
    modified_events: any[];
    deleted_events: any[];
  }>({
    new_events: [],
    modified_events: [],
    deleted_events: []
  });
  const [loading, setLoading] = useState(true);
  const [showEventForm, setShowEventForm] = useState(false);
  const [showEventDetail, setShowEventDetail] = useState(false);
  const [currentEvent, setCurrentEvent] = useState<UICalendarEvent | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<UICalendarEvent | null>(null);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [showRetry, setShowRetry] = useState(false);
  const scheduleChatEndRef = useRef<HTMLDivElement>(null);
  const chatTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadCalendarData = useCallback(async () => {
    setLoading(true);
    try {
      const calendar = await fetchCalendar();
      const uiEvents = calendar.events.map(e => backendEventToUI(e, false));
      setEvents(uiEvents);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const checkDraftDirty = useCallback(async () => {
    try {
      const draft = await fetchDraftCalendar();
      setDraftDirty(draft.dirty || null);
    } catch {
      setDraftDirty(null);
    }
  }, []);

  useEffect(() => {
    loadCalendarData();
  }, [loadCalendarData]);

  // Restore chat history from backend on mount.
  useEffect(() => {
    fetchChatHistory()
      .then(data => {
        if (data.ok && data.messages.length > 0) {
          const restored: ScheduleMessage[] = data.messages.map((msg, i) => ({
            id: i,
            content: msg.content,
            isUser: msg.role === 'user',
            type: 'text' as const,
          }));
          setScheduleMessages(restored);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    scheduleChatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [scheduleMessages]);

  const sendScheduleMessage = async () => {
    if (scheduleInputText.trim() === '' || isChatLoading) return;

    // Pre-check: no API key configured
    if (!llmAvailable) {
      const noKeyMsg: ScheduleMessage = {
        id: Date.now(),
        content: '⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。',
        isUser: false,
        type: 'text' as const,
      };
      setScheduleMessages(prev => [...prev, noKeyMsg]);
      return;
    }

    const newMessage: ScheduleMessage = {
      id: Date.now(),
      content: scheduleInputText,
      isUser: true,
    };

    setScheduleMessages(prev => [...prev, newMessage]);
    const userText = scheduleInputText;
    setScheduleInputText('');
    setIsChatLoading(true);
    setShowRetry(false);

    const aiTypingMessage: ScheduleMessage = {
      id: Date.now() + 1,
      content: '',
      isUser: false,
      isTyping: true,
    };
    setScheduleMessages(prev => [...prev, aiTypingMessage]);

    let hasReceivedEvent = false;

    chatTimeoutRef.current = setTimeout(() => {
      if (!hasReceivedEvent) setShowRetry(true);
    }, 30000);

    try {
      for await (const sseEvent of streamChat(userText)) {
        hasReceivedEvent = true;
        setShowRetry(false);

        const eventType = sseEvent.event;
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(sseEvent.data);
        } catch {
          continue;
        }

        if (eventType === 'thought') {
          const thoughtText = data.text as string || '';
          if (thoughtText) {
            setScheduleMessages(prev => {
              const typingIndex = prev.findIndex(msg => msg.id === aiTypingMessage.id);
              if (typingIndex > -1) {
                const newMessages = [...prev];
                newMessages.splice(typingIndex, 0, {
                  id: Date.now() + Math.random(),
                  content: thoughtText,
                  isUser: false,
                  type: 'thought' as const,
                });
                return newMessages;
              }
              return prev;
            });
          }
        } else if (eventType === 'tool_call') {
          const toolName = data.tool_name as string || '';
          const toolArgs = data.tool_args as Record<string, unknown> || {};
          setScheduleMessages(prev => {
            const typingIndex = prev.findIndex(msg => msg.id === aiTypingMessage.id);
            if (typingIndex > -1) {
              const newMessages = [...prev];
              newMessages.splice(typingIndex, 0, {
                id: Date.now() + Math.random(),
                content: '',
                isUser: false,
                type: 'tool' as const,
                toolCall: { name: toolName, args: toolArgs },
              });
              return newMessages;
            }
            return prev;
          });
        } else if (eventType === 'tool_result') {
          const toolName = data.tool_name as string || '';
          const result = data.result as string || '';
          if (result) {
            setScheduleMessages(prev => {
              const typingIndex = prev.findIndex(msg => msg.id === aiTypingMessage.id);
              if (typingIndex > -1) {
                const newMessages = [...prev];
                newMessages.splice(typingIndex, 0, {
                  id: Date.now() + Math.random(),
                  content: `工具执行结果 (${toolName}):\n${result}`,
                  isUser: false,
                  type: 'text' as const,
                });
                return newMessages;
              }
              return prev;
            });
          }
        } else if (eventType === 'tool_progress') {
          const progressMsg = data.message as string || '';
          if (progressMsg) {
            setScheduleMessages(prev => {
              const typingIndex = prev.findIndex(msg => msg.id === aiTypingMessage.id);
              if (typingIndex > -1) {
                const newMessages = [...prev];
                newMessages.splice(typingIndex, 0, {
                  id: Date.now() + Math.random(),
                  content: progressMsg,
                  isUser: false,
                  type: 'text' as const,
                });
                return newMessages;
              }
              return prev;
            });
          }
        } else if (eventType === 'final') {
          const reply = data.reply as string || '';
          const requiresCommit = data.requires_commit as boolean || false;

          let currentIndex = 0;
          const typingSpeed = 20;
          
          const typeEffect = () => {
            if (currentIndex < reply.length) {
              const currentText = reply.substring(0, currentIndex + 1);
              setScheduleMessages(prev => prev.map(msg =>
                msg.id === aiTypingMessage.id
                  ? { ...msg, content: currentText, isTyping: false, type: 'text' as const, requiresCommit: false }
                  : msg
              ));
              currentIndex++;
              setTimeout(typeEffect, typingSpeed);
            } else {
              setScheduleMessages(prev => prev.map(msg =>
                msg.id === aiTypingMessage.id
                  ? { ...msg, content: reply, isTyping: false, type: 'text' as const, requiresCommit }
                  : msg
              ));
              if (requiresCommit) checkDraftDirty();
            }
          };
          typeEffect();
        } else if (eventType === 'error') {
          const errorMsg = data.message as string || '处理请求时出错';
          setScheduleMessages(prev => prev.map(msg =>
            msg.id === aiTypingMessage.id
              ? { ...msg, content: `❌ ${errorMsg}`, isTyping: false, type: 'text' as const }
              : msg
          ));
        }
      }
    } catch (error) {
      console.error('Chat API error:', error);
      const errMsg = error instanceof Error ? error.message : '';
      const displayMsg = errMsg.includes('未配置 API Key')
        ? `⚠️ **未配置 API Key**\n\n请前往个人中心 → API 配置 填入有效的 API 密钥后再试。`
        : '抱歉，处理您的请求时出错了。请确认后端服务是否已启动。';
      setScheduleMessages(prev => prev.map(msg =>
        msg.id === aiTypingMessage.id
          ? { ...msg, content: displayMsg, isTyping: false, type: 'text' as const }
          : msg
      ));
    } finally {
      setIsChatLoading(false);
      if (chatTimeoutRef.current) {
        clearTimeout(chatTimeoutRef.current);
        chatTimeoutRef.current = null;
      }
    }
  };

  const handleRetry = async () => {
    setShowRetry(false);
    try { await resetAgent(); } catch {}
    setScheduleMessages(prev => {
      const lastTyping = prev.find(m => m.isTyping);
      if (lastTyping) {
        return prev.map(m => m.id === lastTyping.id ? { ...m, content: '已重置，请重新发送消息。', isTyping: false, type: 'text' as const } : m);
      }
      return prev;
    });
    setIsChatLoading(false);
  };

  const handleAddEvent = () => {
    setCurrentEvent(null);
    setIsEditing(false);
    setShowEventForm(true);
  };

  const handleEditEvent = (event: UICalendarEvent) => {
    setCurrentEvent(event);
    setIsEditing(true);
    setShowEventForm(true);
  };

  const handleDeleteEvent = async (eventId: string) => {
    try {
      await deleteEvent(eventId);
      await commitDraft();
      setDraftDirty(null);
      await loadCalendarData();
    } catch (error) {
      console.error('Delete event error:', error);
    }
    setShowEventDetail(false);
  };

  const handleSubmitEvent = async (data: { scheduled_start: Date; deadline: Date; title: string; description?: string; location?: string; priority?: string; status?: string; color_tag: string; tags: string[] }) => {
    try {
      if (isEditing && currentEvent) {
        const req: UpdateEventRequest = {
          title: data.title, description: data.description,
          scheduled_start: data.scheduled_start.toISOString(), deadline: data.deadline.toISOString(),
          location: data.location, priority: data.priority, status: data.status,
          color_tag: data.color_tag, tags: data.tags,
        };
        await updateEvent(currentEvent.id, req);
      } else {
        const req: CreateEventRequest = {
          title: data.title, source: 'personal',
          scheduled_start: data.scheduled_start.toISOString(), deadline: data.deadline.toISOString(),
          description: data.description, location: data.location, priority: data.priority,
          status: data.status, category: 'schedulable', color_tag: data.color_tag, tags: data.tags,
        };
        await createEvent(req);
      }
      await fetchCalendarDiff();
    } catch (error) {
      console.error('Submit event error:', error);
    }
    setShowEventForm(false);
  };

  const handleSelectEvent = (event: UICalendarEvent | null) => {
    setSelectedEvent(event);
    setShowEventDetail(!!event);
  };

  const handleCommitDraft = async () => {
    try {
      await commitDraft();
      setDraftDirty(null);
      await loadCalendarData();
      setScheduleMessages(prev => prev.map(msg => msg.requiresCommit ? { ...msg, requiresCommit: false } : msg));
    } catch (error) {
      console.error('Commit error:', error);
    }
  };

  const handleResetDraft = async () => {
    try {
      await resetDraft();
      setDraftDirty(null);
      setScheduleMessages(prev => prev.map(msg => msg.requiresCommit ? { ...msg, requiresCommit: false } : msg));
    } catch (error) {
      console.error('Reset draft error:', error);
    }
  };

  const fetchCalendarDiff = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/calendar/diff');
      if (!response.ok) throw new Error('Failed to fetch calendar diff');
      const data = await response.json();
      setCalendarDiff(data);
      setShowDiff(true);
    } catch (error) {
      console.error('Fetch calendar diff error:', error);
    }
  };

  const handleEditDiffEvent = (event: any) => {
    setShowDiff(false);
    const uiEvent: UICalendarEvent = {
      id: event.id, title: event.title, description: event.description, source: event.source,
      scheduled_start: new Date(event.scheduled_start), deadline: new Date(event.deadline),
      duration: event.duration, computed_end_time: event.computed_end_time ? new Date(event.computed_end_time) : undefined,
      location: event.location, priority: event.priority, status: event.status,
      category: event.category, color_tag: event.color_tag, recurring_rule: event.recurring_rule,
      metadata: event.metadata || {}, tags: event.tags || [],
      created_at: event.created_at ? new Date(event.created_at) : undefined,
      updated_at: event.updated_at ? new Date(event.updated_at) : undefined,
      duration_minutes: event.duration_minutes || 0, is_feasible: event.is_feasible ?? true,
      is_overdue: event.is_overdue ?? false, is_recurring: event.is_recurring ?? false, is_draft_modified: false
    };
    setCurrentEvent(uiEvent);
    setIsEditing(true);
    setShowEventForm(true);
  };

  const renderScheduleChatMessages = () => (
    <div className="space-y-3">
      {scheduleMessages.map(message => (
        <div key={message.id} className={`${message.isUser ? 'text-right' : 'text-left'}`}>
          {message.type === 'tool' && message.toolCall ? (
            <div className="inline-block text-left max-w-full">
              <div className="px-3 py-2 rounded-lg bg-purple-100 dark:bg-purple-900/40 border border-purple-300 dark:border-purple-700 max-w-full overflow-hidden">
                <div className="font-medium text-sm text-purple-700 dark:text-purple-300 mb-1">🔧 {message.toolCall.name}</div>
                <div className="text-xs text-gray-700 dark:text-gray-300 font-mono overflow-x-auto">
                  {Object.entries(message.toolCall.args).map(([key, value]) => (
                    <div key={key} className="truncate">{key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}</div>
                  ))}
                </div>
              </div>
            </div>
          ) : message.type === 'thought' ? (
            <div className="inline-block text-left max-w-[90%]">
              <div className="px-3 py-2 rounded-lg bg-amber-100 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-700">
                <div className="font-medium text-sm text-amber-700 dark:text-amber-300 mb-1">💭 思考过程</div>
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
              </div>
            </div>
          ) : message.isUser ? (
            <div className="inline-block px-4 py-2.5 rounded-2xl bg-emerald-100/70 dark:bg-emerald-900/30 text-emerald-900 dark:text-emerald-100 text-sm max-w-[80%] break-words text-left backdrop-blur-sm">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          ) : (
            <div className="inline-block px-4 py-2.5 rounded-2xl bg-white dark:bg-gray-600 text-gray-800 dark:text-white text-sm max-w-[80%] shadow-sm whitespace-pre-wrap break-words">
              {message.isTyping ? (
                <span className="inline-flex gap-1">
                  <span className="animate-bounce">●</span>
                  <span className="animate-bounce" style={{ animationDelay: '0.1s' }}>●</span>
                  <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>●</span>
                </span>
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
          {!message.isUser && !message.isTyping && message.type === 'text' && message.requiresCommit && (
            <div className="flex gap-2 mt-2 justify-start">
              <button onClick={fetchCalendarDiff} className="px-3 py-1.5 text-xs bg-emerald-500 text-white rounded-md hover:bg-emerald-600 transition-colors font-medium">查看</button>
            </div>
          )}
        </div>
      ))}
      {showRetry && (
        <div className="text-center">
          <button onClick={handleRetry} className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-sm font-medium">响应超时，点击重试</button>
        </div>
      )}
      <div ref={scheduleChatEndRef} />
    </div>
  );

  const renderScheduleChatInput = () => (
    <div className="border-t border-gray-200/80 dark:border-gray-700/80 p-4">
      <div className="relative">
        <textarea rows={2} value={scheduleInputText} onChange={(e) => setScheduleInputText(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && !isChatLoading && sendScheduleMessage()}
          placeholder={isChatLoading ? "等待回复中..." : "给智能校园助手发送消息"} disabled={isChatLoading}
          className="w-full px-4 py-2.5 text-xs rounded-xl focus:outline-none dark:bg-gray-800 dark:text-white pr-12 resize-none border border-transparent focus:border-green-300 focus:ring-2 focus:ring-green-200/60 dark:focus:border-green-500/60 dark:focus:ring-green-500/20 dark:placeholder-gray-400 disabled:opacity-50" />
        <button onClick={sendScheduleMessage} disabled={isChatLoading || !scheduleInputText.trim()}
          className={`absolute right-3 top-1/2 transform -translate-y-1/2 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-50 ${scheduleInputText && !isChatLoading ? 'bg-green-500 text-white hover:bg-green-600' : 'bg-green-100 text-green-500 hover:bg-green-200'}`}>
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
          </svg>
        </button>
      </div>
    </div>
  );

  const renderScheduleChatEmpty = () => (
    <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
      <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold mb-2">你的日程助理已就绪</h3>
      <p className="text-center max-w-xs">您好！我可以帮你梳理日程安排、提醒关键节点，并协助你更高效地管理学习与生活。</p>
    </div>
  );

  const renderCalendarDiff = () => {
    if (!showDiff) return null;

    return (
      <div className="fixed inset-0 backdrop-blur-md flex items-center justify-center z-50 p-4">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-6xl transform transition-all duration-300 ease-out opacity-100 scale-100 translate-y-0"
          style={{ maxHeight: '90vh', overflow: 'auto' }}>
          <div className="sticky top-0 bg-white dark:bg-gray-800 px-6 py-5 border-b border-gray-100 dark:border-gray-700 z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-blue-100 dark:bg-blue-900/30">
                  <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-gray-900 dark:text-white">日历变更预览</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">查看并确认日历变更</p>
                </div>
              </div>
              <button onClick={() => setShowDiff(false)} className="p-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition-all duration-200 hover:rotate-90 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
          <div className="p-6 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="border border-green-200 dark:border-green-800 rounded-lg p-4">
                <h3 className="text-lg font-medium text-green-600 dark:text-green-400 mb-4 flex items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  新增事件 ({calendarDiff.new_events.length})
                </h3>
                <div className="space-y-3">
                  {calendarDiff.new_events.length === 0 ? (
                    <p className="text-gray-500 dark:text-gray-400 text-sm">无新增事件</p>
                  ) : (
                    calendarDiff.new_events.map((event, index) => (
                      <div key={event.id || index} className="bg-green-50 dark:bg-green-900/20 p-3 rounded-md">
                        <h4 className="font-medium text-gray-900 dark:text-white">{event.title}</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{new Date(event.scheduled_start).toLocaleString()}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">{event.location || '无地点'}</p>
                        <button className="mt-2 text-xs text-blue-600 dark:text-blue-400 hover:underline" onClick={() => handleEditDiffEvent(event)}>修改</button>
                      </div>
                    ))
                  )}
                </div>
              </div>
              <div className="border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                <h3 className="text-lg font-medium text-yellow-600 dark:text-yellow-400 mb-4 flex items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  修改事件 ({calendarDiff.modified_events.length})
                </h3>
                <div className="space-y-3">
                  {calendarDiff.modified_events.length === 0 ? (
                    <p className="text-gray-500 dark:text-gray-400 text-sm">无修改事件</p>
                  ) : (
                    calendarDiff.modified_events.map((event, index) => (
                      <div key={event.draft.id || index} className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-md">
                        <h4 className="font-medium text-gray-900 dark:text-white">{event.draft.title}</h4>
                        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1 space-y-1">
                          <p>原时间: {new Date(event.main.scheduled_start).toLocaleString()}</p>
                          <p>新时间: {new Date(event.draft.scheduled_start).toLocaleString()}</p>
                        </div>
                        <button className="mt-2 text-xs text-blue-600 dark:text-blue-400 hover:underline" onClick={() => handleEditDiffEvent(event.draft)}>修改</button>
                      </div>
                    ))
                  )}
                </div>
              </div>
              <div className="border border-red-200 dark:border-red-800 rounded-lg p-4">
                <h3 className="text-lg font-medium text-red-600 dark:text-red-400 mb-4 flex items-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  删除事件 ({calendarDiff.deleted_events.length})
                </h3>
                <div className="space-y-3">
                  {calendarDiff.deleted_events.length === 0 ? (
                    <p className="text-gray-500 dark:text-gray-400 text-sm">无删除事件</p>
                  ) : (
                    calendarDiff.deleted_events.map((event: any, index: number) => (
                      <div key={event.id || index} className="bg-red-50 dark:bg-red-900/20 p-3 rounded-md">
                        <h4 className="font-medium text-gray-900 dark:text-white line-through">{event.title}</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{new Date(event.scheduled_start).toLocaleString()}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
            <div className="flex gap-3 pt-4 border-t border-gray-100 dark:border-gray-700">
              <button onClick={async () => { await handleResetDraft(); setShowDiff(false); }} className="flex-1 px-6 py-3 border border-gray-200 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200 text-gray-700 dark:text-gray-300 font-medium">撤销更改</button>
              <button onClick={async () => { await handleCommitDraft(); setShowDiff(false); }} className="flex-1 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-xl hover:from-emerald-600 hover:to-teal-600 transition-all duration-200 font-medium shadow-lg shadow-emerald-500/25">保存更改</button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 h-full min-h-0">
        <div className="lg:col-span-2 h-full min-h-0 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500 dark:text-gray-400">加载日历数据中...</div>
            </div>
          ) : (
            <ModernCalendar
              events={events}
              onAddEvent={handleAddEvent}
              onSelectEvent={handleSelectEvent}
              draftDirty={draftDirty}
              onCommitDraft={handleCommitDraft}
              onResetDraft={handleResetDraft}
            />
          )}
        </div>
        <div className="flex flex-col h-full min-h-0">
          <div className="flex flex-col h-full min-h-0 bg-white/90 dark:bg-gray-900/80 rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200/80 dark:border-gray-700/80 flex-shrink-0">
              <h2 className="text-lg font-semibold text-gray-800 dark:text-white tracking-wide">日程助理</h2>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-4">
              {scheduleMessages.length === 0 ? renderScheduleChatEmpty() : renderScheduleChatMessages()}
            </div>
            {renderScheduleChatInput()}
          </div>
        </div>
      </div>

      {showEventForm && (
        <div className="fixed inset-0 backdrop-blur-md flex items-center justify-center z-50">
          <EventForm event={currentEvent || undefined} onSubmit={handleSubmitEvent} onCancel={() => setShowEventForm(false)} onAfterCancel={fetchCalendarDiff} />
        </div>
      )}

      {showEventDetail && selectedEvent && (
        <div className="fixed inset-0 backdrop-blur-md flex items-center justify-center z-50">
          <EventDetail event={selectedEvent} onEdit={() => { setShowEventDetail(false); handleEditEvent(selectedEvent); }} onDelete={() => handleDeleteEvent(selectedEvent.id)} onClose={() => setShowEventDetail(false)} />
        </div>
      )}

      {renderCalendarDiff()}
    </>
  );
};

export default SchedulePlanner;