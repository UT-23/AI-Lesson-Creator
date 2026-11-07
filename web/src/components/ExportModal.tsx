import React, { useEffect, useState } from 'react';
import { X, Download, FileText, Check, AlertCircle } from 'lucide-react';
import { api, ApiError } from '../api/client';

interface ExportModalProps {
  lessonId: number;
  lessonTitle: string;
  versionNo: number | null;
  hasQC1: boolean;
  hasQC2: boolean;
  onClose: () => void;
  onNetworkError?: (msg: string | null) => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  lessonId,
  lessonTitle,
  versionNo,
  onClose,
  onNetworkError,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportBundle, setExportBundle] = useState<{
    blob: Blob;
    fileNames: string[];
    filename: string;
  } | null>(null);

  const loadExportBundle = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.fetchExportZip(lessonId);
      onNetworkError?.(null);
      setExportBundle(res);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isNetworkError) onNetworkError?.(err.detail);
        setError(err.detail);
      } else {
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadExportBundle();
  }, [lessonId]);

  const handleDownload = () => {
    if (!exportBundle) return;
    const url = URL.createObjectURL(exportBundle.blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = exportBundle.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const files = exportBundle?.fileNames || [];
  const hasPdf = files.includes('lesson.pdf');
  const hasDocx = files.includes('lesson.docx');

  const items = [
    {
      label: `Lesson content (v${versionNo ?? 1})`,
      files: ['lesson.md', 'lesson.json'].filter((f) => files.includes(f)),
      present: files.includes('lesson.md'),
    },
    {
      label: 'Numbered references & source reliability tiers',
      files: ['references.md'].filter((f) => files.includes(f)),
      present: files.includes('references.md'),
    },
    {
      label: 'QC1 · Fact check report',
      files: ['qc1_factual_report.md', 'qc1_factual_report.json'].filter((f) =>
        files.includes(f)
      ),
      present: files.includes('qc1_factual_report.md'),
    },
    {
      label: 'QC2 · Teaching quality report',
      files: ['qc2_instructional_report.md', 'qc2_instructional_report.json'].filter((f) =>
        files.includes(f)
      ),
      present: files.includes('qc2_instructional_report.md'),
    },
    ...(hasPdf || hasDocx
      ? [
          {
            label: 'Formatted documents (Pandoc)',
            files: ['lesson.pdf', 'lesson.docx'].filter((f) => files.includes(f)),
            present: true,
          },
        ]
      : []),
  ];

  return (
    <div
      className="fixed inset-0 z-50 bg-[#1C1D1F]/40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-dialog-title"
    >
      <div className="bg-white border border-[#E4E4E0] rounded-[8px] w-full max-w-md overflow-hidden">
        <div className="px-5 py-4 border-b border-[#E4E4E0] flex items-center justify-between bg-[#FAFAF8]">
          <div>
            <h2
              id="export-dialog-title"
              className="font-serif text-[18px] font-semibold text-[#1C1D1F]"
            >
              Export lesson package
            </h2>
            <p className="text-[13px] text-[#525458] truncate max-w-[320px]">{lessonTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close export dialog"
            className="p-1.5 rounded-[6px] text-[#525458] hover:text-[#1C1D1F] hover:bg-[#E4E4E0]/50 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5">
          {loading ? (
            <div className="py-6 text-center text-[14px] text-[#525458]">
              Preparing export archive from backend…
            </div>
          ) : error ? (
            <div className="p-3.5 rounded-[6px] bg-[#FDECEB] border border-[#F5BDBA] text-[#B42318] text-[13.5px]">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={loadExportBundle}
                className="mt-3 px-3 py-1.5 rounded-[6px] bg-white border border-[#E4E4E0] text-[#1C1D1F] text-[12.5px] font-medium hover:bg-[#F3F3EF]"
              >
                Retry export
              </button>
            </div>
          ) : (
            <>
              <div className="text-[12px] font-semibold uppercase tracking-wider text-[#525458] mb-2.5">
                Included in {exportBundle?.filename}
              </div>
              <ul className="divide-y divide-[#E4E4E0] border border-[#E4E4E0] rounded-[6px] bg-[#FAFAF8]">
                {items.map((item) => (
                  <li
                    key={item.label}
                    className="px-3.5 py-2.5 flex items-start justify-between gap-3 text-[13.5px]"
                  >
                    <div className="flex items-start gap-2.5 min-w-0">
                      {item.present ? (
                        <Check className="w-4 h-4 text-[#1E7B4F] shrink-0 mt-0.5" />
                      ) : (
                        <FileText className="w-4 h-4 text-[#76787C] shrink-0 mt-0.5" />
                      )}
                      <div className="min-w-0">
                        <div className="font-medium text-[#1C1D1F]">{item.label}</div>
                        {item.files.length > 0 ? (
                          <div className="font-mono text-[11.5px] text-[#76787C] mt-0.5">
                            {item.files.join(', ')}
                          </div>
                        ) : (
                          <div className="text-[11.5px] text-[#A86A00] mt-0.5">
                            Report not generated yet
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>

              {!hasPdf && !hasDocx && (
                <p className="mt-3 text-[12px] text-[#76787C] leading-relaxed">
                  Note: Markdown and JSON files are included. PDF/DOCX conversion is omitted because Pandoc is not installed on the backend host.
                </p>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3.5 border-t border-[#E4E4E0] bg-[#FAFAF8] flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-2 rounded-[6px] border border-[#E4E4E0] bg-white hover:bg-[#F3F3EF] text-[#1C1D1F] text-[13.5px] font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={loading || !exportBundle}
            onClick={handleDownload}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[13.5px] font-medium transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>Download ZIP</span>
          </button>
        </div>
      </div>
    </div>
  );
};
