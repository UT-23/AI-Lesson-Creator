import React, { useState } from 'react';
import {
  Check,
  X,
  RotateCcw,
  ExternalLink,
  AlertCircle,
  Loader2,
  Circle,
  Slash,
  Wrench,
  ChevronRight,
} from 'lucide-react';
import {
  ClaimVerdictLabel,
  QCIssueItem,
  QCLayer,
  QCResponse,
  SourceItem,
  StepOut,
  TimeBudget,
} from '../types/api';
import { TIER_LABELS } from './MarkdownWithCitations';

export type ReviewTab = 'qc1' | 'qc2' | 'sources' | 'pipeline';

interface QualityReviewDrawerProps {
  activeTab: ReviewTab;
  onTabChange: (tab: ReviewTab) => void;
  qc: QCResponse;
  sources: SourceItem[];
  steps: StepOut[];
  currentVersionNo: number | null;
  generationModel: string | null;
  generationWarnings: string[];
  lessonTimeBudget: TimeBudget | null;
  rerunningLayer: QCLayer | null;
  retryingStep: string | null;
  previewingIssueId: number | null;
  issueErrors: Record<number, string>;
  onRerunQC: (layer: QCLayer) => void;
  onRetryStep: (stepName: string) => void;
  onPreviewFix: (issue: QCIssueItem) => void;
  onDismissIssue: (issue: QCIssueItem) => void;
  onJumpToLocation: (location: string) => void;
  onCloseDrawer?: () => void;
}

const VERDICT_STYLES: Record<
  ClaimVerdictLabel,
  { label: string; bg: string; text: string; border: string }
> = {
  supported: {
    label: 'supported',
    bg: 'bg-[#EAF4EE]',
    text: 'text-[#1E7B4F]',
    border: 'border-[#B8DFC9]',
  },
  partially_supported: {
    label: 'partially',
    bg: 'bg-[#FDF5E6]',
    text: 'text-[#A86A00]',
    border: 'border-[#F0D49B]',
  },
  unsupported: {
    label: 'unsupported',
    bg: 'bg-[#FDECEB]',
    text: 'text-[#B42318]',
    border: 'border-[#F5BDBA]',
  },
  contradicted: {
    label: 'contradicted',
    bg: 'bg-[#FDECEB]',
    text: 'text-[#B42318] font-bold',
    border: 'border-[#B42318]',
  },
  uncited: {
    label: 'uncited',
    bg: 'bg-[#FDF5E6]',
    text: 'text-[#A86A00]',
    border: 'border-[#F0D49B]',
  },
  not_checked: {
    label: 'not checked',
    bg: 'bg-[#F3F3EF]',
    text: 'text-[#76787C]',
    border: 'border-[#E4E4E0]',
  },
};

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt || !finishedAt) return '—';
  const s = new Date(startedAt).getTime();
  const f = new Date(finishedAt).getTime();
  if (Number.isNaN(s) || Number.isNaN(f) || f < s) return '—';
  const sec = (f - s) / 1000;
  if (sec < 1) return `${Math.round(sec * 1000)}ms`;
  return `${sec.toFixed(1)}s`;
}

function formatProviderName(model: string | null | undefined): string {
  if (!model) return 'Not run yet';
  if (model.toLowerCase().includes('gemini')) return `Gemini (${model})`;
  if (model.toLowerCase().includes('groq') || model.includes('/')) return `Groq (${model})`;
  return model;
}

export const QualityReviewDrawer: React.FC<QualityReviewDrawerProps> = ({
  activeTab,
  onTabChange,
  qc,
  sources,
  steps,
  currentVersionNo,
  generationModel,
  generationWarnings,
  lessonTimeBudget,
  rerunningLayer,
  retryingStep,
  previewingIssueId,
  issueErrors,
  onRerunQC,
  onRetryStep,
  onPreviewFix,
  onDismissIssue,
  onJumpToLocation,
  onCloseDrawer,
}) => {
  const [hoveredTierSid, setHoveredTierSid] = useState<string | null>(null);

  const factual = qc.factual;
  const instructional = qc.instructional;

  const countSeverities = (issues: QCIssueItem[]) => {
    const counts = { critical: 0, major: 0, minor: 0 };
    for (const iss of issues) {
      if (iss.status === 'dismissed') continue;
      counts[iss.severity] = (counts[iss.severity] || 0) + 1;
    }
    return counts;
  };

  const renderStaleBanner = (reportVersionNo: number, layer: QCLayer) => {
    if (currentVersionNo == null || currentVersionNo <= reportVersionNo) return null;
    return (
      <div className="mb-3 px-3 py-2 rounded-[6px] bg-[#FDF5E6] border border-[#F0D49B] text-[#A86A00] text-[12.5px] flex items-center justify-between gap-2">
        <span>
          Lesson edited since this review (reviewed v{reportVersionNo}, current v{currentVersionNo}). Re-run to update.
        </span>
        <button
          type="button"
          disabled={rerunningLayer === layer}
          onClick={() => onRerunQC(layer)}
          className="px-2 py-1 rounded-[4px] bg-white border border-[#F0D49B] text-[#A86A00] hover:bg-[#FDF5E6] font-medium text-[11.5px] shrink-0"
        >
          Re-run
        </button>
      </div>
    );
  };

  const renderIssueList = (issues: QCIssueItem[]) => {
    if (issues.length === 0) {
      return (
        <div className="p-4 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8] text-[13px] text-[#525458]">
          No issues reported for this review.
        </div>
      );
    }

    return (
      <div className="space-y-2.5">
        {issues.map((issue) => {
          const isPreviewing = previewingIssueId === issue.id;
          const errText = issueErrors[issue.id];
          const sevBadge =
            issue.severity === 'critical'
              ? 'bg-[#FDECEB] text-[#B42318] border-[#F5BDBA]'
              : issue.severity === 'major'
              ? 'bg-[#FDF5E6] text-[#A86A00] border-[#F0D49B]'
              : 'bg-[#F3F3EF] text-[#525458] border-[#E4E4E0]';

          return (
            <div
              key={issue.id}
              className={`p-3.5 rounded-[6px] border border-[#E4E4E0] bg-white transition-opacity ${
                issue.status !== 'open' ? 'opacity-65 bg-[#FAFAF8]' : ''
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[11.5px] font-semibold text-[#1C1D1F]">
                    {issue.issue_id}
                  </span>
                  <span
                    className={`text-[10.5px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-[4px] border ${sevBadge}`}
                  >
                    {issue.severity}
                  </span>
                  <span className="text-[11.5px] text-[#525458] font-mono">
                    {issue.category}
                  </span>
                  {issue.status !== 'open' && (
                    <span
                      className={`text-[10.5px] font-medium px-1.5 py-0.5 rounded-[4px] border ${
                        issue.status === 'applied'
                          ? 'bg-[#EAF4EE] text-[#1E7B4F] border-[#B8DFC9]'
                          : 'bg-[#F3F3EF] text-[#76787C] border-[#E4E4E0]'
                      }`}
                    >
                      {issue.status}
                    </span>
                  )}
                </div>

                {issue.location && (
                  <button
                    type="button"
                    onClick={() => onJumpToLocation(issue.location!)}
                    className="inline-flex items-center gap-0.5 font-mono text-[11.5px] font-medium text-[#0B4F8A] hover:underline bg-[#EDF4FA] px-2 py-0.5 rounded-[4px]"
                    title="Jump to section in course player"
                  >
                    <span>{issue.location}</span>
                    <ChevronRight className="w-3 h-3" />
                  </button>
                )}
              </div>

              <p className="text-[13px] font-medium text-[#1C1D1F] leading-snug">
                {issue.claim_or_text}
              </p>

              {issue.evidence && (
                <p className="mt-1.5 text-[12px] text-[#525458] bg-[#FAFAF8] border border-[#E4E4E0] rounded-[4px] px-2.5 py-1.5 leading-relaxed">
                  <strong className="font-semibold text-[#1C1D1F]">Evidence: </strong>
                  {issue.evidence}
                </p>
              )}

              <p className="mt-1.5 text-[12.5px] text-[#525458] leading-snug">
                <strong className="font-semibold text-[#1C1D1F]">Suggestion: </strong>
                {issue.suggestion}
              </p>

              {errText && (
                <p className="mt-2 text-[12px] text-[#B42318] bg-[#FDECEB] border border-[#F5BDBA] rounded-[4px] px-2.5 py-1.5">
                  {errText}
                </p>
              )}

              {issue.status === 'open' && (
                <div className="mt-3 pt-2.5 border-t border-[#E4E4E0] flex items-center gap-2">
                  <button
                    type="button"
                    disabled={isPreviewing}
                    onClick={() => onPreviewFix(issue)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[5px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[12px] font-medium transition-colors disabled:opacity-50"
                  >
                    {isPreviewing ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Generating preview…</span>
                      </>
                    ) : (
                      <>
                        <Wrench className="w-3 h-3" />
                        <span>Preview fix</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDismissIssue(issue)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[5px] border border-[#E4E4E0] bg-white hover:bg-[#F3F3EF] text-[#525458] hover:text-[#1C1D1F] text-[12px] font-medium transition-colors"
                  >
                    <Slash className="w-3 h-3" />
                    <span>Dismiss</span>
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <aside
      aria-label="Quality review panel"
      className="fixed inset-y-14 right-0 z-30 w-full sm:w-[420px] lg:static lg:inset-auto lg:z-auto lg:w-[440px] xl:w-[480px] shrink-0 bg-[#FAFAF8] border-l border-[#E4E4E0] flex flex-col h-[calc(100vh-3.5rem)] lg:h-full overflow-hidden shadow-lg lg:shadow-none"
    >
      {/* Drawer Header */}
      <div className="px-4 py-3 bg-white border-b border-[#E4E4E0] flex items-center justify-between">
        <h2 className="font-serif text-[16px] font-semibold text-[#1C1D1F]">Quality review</h2>
        {onCloseDrawer && (
          <button
            type="button"
            onClick={onCloseDrawer}
            aria-label="Close quality review panel"
            className="p-1 rounded-[4px] text-[#525458] hover:text-[#1C1D1F] hover:bg-[#F3F3EF]"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 4 Tabs */}
      <div
        role="tablist"
        className="grid grid-cols-4 bg-white border-b border-[#E4E4E0] px-2 pt-1 text-[12.5px] font-medium"
      >
        {(
          [
            { id: 'qc1', label: 'Fact check' },
            { id: 'qc2', label: 'Teaching' },
            { id: 'sources', label: `Sources (${sources.length})` },
            { id: 'pipeline', label: 'Pipeline' },
          ] as Array<{ id: ReviewTab; label: string }>
        ).map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onTabChange(tab.id)}
              className={`py-2.5 px-1.5 border-b-2 transition-colors truncate ${
                active
                  ? 'border-[#0B4F8A] text-[#0B4F8A] font-semibold'
                  : 'border-transparent text-[#525458] hover:text-[#1C1D1F]'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* TAB 1: FACT CHECK (QC1) */}
        {activeTab === 'qc1' && (
          <div>
            {!factual ? (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-5 text-center">
                <p className="text-[14px] text-[#525458] mb-3">
                  Fact check hasn't run for this version yet.
                </p>
                <button
                  type="button"
                  disabled={rerunningLayer === 'factual'}
                  onClick={() => onRerunQC('factual')}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[13px] font-medium disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>{rerunningLayer === 'factual' ? 'Running fact check…' : 'Run fact check'}</span>
                </button>
              </div>
            ) : (
              <>
                {renderStaleBanner(factual.lesson_version_no, 'factual')}

                {/* Top Score & Severity Summary Card */}
                {(() => {
                  const counts = factual.details.counts || {};
                  const supported = counts.supported || 0;
                  const judgedClaims = (factual.details.claims || []).filter(
                    (c) => c.verdict !== 'not_checked'
                  ).length;
                  const sev = countSeverities(factual.issues || []);

                  return (
                    <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-4 mb-4">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-wider text-[#76787C]">
                            QC1 · Factual Accuracy (v{factual.lesson_version_no})
                          </div>
                          <div className="font-serif text-[20px] font-semibold text-[#1C1D1F] mt-0.5">
                            {supported} of {judgedClaims} claims supported{' '}
                            <span className="text-[15px] font-sans font-normal text-[#525458]">
                              ({factual.score}%)
                            </span>
                          </div>
                        </div>

                        <button
                          type="button"
                          disabled={rerunningLayer === 'factual'}
                          onClick={() => onRerunQC('factual')}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8] hover:bg-[#F3F3EF] text-[#1C1D1F] text-[12px] font-medium transition-colors shrink-0 disabled:opacity-50"
                        >
                          <RotateCcw
                            className={`w-3.5 h-3.5 ${
                              rerunningLayer === 'factual' ? 'animate-spin' : ''
                            }`}
                          />
                          <span>
                            {rerunningLayer === 'factual' ? 'Running…' : 'Re-run fact check'}
                          </span>
                        </button>
                      </div>

                      {/* Critical / Major / Minor counts */}
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className="text-[12px] px-2 py-0.5 rounded-[4px] border bg-[#FDECEB] text-[#B42318] border-[#F5BDBA] font-medium">
                          {sev.critical} critical
                        </span>
                        <span className="text-[12px] px-2 py-0.5 rounded-[4px] border bg-[#FDF5E6] text-[#A86A00] border-[#F0D49B] font-medium">
                          {sev.major} major
                        </span>
                        <span className="text-[12px] px-2 py-0.5 rounded-[4px] border bg-[#F3F3EF] text-[#525458] border-[#E4E4E0] font-medium">
                          {sev.minor} minor
                        </span>
                        {factual.details.model && (
                          <span className="ml-auto text-[11px] font-mono text-[#76787C]">
                            Judge: {factual.details.model}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* Claim Verification Table (first, right under score) */}
                <div className="mb-4">
                  <h3 className="text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-2">
                    Claim verification table ({(factual.details.claims || []).length})
                  </h3>
                  <div className="bg-white border border-[#E4E4E0] rounded-[8px] overflow-hidden">
                    <div className="max-h-56 overflow-y-auto divide-y divide-[#E4E4E0]">
                      {(factual.details.claims || []).map((claim) => {
                        const style =
                          VERDICT_STYLES[claim.verdict] || VERDICT_STYLES.not_checked;
                        return (
                          <div key={claim.id} className="p-2.5 text-[12px] space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono font-semibold text-[#1C1D1F]">
                                  {claim.id}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => onJumpToLocation(claim.location)}
                                  className="font-mono text-[10.5px] text-[#0B4F8A] hover:underline bg-[#EDF4FA] px-1.5 py-0.5 rounded-[3px]"
                                >
                                  {claim.location}
                                </button>
                                {claim.sids && claim.sids.length > 0 && (
                                  <span className="font-mono text-[10.5px] text-[#76787C]">
                                    [{claim.sids.join(', ')}]
                                  </span>
                                )}
                              </div>
                              <span
                                className={`text-[10.5px] font-medium px-1.5 py-0.5 rounded-[4px] border ${style.bg} ${style.text} ${style.border}`}
                              >
                                {style.label}
                              </span>
                            </div>

                            <p className="text-[#1C1D1F] leading-snug">{claim.text}</p>

                            {claim.evidence_quote ? (
                              <p className="text-[11px] text-[#525458] bg-[#FAFAF8] border-l-2 border-[#0B4F8A] pl-2 py-0.5 italic">
                                "{claim.evidence_quote}"
                              </p>
                            ) : (
                              claim.explanation && (
                                <p className="text-[11px] text-[#76787C] leading-snug">
                                  {claim.explanation}
                                </p>
                              )
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Issues List (below claim table) */}
                <div>
                  <h3 className="text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-2">
                    Issues ({factual.issues.length})
                  </h3>
                  {renderIssueList(factual.issues)}
                </div>
              </>
            )}
          </div>
        )}

        {/* TAB 2: TEACHING QUALITY (QC2) */}
        {activeTab === 'qc2' && (
          <div>
            {!instructional ? (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-5 text-center">
                <p className="text-[14px] text-[#525458] mb-3">
                  Teaching quality review hasn't run for this version yet.
                </p>
                <button
                  type="button"
                  disabled={rerunningLayer === 'instructional'}
                  onClick={() => onRerunQC('instructional')}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[13px] font-medium disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>
                    {rerunningLayer === 'instructional'
                      ? 'Running teaching review…'
                      : 'Run teaching review'}
                  </span>
                </button>
              </div>
            ) : (
              <>
                {renderStaleBanner(instructional.lesson_version_no, 'instructional')}

                {/* Score Header */}
                <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-3 mb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-[#76787C]">
                        QC2 · Instructional Quality (v{instructional.lesson_version_no})
                      </div>
                      <div className="font-serif text-[18px] font-semibold text-[#1C1D1F] mt-0.5">
                        Score: {instructional.score}%{' '}
                        <span className="text-[13px] font-sans font-normal text-[#525458]">
                          (Rubric {instructional.details.rubric_average} / 5)
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      disabled={rerunningLayer === 'instructional'}
                      onClick={() => onRerunQC('instructional')}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] border border-[#E4E4E0] bg-[#FAFAF8] hover:bg-[#F3F3EF] text-[#1C1D1F] text-[11.5px] font-medium transition-colors shrink-0 disabled:opacity-50"
                    >
                      <RotateCcw
                        className={`w-3 h-3 ${
                          rerunningLayer === 'instructional' ? 'animate-spin' : ''
                        }`}
                      />
                      <span>
                        {rerunningLayer === 'instructional'
                          ? 'Running…'
                          : 'Re-run teaching review'}
                      </span>
                    </button>
                  </div>
                  <p className="mt-1.5 text-[12px] text-[#525458] leading-snug">
                    {instructional.summary}
                  </p>
                </div>

                {/* Outcome Coverage Matrix Grid */}
                <div className="mb-3.5">
                  <h3 className="text-[11.5px] font-semibold uppercase tracking-wider text-[#525458] mb-1.5">
                    Outcome coverage matrix
                  </h3>
                  <div className="bg-white border border-[#E4E4E0] rounded-[8px] overflow-x-auto">
                    <table className="w-full text-left border-collapse text-[11.5px]">
                      <thead>
                        <tr className="bg-[#F3F3EF] border-b border-[#E4E4E0] text-[#525458] font-semibold">
                          <th className="py-1.5 px-2.5">Outcome</th>
                          <th className="py-1.5 px-1.5 text-center">Explanation</th>
                          <th className="py-1.5 px-1.5 text-center">Example</th>
                          <th className="py-1.5 px-1.5 text-center">Practice</th>
                          <th className="py-1.5 px-1.5 text-center">Quiz</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#E4E4E0]">
                        {(instructional.details.coverage_matrix || []).map((row, idx) => {
                          const cols = [
                            row.explanation,
                            row.example,
                            row.practice,
                            row.quiz,
                          ];
                          return (
                            <tr key={idx}>
                              <td className="py-1.5 px-2.5 text-[#1C1D1F] font-medium leading-snug max-w-[160px]">
                                {row.outcome}
                              </td>
                              {cols.map((cell, cIdx) => (
                                <td
                                  key={cIdx}
                                  className="py-1.5 px-1 text-center align-middle"
                                >
                                  {cell?.present ? (
                                    <div className="inline-flex flex-col items-center">
                                      <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[#EAF4EE] text-[#1E7B4F] font-bold text-[11px]">
                                        ✓
                                      </span>
                                      {cell.sections && cell.sections.length > 0 && (
                                        <button
                                          type="button"
                                          onClick={() => onJumpToLocation(cell.sections[0])}
                                          className="font-mono text-[9.5px] text-[#0B4F8A] hover:underline"
                                        >
                                          {cell.sections.join(', ')}
                                        </button>
                                      )}
                                    </div>
                                  ) : (
                                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[#FDECEB] text-[#B42318] font-bold text-[11px]">
                                      ✗
                                    </span>
                                  )}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Horizontal Bar Chart of Minutes per Section with 45-minute limit line */}
                {(() => {
                  const tb = instructional.details.time_budget || lessonTimeBudget;
                  if (!tb) return null;
                  const limit = tb.budget_min || 45;
                  const maxScale = Math.max(limit * 1.15, tb.total_computed_min * 1.1, 50);
                  const limitPct = (limit / maxScale) * 100;
                  const totalPct = Math.min(100, (tb.total_computed_min / maxScale) * 100);

                  return (
                    <div className="mb-5">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-[#525458]">
                          Time budget ({tb.total_computed_min} of {limit} min)
                        </h3>
                        <span
                          className={`text-[11.5px] font-medium ${
                            tb.over_budget ? 'text-[#B42318]' : 'text-[#1E7B4F]'
                          }`}
                        >
                          {tb.over_budget ? 'Over 45-min limit' : 'Within 45-min limit'}
                        </span>
                      </div>

                      <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-3.5 space-y-3">
                        {/* Total bar with 45-min limit line */}
                        <div>
                          <div className="flex justify-between text-[11.5px] text-[#525458] mb-1.5">
                            <span>Total measured lesson duration</span>
                            <span className="font-mono font-semibold text-[#1C1D1F]">
                              {tb.total_computed_min} min (limit: {limit} min)
                            </span>
                          </div>
                          <div className="relative h-5 bg-[#F3F3EF] rounded-[4px] overflow-visible border border-[#E4E4E0] mb-4">
                            <div
                              style={{ width: `${totalPct}%` }}
                              className={`h-full rounded-l-[3px] transition-all ${
                                tb.over_budget ? 'bg-[#B42318]' : 'bg-[#0B4F8A]'
                              }`}
                            />
                            {/* 45-minute limit line */}
                            <div
                              style={{ left: `${limitPct}%` }}
                              className="absolute -top-1 -bottom-1.5 w-0.5 bg-[#B42318] z-10"
                              title={`${limit}-minute limit`}
                            >
                              <span className="absolute top-full mt-0.5 -translate-x-1/2 font-mono text-[10px] font-semibold text-[#B42318] bg-white px-1 rounded border border-[#F5BDBA] whitespace-nowrap">
                                {limit}m limit
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Per-section horizontal bars with 45-min reference scale */}
                        <div className="pt-2.5 border-t border-[#E4E4E0] space-y-1.5">
                          <div className="flex items-center justify-between text-[11px] font-medium text-[#76787C]">
                            <span>Minutes per section (click to jump)</span>
                            <span className="font-mono text-[10.5px] text-[#B42318]">
                              │ {limit} min budget line
                            </span>
                          </div>
                          {tb.sections.map((sec) => {
                            const widthPct = Math.min(
                              100,
                              Math.max(3, (sec.computed_min / maxScale) * 100)
                            );
                            return (
                              <button
                                key={sec.id}
                                type="button"
                                onClick={() => onJumpToLocation(sec.id)}
                                className="w-full text-left group"
                              >
                                <div className="flex items-center justify-between text-[11px] mb-0.5">
                                  <span className="truncate text-[#1C1D1F] group-hover:text-[#0B4F8A] pr-2">
                                    <span className="font-mono text-[10.5px] text-[#76787C] mr-1">
                                      {sec.id}
                                    </span>
                                    {sec.heading}
                                  </span>
                                  <span className="font-mono text-[10.5px] text-[#525458] shrink-0">
                                    {sec.computed_min} min
                                  </span>
                                </div>
                                <div className="relative h-2 bg-[#F3F3EF] rounded-[3px] overflow-visible">
                                  <div
                                    style={{ width: `${widthPct}%` }}
                                    className="h-full bg-[#0B4F8A]/80 group-hover:bg-[#0B4F8A] rounded-[3px]"
                                  />
                                  <div
                                    style={{ left: `${limitPct}%` }}
                                    className="absolute -top-0.5 -bottom-0.5 w-px bg-[#B42318]/50"
                                  />
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {/* Issues List */}
                <div>
                  <h3 className="text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-2">
                    Issues ({instructional.issues.length})
                  </h3>
                  {renderIssueList(instructional.issues)}
                </div>
              </>
            )}
          </div>
        )}

        {/* TAB 3: SOURCES */}
        {activeTab === 'sources' && (
          <div>
            {sources.length === 0 ? (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-5 text-center text-[13.5px] text-[#525458]">
                No researched sources stored for this lesson yet.
              </div>
            ) : (
              <div className="bg-white border border-[#E4E4E0] rounded-[8px] overflow-hidden">
                <table className="w-full text-left border-collapse text-[12.5px]">
                  <thead>
                    <tr className="bg-[#F3F3EF] border-b border-[#E4E4E0] text-[#525458] font-semibold text-[11.5px] uppercase tracking-wider">
                      <th className="py-2.5 px-3">ID</th>
                      <th className="py-2.5 px-2">Type</th>
                      <th className="py-2.5 px-2">Tier</th>
                      <th className="py-2.5 px-3">Title & Link</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E4E4E0]">
                    {sources.map((src) => (
                      <tr key={src.sid} className="hover:bg-[#FAFAF8]">
                        <td className="py-2.5 px-3 font-mono font-semibold text-[#0B4F8A] align-top">
                          {src.sid}
                        </td>
                        <td className="py-2.5 px-2 align-top">
                          <span className="font-mono text-[11px] uppercase px-1.5 py-0.5 rounded-[4px] bg-[#F3F3EF] text-[#525458]">
                            {src.type}
                          </span>
                        </td>
                        <td
                          className="py-2.5 px-2 align-top relative"
                          onMouseEnter={() => setHoveredTierSid(src.sid)}
                          onMouseLeave={() => setHoveredTierSid(null)}
                        >
                          <span
                            title={src.reliability_reason}
                            className="inline-block font-mono text-[11px] font-medium px-1.5 py-0.5 rounded-[4px] border border-[#E4E4E0] bg-[#FAFAF8] text-[#1C1D1F] cursor-help whitespace-nowrap"
                          >
                            Tier {src.reliability_tier}
                          </span>
                          {hoveredTierSid === src.sid && (
                            <div className="absolute left-0 top-full mt-1 w-56 p-2.5 rounded-[6px] bg-white border border-[#E4E4E0] shadow-sm z-30 text-[11.5px] text-[#1C1D1F] pointer-events-none">
                              <div className="font-semibold mb-0.5">
                                {TIER_LABELS[src.reliability_tier]}
                              </div>
                              <div className="text-[#525458]">{src.reliability_reason}</div>
                            </div>
                          )}
                        </td>
                        <td className="py-2.5 px-3 align-top">
                          <div className="font-medium text-[#1C1D1F] leading-snug">
                            {src.url ? (
                              <a
                                href={src.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="hover:text-[#0B4F8A] hover:underline inline-flex items-start gap-1"
                              >
                                <span>{src.title}</span>
                                <ExternalLink className="w-3 h-3 shrink-0 mt-1 text-[#0B4F8A]" />
                              </a>
                            ) : (
                              src.title
                            )}
                          </div>
                          {src.publisher && (
                            <div className="text-[11px] text-[#76787C] mt-0.5">
                              {src.publisher}
                            </div>
                          )}
                          <div className="text-[11px] text-[#525458] mt-0.5">
                            {src.reliability_reason}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: PIPELINE */}
        {activeTab === 'pipeline' && (
          <div className="space-y-4">
            {/* Models that actually ran */}
            <div className="bg-white border border-[#E4E4E0] rounded-[8px] p-3.5 space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[#76787C]">
                Provider / Model Execution Audit
              </div>
              <div className="grid grid-cols-1 gap-1.5 text-[12.5px]">
                <div className="flex items-center justify-between py-1 border-b border-[#E4E4E0]/60">
                  <span className="text-[#525458]">Lesson generation:</span>
                  <span className="font-mono font-medium text-[#1C1D1F]">
                    {formatProviderName(generationModel)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-[#E4E4E0]/60">
                  <span className="text-[#525458]">Fact check (QC1):</span>
                  <span className="font-mono font-medium text-[#1C1D1F]">
                    {formatProviderName(factual?.details?.model)}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-[#525458]">Teaching review (QC2):</span>
                  <span className="font-mono font-medium text-[#1C1D1F]">
                    {formatProviderName(instructional?.details?.model)}
                  </span>
                </div>
              </div>

              {generationWarnings && generationWarnings.length > 0 && (
                <div className="pt-2 border-t border-[#E4E4E0] space-y-1">
                  {generationWarnings.map((w, i) => (
                    <p
                      key={i}
                      className="text-[11.5px] text-[#A86A00] bg-[#FDF5E6] border border-[#F0D49B] rounded-[4px] px-2.5 py-1.5"
                    >
                      {w}
                    </p>
                  ))}
                </div>
              )}
            </div>

            {/* Steps List */}
            <div className="bg-white border border-[#E4E4E0] rounded-[8px] divide-y divide-[#E4E4E0]">
              {steps.map((step) => {
                const isRetrying = retryingStep === step.name;
                const duration = formatDuration(step.started_at, step.finished_at);

                return (
                  <div key={step.name} className="p-3 text-[13px]">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {step.status === 'done' && (
                          <span className="w-4 h-4 rounded-full bg-[#EAF4EE] text-[#1E7B4F] flex items-center justify-center shrink-0">
                            <Check className="w-3 h-3" />
                          </span>
                        )}
                        {step.status === 'running' && (
                          <Loader2 className="w-4 h-4 text-[#0B4F8A] animate-spin shrink-0" />
                        )}
                        {step.status === 'failed' && (
                          <AlertCircle className="w-4 h-4 text-[#B42318] shrink-0" />
                        )}
                        {step.status === 'skipped' && (
                          <Slash className="w-4 h-4 text-[#A86A00] shrink-0" />
                        )}
                        {step.status === 'pending' && (
                          <Circle className="w-4 h-4 text-[#76787C] shrink-0" />
                        )}

                        <span className="font-mono font-medium text-[#1C1D1F] truncate">
                          {step.name}
                        </span>
                      </div>

                      <div className="flex items-center gap-2.5 text-[11.5px] text-[#76787C] shrink-0">
                        <span>
                          {step.attempt} {step.attempt === 1 ? 'attempt' : 'attempts'}
                        </span>
                        <span className="font-mono">{duration}</span>
                        {(step.status === 'failed' ||
                          step.status === 'skipped' ||
                          step.status === 'done') && (
                          <button
                            type="button"
                            disabled={Boolean(retryingStep)}
                            onClick={() => onRetryStep(step.name)}
                            className={`px-2 py-0.5 rounded-[4px] border text-[11px] font-medium transition-colors ${
                              step.status === 'failed'
                                ? 'bg-[#FDECEB] text-[#B42318] border-[#F5BDBA] hover:bg-[#B42318] hover:text-white'
                                : 'bg-[#FAFAF8] text-[#525458] border-[#E4E4E0] hover:bg-[#F3F3EF] hover:text-[#1C1D1F]'
                            }`}
                          >
                            {isRetrying ? 'Running…' : 'Retry'}
                          </button>
                        )}
                      </div>
                    </div>

                    {step.error && (
                      <p className="mt-2 text-[12px] text-[#B42318] bg-[#FDECEB] border border-[#F5BDBA] rounded-[4px] p-2 font-mono whitespace-pre-wrap break-words">
                        {step.error}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
