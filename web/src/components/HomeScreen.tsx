import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowUp, ChevronDown, Clock, ArrowRight } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { LessonListItem, StepOut } from '../types/api';

const EXAMPLES = [
  {
    label: 'HTTP Requests and Responses',
    title: 'HTTP Requests and Responses',
    objective:
      'Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.',
  },
  {
    label: 'Simple vs Compound Interest',
    title: 'Simple vs Compound Interest',
    objective:
      'Calculate simple and compound interest for a given principal, rate, and time, and explain why compound interest grows faster.',
  },
];

interface EnrichedLessonItem extends LessonListItem {
  version_no?: number | null;
  model?: string | null;
  total_minutes?: number | null;
}

interface HomeScreenProps {
  onStartPipeline: (lessonId: number, initialSteps: StepOut[]) => void;
  onOpenLesson: (lessonId: number) => void;
  onNetworkError: (msg: string | null) => void;
  refreshTrigger?: number;
}

export const HomeScreen: React.FC<HomeScreenProps> = ({
  onStartPipeline,
  onOpenLesson,
  onNetworkError,
  refreshTrigger = 0,
}) => {
  const [title, setTitle] = useState('');
  const [objective, setObjective] = useState('');
  const [titleError, setTitleError] = useState<string | null>(null);
  const [objectiveError, setObjectiveError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [lessons, setLessons] = useState<EnrichedLessonItem[]>([]);
  const [loadingLessons, setLoadingLessons] = useState(true);
  const [lessonsError, setLessonsError] = useState<string | null>(null);

  // Auto-grow objective textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(76, Math.min(el.scrollHeight, 240))}px`;
  }, [objective]);

  // Close model info dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Load recent lessons + their version_no and actual model used
  const loadRecentLessons = async () => {
    setLoadingLessons(true);
    setLessonsError(null);
    try {
      const list = await api.listLessons();
      onNetworkError(null);
      const enriched = await Promise.all(
        list.map(async (item): Promise<EnrichedLessonItem> => {
          try {
            const detail = await api.getLesson(item.id);
            return {
              ...item,
              version_no: detail.version?.version_no ?? null,
              model: detail.generation?.model ?? null,
              total_minutes:
                detail.time_budget?.total_computed_min ??
                detail.version?.content?.total_minutes ??
                null,
            };
          } catch {
            return item;
          }
        })
      );
      setLessons(enriched);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isNetworkError) {
          onNetworkError(err.detail);
        }
        setLessonsError(err.detail);
      } else {
        setLessonsError(String(err));
      }
    } finally {
      setLoadingLessons(false);
    }
  };

  useEffect(() => {
    loadRecentLessons();
  }, [refreshTrigger]);

  const validateClient = (): boolean => {
    let valid = true;
    const cleanTitle = title.replace(/\s+/g, ' ').trim();
    const cleanObjective = objective.replace(/\s+/g, ' ').trim();

    setTitleError(null);
    setObjectiveError(null);
    setGeneralError(null);

    if (!cleanTitle) {
      setTitleError('Title is required.');
      valid = false;
    } else if (cleanTitle.length < 3) {
      setTitleError('Title is too short (minimum 3 characters).');
      valid = false;
    } else if (cleanTitle.length > 200) {
      setTitleError('Title is too long (maximum 200 characters).');
      valid = false;
    } else if (!/[A-Za-z0-9]/.test(cleanTitle)) {
      setTitleError('Title must contain letters or numbers.');
      valid = false;
    }

    if (!cleanObjective) {
      setObjectiveError('Learning objective is required.');
      valid = false;
    } else if (cleanObjective.length < 15) {
      setObjectiveError('Learning objective is too short (minimum 15 characters).');
      valid = false;
    } else if (cleanObjective.length > 1000) {
      setObjectiveError('Learning objective is too long (maximum 1000 characters).');
      valid = false;
    } else if (!/[A-Za-z0-9]/.test(cleanObjective)) {
      setObjectiveError('Learning objective must contain letters or numbers.');
      valid = false;
    }

    return valid;
  };

  const handleSubmit = async () => {
    if (submitting) return;
    if (!validateClient()) return;

    setSubmitting(true);
    try {
      const created = await api.createLesson(title, objective);
      onNetworkError(null);
      await api.runLesson(created.id);
      onStartPipeline(created.id, created.steps || []);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isNetworkError) {
          onNetworkError(err.detail);
        }
        if (err.fieldErrors.title) {
          setTitleError(err.fieldErrors.title);
        }
        if (err.fieldErrors.objective) {
          setObjectiveError(err.fieldErrors.objective);
        }
        if (!err.fieldErrors.title && !err.fieldErrors.objective) {
          setGeneralError(err.detail);
        }
      } else {
        setGeneralError(String(err));
      }
      setSubmitting(false);
    }
  };

  const handleKeyDownTitle = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleKeyDownObjective = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const fillExample = (ex: (typeof EXAMPLES)[number]) => {
    setTitle(ex.title);
    setObjective(ex.objective);
    setTitleError(null);
    setObjectiveError(null);
    setGeneralError(null);
  };

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAF8] text-[#1C1D1F] flex flex-col">
      {/* Top-left small logo wordmark */}
      <header className="w-full px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-[2px] bg-[#0B4F8A] inline-block" />
          <span className="font-serif text-[18px] font-semibold tracking-tight text-[#1C1D1F]">
            Lesson Studio
          </span>
        </div>
      </header>

      {/* Main centered workspace */}
      <main className="flex-1 w-full max-w-[680px] mx-auto px-4 sm:px-6 pt-8 pb-16 flex flex-col justify-center">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
        >
          {/* Calm one-line heading */}
          <h1 className="font-serif text-[28px] sm:text-[32px] font-normal text-[#1C1D1F] text-center mb-6 leading-snug">
            What do you want to teach today?
          </h1>

          {/* Composer Card */}
          <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-4 sm:p-5 transition-colors focus-within:border-[#1C1D1F]/40">
            {/* Lesson Title Input */}
            <div>
              <label
                htmlFor="lesson-title-input"
                className="block text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-1"
              >
                Lesson title
              </label>
              <input
                id="lesson-title-input"
                type="text"
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  if (titleError) setTitleError(null);
                }}
                onKeyDown={handleKeyDownTitle}
                placeholder="e.g., HTTP Requests and Responses"
                className="w-full bg-transparent text-[16px] font-medium text-[#1C1D1F] placeholder:text-[#76787C]/70 focus:outline-none py-1 border-b border-[#E4E4E0] focus:border-[#0B4F8A] transition-colors"
              />
              {titleError && (
                <p
                  role="alert"
                  className="mt-1.5 text-[13px] text-[#B42318] font-normal leading-snug"
                >
                  {titleError}
                </p>
              )}
            </div>

            {/* Learning Objective Textarea */}
            <div className="mt-4">
              <label
                htmlFor="lesson-objective-input"
                className="block text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-1"
              >
                Learning objective
              </label>
              <textarea
                id="lesson-objective-input"
                ref={textareaRef}
                rows={3}
                value={objective}
                onChange={(e) => {
                  setObjective(e.target.value);
                  if (objectiveError) setObjectiveError(null);
                }}
                onKeyDown={handleKeyDownObjective}
                placeholder="Start with an action verb (explain, calculate, distinguish) describing what learners will achieve in 45 minutes…"
                className="w-full bg-transparent text-[15.5px] text-[#1C1D1F] placeholder:text-[#76787C]/70 focus:outline-none resize-none leading-relaxed py-1"
              />
              {objectiveError && (
                <p
                  role="alert"
                  className="mt-1 text-[13px] text-[#B42318] font-normal leading-snug"
                >
                  {objectiveError}
                </p>
              )}
            </div>

            {generalError && (
              <p
                role="alert"
                className="mt-2 text-[13px] text-[#B42318] bg-[#FDECEB] border border-[#F5BDBA] rounded-[6px] px-3 py-2"
              >
                {generalError}
              </p>
            )}

            {/* Composer Footer: Example Chips (bottom-left) & Model Chip + Send Button (bottom-right) */}
            <div className="mt-4 pt-3 border-t border-[#E4E4E0] flex flex-wrap items-center justify-between gap-3">
              {/* Bottom-left: Two small example chips */}
              <div className="flex flex-wrap items-center gap-1.5">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.label}
                    type="button"
                    onClick={() => fillExample(ex)}
                    className="text-[12.5px] text-[#525458] hover:text-[#1C1D1F] bg-[#FAFAF8] hover:bg-[#F3F3EF] border border-[#E4E4E0] rounded-[6px] px-2.5 py-1 transition-colors duration-150"
                  >
                    {ex.label}
                  </button>
                ))}
              </div>

              {/* Bottom-right: Informational Model Chip + Circular Send Button */}
              <div className="flex items-center gap-2.5 ml-auto">
                <div className="relative" ref={dropdownRef}>
                  <button
                    type="button"
                    onClick={() => setModelDropdownOpen((prev) => !prev)}
                    aria-expanded={modelDropdownOpen}
                    className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-[#525458] hover:text-[#1C1D1F] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[6px] px-2.5 py-1 transition-colors"
                  >
                    <span>Gemini</span>
                    <ChevronDown className="w-3.5 h-3.5 text-[#76787C]" />
                  </button>

                  {modelDropdownOpen && (
                    <div className="absolute right-0 bottom-full mb-1.5 w-64 bg-white border border-[#E4E4E0] rounded-[6px] p-2 z-30 shadow-sm text-left">
                      <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-[#76787C]">
                        Backend Model Routing
                      </div>
                      <div className="mt-1 space-y-1">
                        <div className="flex items-center justify-between px-2 py-1.5 rounded-[4px] bg-[#EDF4FA]/60 text-[13px] text-[#1C1D1F] font-medium">
                          <span>Gemini (primary)</span>
                          <span className="text-[11px] font-mono text-[#0B4F8A]">Active</span>
                        </div>
                        <div className="flex items-center justify-between px-2 py-1.5 rounded-[4px] text-[13px] text-[#525458]">
                          <span>Groq (fallback)</span>
                          <span className="text-[11px] font-mono text-[#76787C]">Auto</span>
                        </div>
                      </div>
                      <p className="mt-2 pt-2 border-t border-[#E4E4E0] px-2 text-[11.5px] text-[#76787C] leading-snug">
                        Informational only. Model selection is configured on the server; the actual model that ran is shown on each lesson.
                      </p>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={submitting}
                  aria-label="Create and generate lesson"
                  className="w-9 h-9 rounded-full bg-[#0B4F8A] hover:bg-[#083D6B] text-white flex items-center justify-center transition-colors duration-150 disabled:opacity-50 shrink-0"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Recent Lessons List */}
          <section className="mt-10" aria-labelledby="recent-lessons-heading">
            <div className="flex items-center justify-between mb-3">
              <h2
                id="recent-lessons-heading"
                className="text-[12.5px] font-semibold uppercase tracking-wider text-[#525458]"
              >
                Recent lessons
              </h2>
              {lessons.length > 0 && (
                <span className="text-[12px] text-[#76787C]">
                  {lessons.length} {lessons.length === 1 ? 'lesson' : 'lessons'}
                </span>
              )}
            </div>

            {loadingLessons ? (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-4 text-[14px] text-[#76787C]">
                Loading recent lessons…
              </div>
            ) : lessonsError ? (
              <div className="bg-white border border-[#F5BDBA] rounded-[8px] p-4 flex items-center justify-between gap-4">
                <p className="text-[13.5px] text-[#B42318]">{lessonsError}</p>
                <button
                  type="button"
                  onClick={loadRecentLessons}
                  className="px-3 py-1.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8] hover:bg-[#F3F3EF] text-[13px] font-medium text-[#1C1D1F] shrink-0"
                >
                  Retry
                </button>
              </div>
            ) : lessons.length === 0 ? (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-5 text-[14px] text-[#76787C]">
                No lessons have been created yet. Pick an example chip above or enter a topic to generate your first lesson.
              </div>
            ) : (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] divide-y divide-[#E4E4E0] overflow-hidden">
                {lessons.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onOpenLesson(item.id)}
                    className="w-full px-4 py-3.5 text-left hover:bg-[#F3F3EF]/70 transition-colors duration-150 flex items-center justify-between gap-4 group"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2.5">
                        <span className="font-serif text-[16px] font-medium text-[#1C1D1F] group-hover:text-[#0B4F8A] transition-colors truncate">
                          {item.title}
                        </span>
                        {item.version_no != null && (
                          <span className="font-mono text-[11.5px] font-medium text-[#525458] bg-[#FAFAF8] border border-[#E4E4E0] px-1.5 py-0.5 rounded-[4px] shrink-0">
                            v{item.version_no}
                          </span>
                        )}
                        {item.status === 'failed' && (
                          <span className="text-[11px] font-medium text-[#B42318] bg-[#FDECEB] border border-[#F5BDBA] px-1.5 py-0.5 rounded-[4px] shrink-0">
                            Failed
                          </span>
                        )}
                        {item.status === 'running' && (
                          <span className="text-[11px] font-medium text-[#0B4F8A] bg-[#EDF4FA] border border-[#0B4F8A]/30 px-1.5 py-0.5 rounded-[4px] shrink-0">
                            Running
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-[#76787C]">
                        <span>{formatDate(item.updated_at)}</span>
                        {item.total_minutes != null && (
                          <span className="inline-flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span>{item.total_minutes} min</span>
                          </span>
                        )}
                        {item.model && (
                          <span className="font-mono text-[11.5px] text-[#525458]">
                            Model: {item.model}
                          </span>
                        )}
                      </div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-[#76787C] group-hover:text-[#0B4F8A] group-hover:translate-x-0.5 transition-all shrink-0" />
                  </button>
                ))}
              </div>
            )}
          </section>
        </motion.div>
      </main>
    </div>
  );
};
