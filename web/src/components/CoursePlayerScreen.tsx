import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Clock,
  Download,
  ExternalLink,
  History,
  Loader2,
  Menu,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  AlertCircle,
  BookOpen,
  Video as VideoIcon,
  Globe,
} from 'lucide-react';
import { api, ApiError } from '../api/client';
import {
  LessonDetailResponse,
  LessonSection,
  PreviewFixResponse,
  QCIssueItem,
  QCLayer,
  QCResponse,
  QuizItem,
  SectionType,
  SourceItem,
  StepOut,
  VersionAuthor,
  VersionSummary,
} from '../types/api';
import { MarkdownWithCitations, TIER_LABELS } from './MarkdownWithCitations';
import { QualityReviewDrawer, ReviewTab } from './QualityReviewDrawer';
import { FixDiffModal } from './FixDiffModal';
import { ExportModal } from './ExportModal';

const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  hook: 'Hook',
  concept: 'Concept',
  example: 'Example',
  activity: 'Activity',
  video: 'Video',
  knowledge_check: 'Knowledge check',
  summary: 'Summary',
};

const AUTHOR_LABELS: Record<VersionAuthor, string> = {
  ai: 'AI',
  instructor: 'Instructor',
  qc_fix: 'QC fix',
};

function extractYouTubeId(url: string | null | undefined, metaVideoId?: string): string | null {
  if (metaVideoId) return metaVideoId;
  if (!url) return null;
  const regExp = /(?:youtube\.com\/(?:watch\?v=|embed\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/;
  const match = url.match(regExp);
  return match ? match[1] : null;
}

interface CoursePlayerScreenProps {
  lessonId: number;
  onBackHome: () => void;
  onNetworkError: (msg: string | null) => void;
}

export const CoursePlayerScreen: React.FC<CoursePlayerScreenProps> = ({
  lessonId,
  onBackHome,
  onNetworkError,
}) => {
  const [data, setData] = useState<LessonDetailResponse | null>(null);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [qc, setQc] = useState<QCResponse>({ factual: null, instructional: null });
  const [steps, setSteps] = useState<StepOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Navigation & UI state
  const [mode, setMode] = useState<'preview' | 'edit'>('preview');
  const [currentIndex, setCurrentIndex] = useState(0); // 0..sections.length (where sections.length === References)
  const [completedIndices, setCompletedIndices] = useState<Set<number>>(() => new Set([0]));
  const [mobileCurriculumOpen, setMobileCurriculumOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 1024 : true
  );
  const [reviewTab, setReviewTab] = useState<ReviewTab>('qc1');
  const [versionMenuOpen, setVersionMenuOpen] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const versionMenuRef = useRef<HTMLDivElement | null>(null);

  // Interactive Quiz answers in Preview mode: questionIndex -> selectedOption
  const [selectedQuizAnswers, setSelectedQuizAnswers] = useState<Record<number, string>>({});

  // Edit Mode state (never lost on save error)
  const [editedSections, setEditedSections] = useState<
    Record<string, { heading: string; content_md: string }>
  >({});
  const [editedQuiz, setEditedQuiz] = useState<Record<number, QuizItem>>({});
  const [dirtySectionIds, setDirtySectionIds] = useState<Set<string>>(() => new Set());
  const [dirtyQuizIndices, setDirtyQuizIndices] = useState<Set<number>>(() => new Set());
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [savedVersionNo, setSavedVersionNo] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);
  const autosaveTimerRef = useRef<number | null>(null);

  // QC / Pipeline action states
  const [rerunningLayer, setRerunningLayer] = useState<QCLayer | null>(null);
  const [retryingStep, setRetryingStep] = useState<string | null>(null);
  const [previewingIssueId, setPreviewingIssueId] = useState<number | null>(null);
  const [issueErrors, setIssueErrors] = useState<Record<number, string>>({});
  const [activeFixModal, setActiveFixModal] = useState<{
    issue: QCIssueItem;
    fix: PreviewFixResponse;
  } | null>(null);
  const [applyingFix, setApplyingFix] = useState(false);
  const [dismissingFix, setDismissingFix] = useState(false);
  const [fixModalError, setFixModalError] = useState<string | null>(null);

  // Sync editor buffers from a loaded version
  const initEditorFromVersion = useCallback((detail: LessonDetailResponse) => {
    const content = detail.version?.content;
    if (!content) return;
    const secMap: Record<string, { heading: string; content_md: string }> = {};
    for (const sec of content.sections) {
      secMap[sec.id] = { heading: sec.heading, content_md: sec.content_md };
    }
    const quizMap: Record<number, QuizItem> = {};
    content.knowledge_check.forEach((q, idx) => {
      quizMap[idx] = { ...q, options: [...q.options] };
    });
    setEditedSections(secMap);
    setEditedQuiz(quizMap);
    setDirtySectionIds(new Set());
    setDirtyQuizIndices(new Set());
  }, []);

  const loadAll = useCallback(
    async (reinitEditor = true) => {
      setLoadError(null);
      try {
        const [lessonRes, versionsRes, qcRes, stepsRes] = await Promise.all([
          api.getLesson(lessonId),
          api.listVersions(lessonId),
          api.getQC(lessonId),
          api.getSteps(lessonId, false),
        ]);
        onNetworkError(null);
        setData(lessonRes);
        setVersions(versionsRes);
        setQc(qcRes);
        setSteps(stepsRes);
        if (reinitEditor) {
          initEditorFromVersion(lessonRes);
        }
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.isNetworkError) onNetworkError(err.detail);
          setLoadError(err.detail);
        } else {
          setLoadError(String(err));
        }
      } finally {
        setLoading(false);
      }
    },
    [lessonId, initEditorFromVersion, onNetworkError]
  );

  useEffect(() => {
    setLoading(true);
    loadAll(true);
  }, [loadAll]);

  // Close version menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (versionMenuRef.current && !versionMenuRef.current.contains(e.target as Node)) {
        setVersionMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const sections: LessonSection[] = data?.version?.content?.sections || [];
  const totalItems = sections.length + 1; // +1 for References item at the end
  const isReferencesView = currentIndex === sections.length;
  const activeSection: LessonSection | undefined = sections[currentIndex];

  const sourcesBySid = useMemo(() => {
    const map: Record<string, SourceItem> = {};
    for (const s of data?.sources || []) {
      map[s.sid] = s;
    }
    return map;
  }, [data?.sources]);

  // Navigate to section index and mark visited
  const goToIndex = useCallback(
    (idx: number) => {
      const clamped = Math.max(0, Math.min(idx, totalItems - 1));
      setCurrentIndex(clamped);
      setCompletedIndices((prev) => {
        const next = new Set(prev);
        next.add(clamped);
        return next;
      });
      setMobileCurriculumOpen(false);
    },
    [totalItems]
  );

  // Keyboard Left/Right navigation in Preview mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (mode !== 'preview' || activeFixModal || exportModalOpen) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'ArrowRight' && currentIndex < totalItems - 1) {
        e.preventDefault();
        goToIndex(currentIndex + 1);
      } else if (e.key === 'ArrowLeft' && currentIndex > 0) {
        e.preventDefault();
        goToIndex(currentIndex - 1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mode, activeFixModal, exportModalOpen, currentIndex, totalItems, goToIndex]);

  // Jump from QC issue or claim location (e.g. "sec-4", "quiz-Q2", "Q1") to corresponding section
  const handleJumpToLocation = useCallback(
    (location: string) => {
      if (!location) return;
      const secMatch = location.match(/sec-\d+/);
      if (secMatch) {
        const idx = sections.findIndex((s) => s.id === secMatch[0]);
        if (idx !== -1) {
          goToIndex(idx);
          return;
        }
      }
      if (location.toLowerCase().includes('quiz') || /^Q\d+$/i.test(location)) {
        const kcIdx = sections.findIndex((s) => s.type === 'knowledge_check');
        if (kcIdx !== -1) {
          goToIndex(kcIdx);
        }
      }
    },
    [sections, goToIndex]
  );

  // Perform Autosave (or Retry save) via PUT /lessons/{id}/content
  const performSave = useCallback(
    async (secIdsToSave: Set<string>, quizIndicesToSave: Set<number>) => {
      if (secIdsToSave.size === 0 && quizIndicesToSave.size === 0) return;

      const sectionsPayload: Record<string, { content_md: string; heading?: string | null }> = {};
      secIdsToSave.forEach((id) => {
        const edited = editedSections[id];
        if (edited) {
          sectionsPayload[id] = {
            content_md: edited.content_md,
            heading: edited.heading,
          };
        }
      });

      const quizPayload: Record<number, QuizItem> = {};
      quizIndicesToSave.forEach((idx) => {
        const q = editedQuiz[idx];
        if (q) {
          quizPayload[idx] = q;
        }
      });

      setSaveStatus('saving');
      setSaveError(null);
      try {
        const res = await api.editContent(lessonId, {
          sections: sectionsPayload,
          quiz: quizPayload,
        });
        onNetworkError(null);
        setSavedVersionNo(res.version_no);
        setSaveStatus('saved');
        setDirtySectionIds(new Set());
        setDirtyQuizIndices(new Set());
        // Refresh lesson data and version history without wiping active typing buffer
        await loadAll(false);
      } catch (err) {
        setSaveStatus('error');
        if (err instanceof ApiError) {
          if (err.isNetworkError) onNetworkError(err.detail);
          setSaveError(err.detail);
        } else {
          setSaveError(String(err));
        }
      }
    },
    [editedSections, editedQuiz, lessonId, loadAll, onNetworkError]
  );

  // Debounced autosave 1s after typing stops
  useEffect(() => {
    if (dirtySectionIds.size === 0 && dirtyQuizIndices.size === 0) return;
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
    }
    autosaveTimerRef.current = window.setTimeout(() => {
      performSave(new Set(dirtySectionIds), new Set(dirtyQuizIndices));
    }, 1000);

    return () => {
      if (autosaveTimerRef.current) {
        clearTimeout(autosaveTimerRef.current);
      }
    };
  }, [editedSections, editedQuiz, dirtySectionIds, dirtyQuizIndices, performSave]);

  const handleSectionChange = (sectionId: string, field: 'heading' | 'content_md', val: string) => {
    setEditedSections((prev) => ({
      ...prev,
      [sectionId]: {
        heading: prev[sectionId]?.heading ?? '',
        content_md: prev[sectionId]?.content_md ?? '',
        [field]: val,
      },
    }));
    setDirtySectionIds((prev) => {
      const next = new Set(prev);
      next.add(sectionId);
      return next;
    });
  };

  const handleQuizChange = (qIdx: number, updated: QuizItem) => {
    setEditedQuiz((prev) => ({
      ...prev,
      [qIdx]: updated,
    }));
    setDirtyQuizIndices((prev) => {
      const next = new Set(prev);
      next.add(qIdx);
      return next;
    });
  };

  const handleRestoreVersion = async (versionNo: number) => {
    setRestoringVersion(versionNo);
    try {
      const res = await api.restoreVersion(lessonId, versionNo);
      setSavedVersionNo(res.version_no);
      setSaveStatus('saved');
      setVersionMenuOpen(false);
      await loadAll(true);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setSaveError(msg);
      setSaveStatus('error');
    } finally {
      setRestoringVersion(null);
    }
  };

  // Poll steps until running finishes (used when re-running QC or retrying a step from the drawer)
  const pollUntilStepCompletes = useCallback(
    async (onFinished: () => void) => {
      const poll = async () => {
        try {
          const updatedSteps = await api.getSteps(lessonId, false);
          setSteps(updatedSteps);
          const stillRunning = updatedSteps.some(
            (s) => s.status === 'running' || s.status === 'pending'
          );
          if (stillRunning) {
            window.setTimeout(poll, 2000);
          } else {
            await loadAll(false);
            onFinished();
          }
        } catch {
          onFinished();
        }
      };
      window.setTimeout(poll, 1500);
    },
    [lessonId, loadAll]
  );

  const handleRerunQC = async (layer: QCLayer) => {
    setRerunningLayer(layer);
    try {
      await api.rerunQC(lessonId, layer);
      pollUntilStepCompletes(() => setRerunningLayer(null));
    } catch (err) {
      setRerunningLayer(null);
      if (err instanceof ApiError && err.isNetworkError) {
        onNetworkError(err.detail);
      }
    }
  };

  const handleRetryStep = async (stepName: string) => {
    setRetryingStep(stepName);
    try {
      await api.retryStep(lessonId, stepName);
      pollUntilStepCompletes(() => setRetryingStep(null));
    } catch (err) {
      setRetryingStep(null);
      if (err instanceof ApiError && err.isNetworkError) {
        onNetworkError(err.detail);
      }
    }
  };

  const handlePreviewFix = async (issue: QCIssueItem) => {
    setPreviewingIssueId(issue.id);
    setIssueErrors((prev) => {
      const next = { ...prev };
      delete next[issue.id];
      return next;
    });
    try {
      const fix = await api.previewFix(issue.id);
      setActiveFixModal({ issue, fix });
      setFixModalError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setIssueErrors((prev) => ({ ...prev, [issue.id]: msg }));
    } finally {
      setPreviewingIssueId(null);
    }
  };

  const handleApplyFix = async () => {
    if (!activeFixModal) return;
    const { issue, fix } = activeFixModal;
    setApplyingFix(true);
    setFixModalError(null);
    try {
      const payload =
        fix.kind === 'quiz' && fix.quiz_index != null && fix.after_item
          ? { quiz_index: fix.quiz_index, quiz_item: fix.after_item }
          : { section_id: fix.section_id, content_md: fix.after };
      const res = await api.applyFix(issue.id, payload);
      setSavedVersionNo(res.version_no);
      setSaveStatus('saved');
      setActiveFixModal(null);
      await loadAll(true);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setFixModalError(msg);
    } finally {
      setApplyingFix(false);
    }
  };

  const handleDismissIssue = async (issue: QCIssueItem) => {
    setDismissingFix(true);
    try {
      await api.dismissIssue(issue.id);
      if (activeFixModal?.issue.id === issue.id) {
        setActiveFixModal(null);
      }
      await loadAll(false);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      if (activeFixModal?.issue.id === issue.id) {
        setFixModalError(msg);
      } else {
        setIssueErrors((prev) => ({ ...prev, [issue.id]: msg }));
      }
    } finally {
      setDismissingFix(false);
    }
  };

  // Curriculum progress calculations
  const totalDeclaredMinutes = useMemo(
    () => Math.round(sections.reduce((acc, s) => acc + (s.minutes || 0), 0)),
    [sections]
  );
  const completedMinutes = useMemo(
    () =>
      Math.round(
        sections.reduce(
          (acc, s, idx) => (completedIndices.has(idx) ? acc + (s.minutes || 0) : acc),
          0
        )
      ),
    [sections, completedIndices]
  );
  const completedSectionsCount = useMemo(
    () => sections.filter((_, idx) => completedIndices.has(idx)).length,
    [sections, completedIndices]
  );
  const measuredTotalMin =
    data?.time_budget?.total_computed_min ??
    data?.version?.content?.total_minutes ??
    totalDeclaredMinutes;
  const budgetLimitMin = data?.time_budget?.budget_min ?? 45;

  const openIssuesCount = useMemo(() => {
    const fOpen = (qc.factual?.issues || []).filter((i) => i.status === 'open').length;
    const iOpen = (qc.instructional?.issues || []).filter((i) => i.status === 'open').length;
    return fOpen + iOpen;
  }, [qc]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center p-6">
        <div className="flex items-center gap-2.5 text-[15px] text-[#525458]">
          <Loader2 className="w-4 h-4 animate-spin text-[#0B4F8A]" />
          <span>Loading lesson workspace…</span>
        </div>
      </div>
    );
  }

  if (loadError || !data) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center p-6">
        <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-6 max-w-md w-full">
          <div className="flex items-start gap-3 text-[#B42318]">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <h2 className="font-serif text-[18px] font-semibold text-[#1C1D1F]">
                Could not load lesson
              </h2>
              <p className="mt-1.5 text-[13.5px] text-[#B42318]">{loadError}</p>
              <div className="mt-4 flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => loadAll(true)}
                  className="px-3.5 py-2 rounded-[6px] bg-[#0B4F8A] text-white text-[13.5px] font-medium"
                >
                  Retry
                </button>
                <button
                  type="button"
                  onClick={onBackHome}
                  className="px-3.5 py-2 rounded-[6px] border border-[#E4E4E0] bg-white text-[#1C1D1F] text-[13.5px] font-medium"
                >
                  Back to home
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const version = data.version;

  return (
    <div className="h-screen bg-[#FAFAF8] text-[#1C1D1F] flex flex-col overflow-hidden">
      {/* TOP BAR */}
      <header className="min-h-14 py-2 sm:py-0 sm:h-14 bg-white border-b border-[#E4E4E0] px-3 sm:px-5 flex flex-wrap sm:flex-nowrap items-center justify-between gap-2 shrink-0 z-30">
        {/* Left: Back button, mobile curriculum menu, Lesson title, 45-min badge */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 w-full sm:w-auto sm:flex-1">
          <button
            type="button"
            onClick={onBackHome}
            aria-label="Back to home"
            className="p-1.5 rounded-[6px] text-[#525458] hover:text-[#1C1D1F] hover:bg-[#F3F3EF] transition-colors shrink-0"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={() => setMobileCurriculumOpen((prev) => !prev)}
            aria-label="Toggle curriculum sidebar"
            className="lg:hidden p-1.5 rounded-[6px] text-[#525458] hover:text-[#1C1D1F] hover:bg-[#F3F3EF] shrink-0"
          >
            <Menu className="w-4 h-4" />
          </button>

          <h1 className="font-serif text-[16px] sm:text-[18px] font-semibold text-[#1C1D1F] truncate">
            {data.lesson.title}
          </h1>

          {/* "45 min" style badge with the measured total */}
          <span
            title={`Measured duration: ${measuredTotalMin} min (budget: ${budgetLimitMin} min)`}
            className={`hidden sm:inline-flex items-center gap-1 font-mono text-[12px] font-medium px-2 py-0.5 rounded-[4px] border shrink-0 ${
              data.time_budget?.over_budget
                ? 'bg-[#FDF5E6] text-[#A86A00] border-[#F0D49B]'
                : 'bg-[#FAFAF8] text-[#525458] border-[#E4E4E0]'
            }`}
          >
            <Clock className="w-3 h-3" />
            <span>
              {measuredTotalMin} / {budgetLimitMin} min
            </span>
          </span>
        </div>

        {/* Right: Save Status, Version Selector, Preview | Edit Toggle, Quality Review Toggle, Export */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Quiet Autosave Indicator */}
          {saveStatus === 'saving' && (
            <span className="hidden md:inline-flex items-center gap-1 text-[12px] text-[#525458]">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Saving…</span>
            </span>
          )}
          {saveStatus === 'saved' && savedVersionNo != null && (
            <span className="hidden md:inline-flex items-center gap-1 text-[12px] text-[#1E7B4F] font-medium">
              <Check className="w-3.5 h-3.5" />
              <span>Saved as version {savedVersionNo}</span>
            </span>
          )}
          {saveStatus === 'error' && (
            <div className="flex items-center gap-1.5 bg-[#FDECEB] border border-[#F5BDBA] px-2 py-1 rounded-[5px]">
              <span className="text-[11.5px] text-[#B42318] max-w-[180px] truncate" title={saveError || ''}>
                {saveError || 'Save failed'}
              </span>
              <button
                type="button"
                onClick={() => performSave(new Set(dirtySectionIds), new Set(dirtyQuizIndices))}
                className="text-[11.5px] font-semibold text-[#B42318] underline hover:no-underline shrink-0"
              >
                Retry save
              </button>
            </div>
          )}

          {/* Version Selector Dropdown */}
          {version && (
            <div className="relative" ref={versionMenuRef}>
              <button
                type="button"
                onClick={() => setVersionMenuOpen((prev) => !prev)}
                aria-label="Select or restore lesson version"
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8] hover:bg-[#F3F3EF] text-[12.5px] font-medium text-[#1C1D1F] transition-colors"
              >
                <History className="w-3.5 h-3.5 text-[#525458]" />
                <span className="font-mono">v{version.version_no}</span>
                <span className="hidden md:inline text-[#76787C]">
                  · {AUTHOR_LABELS[version.author] || version.author}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-[#76787C]" />
              </button>

              {versionMenuOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-80 bg-white border border-[#E4E4E0] rounded-[8px] shadow-sm z-40 overflow-hidden">
                  <div className="px-3.5 py-2.5 bg-[#FAFAF8] border-b border-[#E4E4E0] text-[11.5px] font-semibold uppercase tracking-wider text-[#525458]">
                    Version History ({versions.length})
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-[#E4E4E0]">
                    {versions.map((v) => {
                      const isCurrent = v.version_no === version.version_no;
                      const formattedTime = new Date(v.created_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      });

                      return (
                        <div
                          key={v.version_no}
                          className={`p-3 text-[12.5px] flex items-start justify-between gap-2 ${
                            isCurrent ? 'bg-[#EDF4FA]/60' : 'hover:bg-[#FAFAF8]'
                          }`}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono font-semibold text-[#1C1D1F]">
                                v{v.version_no}
                              </span>
                              <span className="px-1.5 py-0.5 rounded-[4px] bg-white border border-[#E4E4E0] text-[11px] font-medium text-[#525458]">
                                {AUTHOR_LABELS[v.author] || v.author}
                              </span>
                              {isCurrent && (
                                <span className="text-[11px] font-semibold text-[#0B4F8A]">
                                  Latest
                                </span>
                              )}
                            </div>
                            {v.note && (
                              <p className="text-[12px] text-[#525458] mt-1 leading-snug">
                                {v.note}
                              </p>
                            )}
                            <div className="text-[11px] text-[#76787C] mt-1">{formattedTime}</div>
                          </div>

                          {!isCurrent && (
                            <button
                              type="button"
                              disabled={restoringVersion === v.version_no}
                              onClick={() => handleRestoreVersion(v.version_no)}
                              className="px-2.5 py-1 rounded-[5px] border border-[#E4E4E0] bg-white hover:bg-[#0B4F8A] hover:text-white hover:border-[#0B4F8A] text-[11.5px] font-medium text-[#1C1D1F] transition-colors shrink-0"
                            >
                              {restoringVersion === v.version_no ? 'Restoring…' : 'Restore'}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Preview | Edit Segmented Toggle */}
          <div
            role="group"
            aria-label="View mode toggle"
            className="inline-flex rounded-[6px] border border-[#E4E4E0] bg-[#F3F3EF] p-0.5 text-[12.5px] font-medium"
          >
            <button
              type="button"
              onClick={() => setMode('preview')}
              className={`px-2.5 py-1 rounded-[5px] transition-colors ${
                mode === 'preview'
                  ? 'bg-white text-[#1C1D1F] shadow-[0_1px_2px_rgba(0,0,0,0.05)] font-semibold'
                  : 'text-[#525458] hover:text-[#1C1D1F]'
              }`}
            >
              Preview
            </button>
            <button
              type="button"
              onClick={() => setMode('edit')}
              className={`px-2.5 py-1 rounded-[5px] transition-colors ${
                mode === 'edit'
                  ? 'bg-white text-[#1C1D1F] shadow-[0_1px_2px_rgba(0,0,0,0.05)] font-semibold'
                  : 'text-[#525458] hover:text-[#1C1D1F]'
              }`}
            >
              Edit
            </button>
          </div>

          {/* Export Button */}
          <button
            type="button"
            onClick={() => setExportModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[12.5px] font-medium transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export</span>
          </button>

          {/* Toggle Quality Review Drawer */}
          <button
            type="button"
            onClick={() => setRightDrawerOpen((prev) => !prev)}
            aria-label="Toggle quality review drawer"
            title="Toggle Quality review panel"
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] border text-[12.5px] font-medium transition-colors ${
              rightDrawerOpen
                ? 'border-[#0B4F8A]/40 bg-[#EDF4FA] text-[#0B4F8A]'
                : 'border-[#E4E4E0] bg-white text-[#525458] hover:text-[#1C1D1F]'
            }`}
          >
            {rightDrawerOpen ? (
              <PanelRightClose className="w-4 h-4" />
            ) : (
              <PanelRightOpen className="w-4 h-4" />
            )}
            <span className="hidden xl:inline">Quality review</span>
            {openIssuesCount > 0 && (
              <span className="font-mono text-[11px] px-1.5 py-0.2 rounded-full bg-[#FDF5E6] text-[#A86A00] border border-[#F0D49B]">
                {openIssuesCount}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* BODY: 3-Column Course Player Layout */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* LEFT SIDEBAR: CURRICULUM */}
        <aside
          aria-label="Lesson curriculum"
          className={`${
            mobileCurriculumOpen
              ? 'fixed inset-y-14 left-0 z-30 w-72 shadow-lg'
              : 'hidden lg:flex lg:w-72'
          } bg-white border-r border-[#E4E4E0] flex-col shrink-0 h-full overflow-hidden`}
        >
          {/* Progress header */}
          <div className="p-4 border-b border-[#E4E4E0] bg-[#FAFAF8]">
            <div className="flex items-center justify-between text-[11.5px] font-semibold uppercase tracking-wider text-[#525458] mb-1">
              <span>Curriculum</span>
              {data.generation?.model && (
                <span
                  className="font-mono text-[10.5px] normal-case text-[#76787C] truncate max-w-[130px]"
                  title={`Generated by ${data.generation.model}`}
                >
                  {data.generation.model}
                </span>
              )}
            </div>
            <div className="text-[12.5px] text-[#1C1D1F] font-medium">
              {completedSectionsCount} of {sections.length} · {completedMinutes} of{' '}
              {totalDeclaredMinutes} min
            </div>
            <div className="mt-2 h-1.5 w-full bg-[#E4E4E0] rounded-full overflow-hidden">
              <div
                style={{
                  width: `${
                    sections.length > 0
                      ? Math.min(100, Math.round((completedSectionsCount / sections.length) * 100))
                      : 0
                  }%`,
                }}
                className="h-full bg-[#0B4F8A] transition-all duration-200"
              />
            </div>
          </div>

          {/* Section List */}
          <nav className="flex-1 overflow-y-auto divide-y divide-[#E4E4E0]/70">
            {sections.map((sec, idx) => {
              const isCurrent = currentIndex === idx;
              const isDone = completedIndices.has(idx);
              return (
                <button
                  key={sec.id}
                  type="button"
                  onClick={() => goToIndex(idx)}
                  className={`w-full px-4 py-3 text-left transition-colors flex items-start gap-3 ${
                    isCurrent
                      ? 'bg-[#EDF4FA] border-l-[3px] border-l-[#0B4F8A]'
                      : 'hover:bg-[#FAFAF8]'
                  }`}
                >
                  <span
                    className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-mono shrink-0 border ${
                      isCurrent
                        ? 'bg-[#0B4F8A] text-white border-[#0B4F8A]'
                        : isDone
                        ? 'bg-[#EAF4EE] text-[#1E7B4F] border-[#B8DFC9]'
                        : 'bg-white text-[#76787C] border-[#E4E4E0]'
                    }`}
                  >
                    {isDone && !isCurrent ? <Check className="w-3 h-3" /> : idx + 1}
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 text-[11px] text-[#76787C] uppercase tracking-wider font-semibold">
                      <span>{SECTION_TYPE_LABELS[sec.type] || sec.type}</span>
                      <span className="font-mono normal-case">{sec.minutes} min</span>
                    </div>
                    <div
                      className={`text-[13.5px] leading-snug mt-0.5 ${
                        isCurrent ? 'font-semibold text-[#0B4F8A]' : 'font-medium text-[#1C1D1F]'
                      }`}
                    >
                      {editedSections[sec.id]?.heading || sec.heading}
                    </div>
                  </div>
                </button>
              );
            })}

            {/* Last Item: References */}
            <button
              type="button"
              onClick={() => goToIndex(sections.length)}
              className={`w-full px-4 py-3 text-left transition-colors flex items-start gap-3 ${
                isReferencesView
                  ? 'bg-[#EDF4FA] border-l-[3px] border-l-[#0B4F8A]'
                  : 'hover:bg-[#FAFAF8]'
              }`}
            >
              <span
                className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-mono shrink-0 border ${
                  isReferencesView
                    ? 'bg-[#0B4F8A] text-white border-[#0B4F8A]'
                    : completedIndices.has(sections.length)
                    ? 'bg-[#EAF4EE] text-[#1E7B4F] border-[#B8DFC9]'
                    : 'bg-white text-[#76787C] border-[#E4E4E0]'
                }`}
              >
                {completedIndices.has(sections.length) && !isReferencesView ? (
                  <Check className="w-3 h-3" />
                ) : (
                  sections.length + 1
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2 text-[11px] text-[#76787C] uppercase tracking-wider font-semibold">
                  <span>Bibliography</span>
                  <span className="font-mono normal-case">{data.sources.length} sources</span>
                </div>
                <div
                  className={`text-[13.5px] leading-snug mt-0.5 ${
                    isReferencesView
                      ? 'font-semibold text-[#0B4F8A]'
                      : 'font-medium text-[#1C1D1F]'
                  }`}
                >
                  References
                </div>
              </div>
            </button>
          </nav>
        </aside>

        {/* MAIN COLUMN: PREVIEW OR EDIT */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 sm:py-8">
          {!version ? (
            <div className="max-w-[720px] mx-auto bg-white border border-[#E4E4E0] rounded-[8px] p-6 text-center">
              <p className="text-[15px] text-[#525458] mb-3">
                This lesson does not have a generated version yet.
              </p>
              <button
                type="button"
                onClick={() => handleRetryStep('plan')}
                className="px-4 py-2 rounded-[6px] bg-[#0B4F8A] text-white text-[13.5px] font-medium"
              >
                Run pipeline
              </button>
            </div>
          ) : mode === 'edit' ? (
            /* ================= EDIT MODE (Side-by-side Markdown + Live Preview) ================= */
            <div className="max-w-6xl mx-auto space-y-6">
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] px-5 py-3.5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-serif text-[18px] font-semibold text-[#1C1D1F]">
                    Instructor Editor · v{version.version_no}
                  </h2>
                  <p className="text-[13px] text-[#525458]">
                    Edits autosave 1 second after you stop typing and create a new version. Keep{' '}
                    <code className="font-mono text-[12px] bg-[#F3F3EF] px-1 py-0.5 rounded">
                      [S#]
                    </code>{' '}
                    citations attached to factual claims.
                  </p>
                </div>
                <div className="flex items-center gap-2 text-[12.5px]">
                  {saveStatus === 'saving' && (
                    <span className="inline-flex items-center gap-1.5 text-[#525458]">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-[#0B4F8A]" />
                      <span>Saving…</span>
                    </span>
                  )}
                  {saveStatus === 'saved' && savedVersionNo != null && (
                    <span className="inline-flex items-center gap-1.5 text-[#1E7B4F] font-medium bg-[#EAF4EE] border border-[#B8DFC9] px-2.5 py-1 rounded-[5px]">
                      <Check className="w-3.5 h-3.5" />
                      <span>Saved as version {savedVersionNo}</span>
                    </span>
                  )}
                  {saveStatus === 'error' && (
                    <div className="flex items-center gap-2 bg-[#FDECEB] border border-[#F5BDBA] px-3 py-1.5 rounded-[6px] text-[#B42318]">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{saveError}</span>
                      <button
                        type="button"
                        onClick={() =>
                          performSave(new Set(dirtySectionIds), new Set(dirtyQuizIndices))
                        }
                        className="px-2 py-0.5 rounded bg-white border border-[#F5BDBA] text-[#B42318] font-semibold text-[12px]"
                      >
                        Retry save
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Active section editor (or if on References, show first section + all sections below) */}
              {sections.map((sec, secIdx) => {
                const isSelected = currentIndex === secIdx;
                const editVal = editedSections[sec.id] || {
                  heading: sec.heading,
                  content_md: sec.content_md,
                };

                return (
                  <div
                    key={sec.id}
                    id={`editor-${sec.id}`}
                    className={`bg-white border rounded-[8px] overflow-hidden transition-colors ${
                      isSelected ? 'border-[#0B4F8A]' : 'border-[#E4E4E0]'
                    }`}
                  >
                    <div className="px-5 py-3 bg-[#FAFAF8] border-b border-[#E4E4E0] flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 flex-1 min-w-[240px]">
                        <span className="font-mono text-[12px] font-semibold text-[#0B4F8A] bg-[#EDF4FA] px-2 py-0.5 rounded-[4px]">
                          {sec.id}
                        </span>
                        <span className="text-[11.5px] font-semibold uppercase tracking-wider text-[#525458]">
                          {SECTION_TYPE_LABELS[sec.type]} · {sec.minutes} min
                        </span>
                        <input
                          type="text"
                          value={editVal.heading}
                          onChange={(e) =>
                            handleSectionChange(sec.id, 'heading', e.target.value)
                          }
                          aria-label={`Heading for ${sec.id}`}
                          className="flex-1 font-serif text-[16px] font-semibold text-[#1C1D1F] bg-white border border-[#E4E4E0] rounded-[5px] px-2.5 py-1 focus:outline-none focus:border-[#0B4F8A]"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-[#E4E4E0]">
                      {/* Left: Markdown Textarea */}
                      <div className="p-4 flex flex-col">
                        <label
                          htmlFor={`textarea-${sec.id}`}
                          className="text-[11px] font-semibold uppercase tracking-wider text-[#76787C] mb-1.5"
                        >
                          Markdown source
                        </label>
                        <textarea
                          id={`textarea-${sec.id}`}
                          value={editVal.content_md}
                          onChange={(e) =>
                            handleSectionChange(sec.id, 'content_md', e.target.value)
                          }
                          rows={Math.max(8, Math.min(22, editVal.content_md.split('\n').length + 2))}
                          className="w-full flex-1 font-mono text-[13.5px] leading-relaxed text-[#1C1D1F] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[6px] p-3 focus:outline-none focus:border-[#0B4F8A] resize-y"
                        />
                      </div>

                      {/* Right: Live Preview */}
                      <div className="p-4 bg-white">
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-[#76787C] mb-2">
                          Live preview
                        </div>
                        <MarkdownWithCitations
                          content={editVal.content_md}
                          sourcesBySid={sourcesBySid}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Editable Quiz Items */}
              {version.content.knowledge_check.length > 0 && (
                <div className="bg-white border border-[#E4E4E0] rounded-[8px] overflow-hidden">
                  <div className="px-5 py-3.5 bg-[#FAFAF8] border-b border-[#E4E4E0]">
                    <h3 className="font-serif text-[17px] font-semibold text-[#1C1D1F]">
                      Knowledge Check Questions ({version.content.knowledge_check.length})
                    </h3>
                  </div>

                  <div className="divide-y divide-[#E4E4E0]">
                    {version.content.knowledge_check.map((origQ, qIdx) => {
                      const qItem = editedQuiz[qIdx] || origQ;
                      return (
                        <div
                          key={qIdx}
                          className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-[#E4E4E0]"
                        >
                          {/* Quiz Item Editor */}
                          <div className="p-4 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[12px] font-semibold text-[#0B4F8A]">
                                Question Q{qIdx + 1}
                              </span>
                              <span className="text-[11.5px] text-[#76787C] truncate max-w-[260px]">
                                Outcome: {qItem.outcome}
                              </span>
                            </div>

                            <div>
                              <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#525458] mb-1">
                                Question prompt
                              </label>
                              <textarea
                                rows={2}
                                value={qItem.q}
                                onChange={(e) =>
                                  handleQuizChange(qIdx, { ...qItem, q: e.target.value })
                                }
                                className="w-full text-[13.5px] text-[#1C1D1F] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[5px] p-2 focus:outline-none focus:border-[#0B4F8A]"
                              />
                            </div>

                            <div className="space-y-1.5">
                              <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#525458]">
                                Options (select radio button to mark correct answer)
                              </label>
                              {qItem.options.map((opt, oIdx) => (
                                <div key={oIdx} className="flex items-center gap-2">
                                  <input
                                    type="radio"
                                    name={`correct-opt-${qIdx}`}
                                    checked={qItem.answer === opt}
                                    onChange={() =>
                                      handleQuizChange(qIdx, { ...qItem, answer: opt })
                                    }
                                    className="accent-[#0B4F8A]"
                                    title="Mark as keyed correct answer"
                                  />
                                  <input
                                    type="text"
                                    value={opt}
                                    onChange={(e) => {
                                      const newVal = e.target.value;
                                      const nextOptions = [...qItem.options];
                                      nextOptions[oIdx] = newVal;
                                      const nextAnswer =
                                        qItem.answer === opt ? newVal : qItem.answer;
                                      handleQuizChange(qIdx, {
                                        ...qItem,
                                        options: nextOptions,
                                        answer: nextAnswer,
                                      });
                                    }}
                                    className="flex-1 text-[13px] text-[#1C1D1F] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[5px] px-2.5 py-1 focus:outline-none focus:border-[#0B4F8A]"
                                  />
                                </div>
                              ))}
                            </div>

                            <div>
                              <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#525458] mb-1">
                                Explanation (markdown + [S#] citations)
                              </label>
                              <textarea
                                rows={2}
                                value={qItem.explanation}
                                onChange={(e) =>
                                  handleQuizChange(qIdx, {
                                    ...qItem,
                                    explanation: e.target.value,
                                  })
                                }
                                className="w-full font-mono text-[12.5px] text-[#1C1D1F] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[5px] p-2 focus:outline-none focus:border-[#0B4F8A]"
                              />
                            </div>
                          </div>

                          {/* Quiz Item Live Preview */}
                          <div className="p-4 bg-white">
                            <div className="text-[11px] font-semibold uppercase tracking-wider text-[#76787C] mb-2">
                              Live preview · Q{qIdx + 1}
                            </div>
                            <p className="font-medium text-[15px] text-[#1C1D1F] mb-2.5">
                              {qItem.q}
                            </p>
                            <ul className="space-y-1.5 mb-3">
                              {qItem.options.map((opt, oIdx) => {
                                const isAns = opt === qItem.answer;
                                return (
                                  <li
                                    key={oIdx}
                                    className={`text-[13.5px] px-3 py-1.5 rounded-[5px] border ${
                                      isAns
                                        ? 'bg-[#EAF4EE] border-[#B8DFC9] text-[#1E7B4F] font-medium'
                                        : 'bg-[#FAFAF8] border-[#E4E4E0] text-[#525458]'
                                    }`}
                                  >
                                    {opt} {isAns && '✓'}
                                  </li>
                                );
                              })}
                            </ul>
                            <div className="text-[13px] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[5px] p-2.5">
                              <MarkdownWithCitations
                                content={qItem.explanation}
                                sourcesBySid={sourcesBySid}
                                className="text-[13px]"
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* ================= PREVIEW MODE (Course Player, One Section at a Time) ================= */
            <div className="max-w-[720px] mx-auto">
              {isReferencesView ? (
                /* REFERENCES SECTION (LAST ITEM IN CURRICULUM) */
                <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-6 sm:p-8">
                  <div className="flex items-center justify-between gap-2 text-[12px] font-semibold uppercase tracking-wider text-[#0B4F8A] mb-1">
                    <span>References & Further Reading</span>
                    <span className="font-mono text-[#76787C]">
                      {data.sources.length} total sources
                    </span>
                  </div>
                  <h2 className="font-serif text-[26px] font-semibold text-[#1C1D1F] mb-6">
                    Lesson References
                  </h2>

                  {(() => {
                    const webSources = data.sources.filter((s) => s.type === 'web');
                    const videoSources = data.sources.filter((s) => s.type === 'video');
                    const bookSources = data.sources.filter((s) => s.type === 'book');

                    return (
                      <div className="space-y-8">
                        {/* Group 1: Web Sources */}
                        <div>
                          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-[#525458] pb-2 border-b border-[#E4E4E0] mb-3">
                            <Globe className="w-4 h-4 text-[#0B4F8A]" />
                            <span>Web Sources ({webSources.length})</span>
                          </div>
                          {webSources.length === 0 ? (
                            <p className="text-[14px] text-[#76787C]">No web sources.</p>
                          ) : (
                            <ol className="space-y-3">
                              {webSources.map((src) => (
                                <li
                                  key={src.sid}
                                  className="p-3.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8]"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                                    <span className="font-mono text-[12px] font-semibold text-[#0B4F8A] bg-[#EDF4FA] px-2 py-0.5 rounded-[4px]">
                                      [{src.sid}]
                                    </span>
                                    <span className="text-[11.5px] font-medium px-2 py-0.5 rounded-[4px] bg-white border border-[#E4E4E0] text-[#525458]">
                                      {TIER_LABELS[src.reliability_tier] ||
                                        `Tier ${src.reliability_tier}`}
                                    </span>
                                  </div>
                                  <div className="text-[15px] font-semibold text-[#1C1D1F] mt-1">
                                    {src.url ? (
                                      <a
                                        href={src.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="hover:text-[#0B4F8A] hover:underline inline-flex items-center gap-1.5"
                                      >
                                        <span>{src.title}</span>
                                        <ExternalLink className="w-3.5 h-3.5 text-[#0B4F8A] shrink-0" />
                                      </a>
                                    ) : (
                                      src.title
                                    )}
                                  </div>
                                  {src.publisher && (
                                    <div className="text-[12.5px] text-[#525458] mt-0.5">
                                      Publisher: {src.publisher}
                                    </div>
                                  )}
                                  <div className="text-[12px] text-[#76787C] mt-1">
                                    Why this tier: {src.reliability_reason}
                                  </div>
                                </li>
                              ))}
                            </ol>
                          )}
                        </div>

                        {/* Group 2: Videos */}
                        <div>
                          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-[#525458] pb-2 border-b border-[#E4E4E0] mb-3">
                            <VideoIcon className="w-4 h-4 text-[#0B4F8A]" />
                            <span>Videos ({videoSources.length})</span>
                          </div>
                          {videoSources.length === 0 ? (
                            <p className="text-[14px] text-[#76787C]">No video sources.</p>
                          ) : (
                            <ol className="space-y-3">
                              {videoSources.map((src) => (
                                <li
                                  key={src.sid}
                                  className="p-3.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8]"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                                    <span className="font-mono text-[12px] font-semibold text-[#0B4F8A] bg-[#EDF4FA] px-2 py-0.5 rounded-[4px]">
                                      [{src.sid}]
                                    </span>
                                    <span className="text-[11.5px] font-medium px-2 py-0.5 rounded-[4px] bg-white border border-[#E4E4E0] text-[#525458]">
                                      {TIER_LABELS[src.reliability_tier] ||
                                        `Tier ${src.reliability_tier}`}
                                    </span>
                                  </div>
                                  <div className="text-[15px] font-semibold text-[#1C1D1F] mt-1">
                                    {src.url ? (
                                      <a
                                        href={src.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="hover:text-[#0B4F8A] hover:underline inline-flex items-center gap-1.5"
                                      >
                                        <span>{src.title}</span>
                                        <ExternalLink className="w-3.5 h-3.5 text-[#0B4F8A] shrink-0" />
                                      </a>
                                    ) : (
                                      src.title
                                    )}
                                  </div>
                                  {src.publisher && (
                                    <div className="text-[12.5px] text-[#525458] mt-0.5">
                                      Channel: {src.publisher}
                                    </div>
                                  )}
                                  <div className="text-[12px] text-[#76787C] mt-1">
                                    Why this tier: {src.reliability_reason}
                                  </div>
                                </li>
                              ))}
                            </ol>
                          )}
                        </div>

                        {/* Group 3: Books (Further Reading) */}
                        <div>
                          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-[#525458] pb-2 border-b border-[#E4E4E0] mb-2">
                            <BookOpen className="w-4 h-4 text-[#0B4F8A]" />
                            <span>Books · Further Reading ({bookSources.length})</span>
                          </div>
                          <p className="text-[12.5px] text-[#76787C] mb-3">
                            Catalogue details and publisher descriptions only; not used as cited factual evidence.
                          </p>
                          {bookSources.length === 0 ? (
                            <p className="text-[14px] text-[#76787C]">
                              No further-reading books listed.
                            </p>
                          ) : (
                            <ol className="space-y-3">
                              {bookSources.map((src) => (
                                <li
                                  key={src.sid}
                                  className="p-3.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8]"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                                    <span className="font-mono text-[12px] font-semibold text-[#525458] bg-white border border-[#E4E4E0] px-2 py-0.5 rounded-[4px]">
                                      [{src.sid}]
                                    </span>
                                    <span className="text-[11.5px] font-medium px-2 py-0.5 rounded-[4px] bg-white border border-[#E4E4E0] text-[#525458]">
                                      {TIER_LABELS[src.reliability_tier] ||
                                        `Tier ${src.reliability_tier}`}
                                    </span>
                                  </div>
                                  <div className="text-[15px] font-semibold text-[#1C1D1F] mt-1">
                                    {src.url ? (
                                      <a
                                        href={src.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="hover:text-[#0B4F8A] hover:underline inline-flex items-center gap-1.5"
                                      >
                                        <span>{src.title}</span>
                                        <ExternalLink className="w-3.5 h-3.5 text-[#0B4F8A] shrink-0" />
                                      </a>
                                    ) : (
                                      src.title
                                    )}
                                  </div>
                                  {src.publisher && (
                                    <div className="text-[12.5px] text-[#525458] mt-0.5">
                                      Author / Publisher: {src.publisher}
                                    </div>
                                  )}
                                  <div className="text-[12px] text-[#76787C] mt-1">
                                    {src.reliability_reason}
                                  </div>
                                </li>
                              ))}
                            </ol>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : activeSection ? (
                /* SINGLE SECTION CARD */
                <article className="bg-white border border-[#E4E4E0] rounded-[8px] p-6 sm:p-8">
                  {/* Section Meta Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[11.5px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-[4px] bg-[#EDF4FA] text-[#0B4F8A]">
                        {SECTION_TYPE_LABELS[activeSection.type] || activeSection.type}
                      </span>
                      <span className="font-mono text-[12px] text-[#76787C]">
                        {activeSection.id}
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1 font-mono text-[12.5px] text-[#525458]">
                      <Clock className="w-3.5 h-3.5 text-[#76787C]" />
                      <span>{activeSection.minutes} min</span>
                    </span>
                  </div>

                  {/* Section Title */}
                  <h2 className="font-serif text-[24px] sm:text-[26px] font-semibold text-[#1C1D1F] leading-snug mb-5">
                    {activeSection.heading}
                  </h2>

                  {/* Section Content by Type */}
                  {activeSection.type === 'activity' ? (
                    <div className="p-5 rounded-[8px] border border-[#0B4F8A]/35 bg-[#FAFAF8]">
                      <div className="text-[11.5px] font-semibold uppercase tracking-wider text-[#0B4F8A] mb-3 pb-2 border-b border-[#E4E4E0]">
                        Practical Activity Instructions
                      </div>
                      <MarkdownWithCitations
                        content={activeSection.content_md}
                        sourcesBySid={sourcesBySid}
                      />
                    </div>
                  ) : activeSection.type === 'video' ? (
                    <div className="space-y-6">
                      <MarkdownWithCitations
                        content={activeSection.content_md}
                        sourcesBySid={sourcesBySid}
                      />

                      {/* Embedded 16:9 YouTube Video Cards */}
                      <div className="space-y-6 mt-4">
                        {version.content.videos.map((vid) => {
                          const src = sourcesBySid[vid.sid];
                          const ytId = extractYouTubeId(vid.url, src?.metadata_json?.video_id);
                          const channelName =
                            src?.publisher || src?.metadata_json?.channel_title || 'YouTube';

                          return (
                            <div
                              key={vid.sid}
                              className="border border-[#E4E4E0] rounded-[8px] overflow-hidden bg-[#FAFAF8]"
                            >
                              {ytId ? (
                                <div className="relative w-full aspect-video bg-[#1C1D1F]">
                                  <iframe
                                    src={`https://www.youtube.com/embed/${ytId}`}
                                    title={vid.title}
                                    className="w-full h-full border-0"
                                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                    allowFullScreen
                                  />
                                </div>
                              ) : null}

                              <div className="p-4">
                                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                                  <span className="font-mono text-[11.5px] font-semibold text-[#0B4F8A] bg-[#EDF4FA] px-2 py-0.5 rounded-[4px]">
                                    [{vid.sid}]
                                  </span>
                                  <div className="flex items-center gap-2 text-[12px] text-[#525458]">
                                    <span>{channelName}</span>
                                    <span>·</span>
                                    <span className="font-mono">{vid.duration_min} min</span>
                                    {vid.watch_segment && (
                                      <span className="font-mono bg-white border border-[#E4E4E0] px-1.5 py-0.5 rounded">
                                        Segment: {vid.watch_segment}
                                      </span>
                                    )}
                                  </div>
                                </div>

                                <h3 className="font-serif text-[18px] font-semibold text-[#1C1D1F] mt-1">
                                  <a
                                    href={vid.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:text-[#0B4F8A] hover:underline inline-flex items-center gap-1.5"
                                  >
                                    <span>{vid.title}</span>
                                    <ExternalLink className="w-3.5 h-3.5 text-[#0B4F8A] shrink-0" />
                                  </a>
                                </h3>

                                <div className="mt-2 pt-2 border-t border-[#E4E4E0] text-[14px] text-[#525458]">
                                  <strong className="font-semibold text-[#1C1D1F]">
                                    Why watch:{' '}
                                  </strong>
                                  <MarkdownWithCitations
                                    content={vid.why}
                                    sourcesBySid={sourcesBySid}
                                    className="inline text-[14px]"
                                  />
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : activeSection.type === 'knowledge_check' ? (
                    <div className="space-y-6">
                      <MarkdownWithCitations
                        content={activeSection.content_md}
                        sourcesBySid={sourcesBySid}
                      />

                      {/* Interactive Multiple-Choice Questions */}
                      <div className="space-y-5 mt-4">
                        <div className="flex items-center justify-between">
                          <span className="text-[12px] font-semibold uppercase tracking-wider text-[#525458]">
                            {version.content.knowledge_check.length} Questions
                          </span>
                          {Object.keys(selectedQuizAnswers).length > 0 && (
                            <button
                              type="button"
                              onClick={() => setSelectedQuizAnswers({})}
                              className="text-[12px] font-medium text-[#0B4F8A] hover:underline"
                            >
                              Reset answers
                            </button>
                          )}
                        </div>

                        {version.content.knowledge_check.map((item, qIdx) => {
                          const picked = selectedQuizAnswers[qIdx];
                          const isAnswered = picked !== undefined;
                          const isCorrect = picked === item.answer;

                          return (
                            <div
                              key={qIdx}
                              className="p-5 rounded-[8px] border border-[#E4E4E0] bg-[#FAFAF8]"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                                <span className="font-mono text-[12px] font-semibold text-[#0B4F8A]">
                                  Question {qIdx + 1} of {version.content.knowledge_check.length}
                                </span>
                                <span className="text-[11.5px] text-[#76787C] bg-white border border-[#E4E4E0] px-2 py-0.5 rounded-[4px]">
                                  Assesses: {item.outcome}
                                </span>
                              </div>

                              <p className="font-serif text-[17px] font-medium text-[#1C1D1F] mb-4 leading-snug">
                                {item.q}
                              </p>

                              <div className="space-y-2">
                                {item.options.map((option, oIdx) => {
                                  const isThisPicked = picked === option;
                                  const isThisCorrectAnswer = option === item.answer;

                                  let optionStyle =
                                    'bg-white border-[#E4E4E0] text-[#1C1D1F] hover:border-[#0B4F8A]';
                                  if (isAnswered) {
                                    if (isThisCorrectAnswer) {
                                      optionStyle =
                                        'bg-[#EAF4EE] border-[#1E7B4F] text-[#1E7B4F] font-medium';
                                    } else if (isThisPicked && !isThisCorrectAnswer) {
                                      optionStyle =
                                        'bg-[#FDECEB] border-[#B42318] text-[#B42318] font-medium';
                                    } else {
                                      optionStyle = 'bg-white/60 border-[#E4E4E0] text-[#76787C]';
                                    }
                                  }

                                  return (
                                    <button
                                      key={oIdx}
                                      type="button"
                                      onClick={() =>
                                        setSelectedQuizAnswers((prev) => ({
                                          ...prev,
                                          [qIdx]: option,
                                        }))
                                      }
                                      className={`w-full text-left px-4 py-3 rounded-[6px] border text-[14.5px] transition-colors flex items-center justify-between gap-3 ${optionStyle}`}
                                    >
                                      <span>{option}</span>
                                      {isAnswered && isThisCorrectAnswer && (
                                        <span className="text-[12px] font-mono font-semibold text-[#1E7B4F] shrink-0">
                                          ✓ Correct
                                        </span>
                                      )}
                                      {isAnswered && isThisPicked && !isThisCorrectAnswer && (
                                        <span className="text-[12px] font-mono font-semibold text-[#B42318] shrink-0">
                                          ✗ Incorrect
                                        </span>
                                      )}
                                    </button>
                                  );
                                })}
                              </div>

                              {isAnswered && (
                                <div
                                  className={`mt-4 p-3.5 rounded-[6px] border text-[14px] ${
                                    isCorrect
                                      ? 'bg-[#EAF4EE]/60 border-[#B8DFC9]'
                                      : 'bg-[#FDECEB]/50 border-[#F5BDBA]'
                                  }`}
                                >
                                  <div
                                    className={`text-[12px] font-semibold uppercase tracking-wider mb-1 ${
                                      isCorrect ? 'text-[#1E7B4F]' : 'text-[#B42318]'
                                    }`}
                                  >
                                    {isCorrect ? 'Correct' : 'Incorrect'} — Explanation
                                  </div>
                                  <MarkdownWithCitations
                                    content={item.explanation}
                                    sourcesBySid={sourcesBySid}
                                    className="text-[14px]"
                                  />
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    /* Concept / Example / Hook / Summary */
                    <MarkdownWithCitations
                      content={activeSection.content_md}
                      sourcesBySid={sourcesBySid}
                    />
                  )}
                </article>
              ) : null}

              {/* BOTTOM NAVIGATION: ← Previous and Next → */}
              <div className="mt-6 flex items-center justify-between gap-4">
                <button
                  type="button"
                  disabled={currentIndex === 0}
                  onClick={() => goToIndex(currentIndex - 1)}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-[6px] border border-[#E4E4E0] bg-white hover:bg-[#F3F3EF] text-[#1C1D1F] text-[14px] font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Previous</span>
                </button>

                <span className="text-[12.5px] text-[#76787C] font-mono">
                  {currentIndex + 1} / {totalItems}
                </span>

                <button
                  type="button"
                  disabled={currentIndex >= totalItems - 1}
                  onClick={() => goToIndex(currentIndex + 1)}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[14px] font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none"
                >
                  <span>Next</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </main>

        {/* RIGHT PANEL: QUALITY REVIEW DRAWER */}
        {rightDrawerOpen && (
          <QualityReviewDrawer
            activeTab={reviewTab}
            onTabChange={setReviewTab}
            qc={qc}
            sources={data.sources}
            steps={steps}
            currentVersionNo={version?.version_no ?? null}
            generationModel={data.generation?.model ?? null}
            generationWarnings={data.generation?.warnings ?? []}
            lessonTimeBudget={data.time_budget}
            rerunningLayer={rerunningLayer}
            retryingStep={retryingStep}
            previewingIssueId={previewingIssueId}
            issueErrors={issueErrors}
            onRerunQC={handleRerunQC}
            onRetryStep={handleRetryStep}
            onPreviewFix={handlePreviewFix}
            onDismissIssue={handleDismissIssue}
            onJumpToLocation={handleJumpToLocation}
            onCloseDrawer={() => setRightDrawerOpen(false)}
          />
        )}
      </div>

      {/* BEFORE/AFTER DIFF MODAL FOR PREVIEW FIX */}
      {activeFixModal && (
        <FixDiffModal
          issue={activeFixModal.issue}
          fix={activeFixModal.fix}
          applying={applyingFix}
          dismissing={dismissingFix}
          error={fixModalError}
          onApply={handleApplyFix}
          onDismiss={() => handleDismissIssue(activeFixModal.issue)}
          onClose={() => setActiveFixModal(null)}
        />
      )}

      {/* EXPORT DIALOG */}
      {exportModalOpen && (
        <ExportModal
          lessonId={lessonId}
          lessonTitle={data.lesson.title}
          versionNo={version?.version_no ?? null}
          hasQC1={Boolean(qc.factual)}
          hasQC2={Boolean(qc.instructional)}
          onClose={() => setExportModalOpen(false)}
          onNetworkError={onNetworkError}
        />
      )}
    </div>
  );
};
