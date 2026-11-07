import React, { useMemo } from 'react';
import { X, Check, Slash, AlertCircle } from 'lucide-react';
import { PreviewFixResponse, QCIssueItem } from '../types/api';
import { computeSideBySideDiff, DiffToken } from '../utils/diff';

interface FixDiffModalProps {
  issue: QCIssueItem;
  fix: PreviewFixResponse;
  applying: boolean;
  dismissing: boolean;
  error: string | null;
  onApply: () => void;
  onDismiss: () => void;
  onClose: () => void;
}

const renderTokens = (tokens: DiffToken[] | undefined, fallback: string | null) => {
  if (!tokens || tokens.length === 0) {
    return <span>{fallback ?? ''}</span>;
  }
  return tokens.map((tok, idx) => {
    if (tok.type === 'removed') {
      return (
        <span
          key={idx}
          className="bg-[#FDECEB] text-[#B42318] border-b border-[#B42318]/40 px-0.5 rounded-[2px] line-through decoration-[#B42318]/70"
        >
          {tok.text}
        </span>
      );
    }
    if (tok.type === 'added') {
      return (
        <span
          key={idx}
          className="bg-[#EAF4EE] text-[#1E7B4F] border-b border-[#1E7B4F]/40 px-0.5 rounded-[2px] font-medium"
        >
          {tok.text}
        </span>
      );
    }
    return <span key={idx}>{tok.text}</span>;
  });
};

export const FixDiffModal: React.FC<FixDiffModalProps> = ({
  issue,
  fix,
  applying,
  dismissing,
  error,
  onApply,
  onDismiss,
  onClose,
}) => {
  const diffRows = useMemo(
    () => computeSideBySideDiff(fix.before || '', fix.after || ''),
    [fix.before, fix.after]
  );

  const addedCitations = Object.entries(fix.citations_added || {});
  const removedCitations = Object.entries(fix.citations_removed || {});

  return (
    <div
      className="fixed inset-0 z-50 bg-[#1C1D1F]/40 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="diff-modal-title"
    >
      <div className="bg-white border border-[#E4E4E0] rounded-[8px] w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[#E4E4E0] flex items-start justify-between gap-4 bg-[#FAFAF8]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[12px] font-semibold px-2 py-0.5 rounded-[4px] bg-white border border-[#E4E4E0] text-[#1C1D1F]">
                {issue.issue_id}
              </span>
              <span
                className={`text-[11.5px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-[4px] border ${
                  issue.severity === 'critical'
                    ? 'bg-[#FDECEB] text-[#B42318] border-[#F5BDBA]'
                    : issue.severity === 'major'
                    ? 'bg-[#FDF5E6] text-[#A86A00] border-[#F0D49B]'
                    : 'bg-[#FAFAF8] text-[#525458] border-[#E4E4E0]'
                }`}
              >
                {issue.severity}
              </span>
              <span className="text-[13px] font-medium text-[#525458]">
                Target: <strong className="text-[#1C1D1F]">{fix.heading}</strong>{' '}
                {fix.section_id ? `(${fix.section_id})` : ''}
              </span>
              <span className="text-[12px] font-mono text-[#76787C]">
                · Proposed by {fix.model} (base v{fix.base_version_no})
              </span>
            </div>
            <h2
              id="diff-modal-title"
              className="font-serif text-[18px] font-semibold text-[#1C1D1F] mt-1.5"
            >
              Preview proposed fix
            </h2>
            <p className="text-[13.5px] text-[#525458] mt-0.5">{fix.change_summary}</p>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close diff preview"
            className="p-1.5 rounded-[6px] text-[#525458] hover:text-[#1C1D1F] hover:bg-[#E4E4E0]/50 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Metadata bar: verified citation diff from evidence store */}
        <div className="px-5 py-2.5 bg-white border-b border-[#E4E4E0] flex flex-wrap items-center justify-between gap-3 text-[12.5px]">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <span className="text-[#76787C] font-medium">Citations added: </span>
              {addedCitations.length > 0 ? (
                addedCitations.map(([sid, tier]) => (
                  <span
                    key={sid}
                    className="inline-block font-mono text-[11.5px] bg-[#EAF4EE] text-[#1E7B4F] border border-[#B8DFC9] px-1.5 py-0.5 rounded-[4px] mr-1"
                  >
                    [{sid}] Tier {tier}
                  </span>
                ))
              ) : (
                <span className="text-[#525458]">none</span>
              )}
            </div>
            <div>
              <span className="text-[#76787C] font-medium">Citations removed: </span>
              {removedCitations.length > 0 ? (
                removedCitations.map(([sid, tier]) => (
                  <span
                    key={sid}
                    className="inline-block font-mono text-[11.5px] bg-[#FDECEB] text-[#B42318] border border-[#F5BDBA] px-1.5 py-0.5 rounded-[4px] mr-1"
                  >
                    [{sid}] Tier {tier}
                  </span>
                ))
              ) : (
                <span className="text-[#525458]">none</span>
              )}
            </div>
          </div>

          {fix.unchanged && (
            <span className="text-[12px] text-[#A86A00] bg-[#FDF5E6] border border-[#F0D49B] px-2 py-0.5 rounded-[4px]">
              Proposed text is identical to current version.
            </span>
          )}
        </div>

        {/* Side-by-side Diff Body */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#E4E4E0]">
          {/* Column Headers */}
          <div className="grid grid-cols-1 md:grid-cols-2 bg-[#F3F3EF] text-[12px] font-semibold uppercase tracking-wider text-[#525458] sticky top-0 z-10 border-b border-[#E4E4E0]">
            <div className="px-4 py-2 border-b md:border-b-0 md:border-r border-[#E4E4E0] flex items-center justify-between">
              <span>Before (v{fix.base_version_no})</span>
              <span className="text-[#B42318] font-mono text-[11px] normal-case">Removed in red</span>
            </div>
            <div className="px-4 py-2 flex items-center justify-between">
              <span>After (Proposed rewrite)</span>
              <span className="text-[#1E7B4F] font-mono text-[11px] normal-case">Added in green</span>
            </div>
          </div>

          {/* Diff Rows */}
          <div className="font-mono text-[12.5px] leading-[1.65]">
            {diffRows.map((row, idx) => {
              const leftBg =
                row.status === 'removed'
                  ? 'bg-[#FDECEB]/65'
                  : row.status === 'modified'
                  ? 'bg-[#FDECEB]/25'
                  : 'bg-white';
              const rightBg =
                row.status === 'added'
                  ? 'bg-[#EAF4EE]/65'
                  : row.status === 'modified'
                  ? 'bg-[#EAF4EE]/25'
                  : 'bg-white';

              return (
                <div
                  key={idx}
                  className="grid grid-cols-1 md:grid-cols-2 border-b border-[#E4E4E0]/60 last:border-b-0"
                >
                  {/* Left (Before) */}
                  <div
                    className={`px-3 py-1.5 md:border-r border-[#E4E4E0] flex items-start gap-2.5 whitespace-pre-wrap break-words ${leftBg}`}
                  >
                    <span className="w-6 text-right text-[11px] text-[#76787C] select-none shrink-0">
                      {row.leftLineNo ?? ''}
                    </span>
                    <div className="flex-1 min-w-0 text-[#1C1D1F]">
                      {row.leftText !== null
                        ? renderTokens(row.leftTokens, row.leftText)
                        : null}
                    </div>
                  </div>

                  {/* Right (After) */}
                  <div
                    className={`px-3 py-1.5 flex items-start gap-2.5 whitespace-pre-wrap break-words ${rightBg}`}
                  >
                    <span className="w-6 text-right text-[11px] text-[#76787C] select-none shrink-0">
                      {row.rightLineNo ?? ''}
                    </span>
                    <div className="flex-1 min-w-0 text-[#1C1D1F]">
                      {row.rightText !== null
                        ? renderTokens(row.rightTokens, row.rightText)
                        : null}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-[#E4E4E0] bg-[#FAFAF8] flex flex-wrap items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            {error && (
              <div className="flex items-center gap-2 text-[13px] text-[#B42318]">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span className="truncate">{error}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2.5 ml-auto">
            <button
              type="button"
              onClick={onDismiss}
              disabled={applying || dismissing}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[6px] border border-[#E4E4E0] bg-white hover:bg-[#F3F3EF] text-[#525458] hover:text-[#1C1D1F] text-[13.5px] font-medium transition-colors disabled:opacity-50"
            >
              <Slash className="w-3.5 h-3.5" />
              <span>{dismissing ? 'Dismissing…' : 'Dismiss issue'}</span>
            </button>
            <button
              type="button"
              onClick={onApply}
              disabled={applying || dismissing || fix.unchanged}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[13.5px] font-medium transition-colors disabled:opacity-50"
            >
              <Check className="w-4 h-4" />
              <span>{applying ? 'Applying fix…' : 'Apply (creates new version)'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
