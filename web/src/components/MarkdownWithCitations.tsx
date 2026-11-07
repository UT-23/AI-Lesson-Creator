import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ExternalLink } from 'lucide-react';
import { SourceItem } from '../types/api';

export const TIER_LABELS: Record<number, string> = {
  1: 'Tier 1 · Standard / Official',
  2: 'Tier 2 · Academic / Publisher',
  3: 'Tier 3 · Known Education Site',
  4: 'Tier 4 · Blog / Forum',
};

interface CitationChipProps {
  sid: string;
  source?: SourceItem;
}

export const CitationChip: React.FC<CitationChipProps> = ({ sid, source }) => {
  const [hovered, setHovered] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  const handleMouseEnter = (e: React.MouseEvent<HTMLSpanElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const tooltipWidth = 288; // w-72
    const clampedLeft = Math.max(
      tooltipWidth / 2 + 12,
      Math.min(window.innerWidth - tooltipWidth / 2 - 12, rect.left + rect.width / 2)
    );
    setCoords({
      top: rect.top - 8,
      left: clampedLeft,
    });
    setHovered(true);
  };

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (source?.url) {
      window.open(source.url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <span
      className="relative inline-block align-baseline mx-0.5"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onClick={handleClick}
        title={source ? `${source.title} (${TIER_LABELS[source.reliability_tier] || `Tier ${source.reliability_tier}`})` : sid}
        className="inline-flex items-center gap-0.5 text-[11px] leading-none font-mono font-medium px-1.5 py-0.5 rounded-[4px] border border-[#0B4F8A]/30 bg-[#EDF4FA] text-[#0B4F8A] hover:bg-[#0B4F8A] hover:text-white transition-colors duration-150 -translate-y-1 cursor-pointer"
      >
        <span>{sid}</span>
      </button>

      {hovered && source && coords && (
        <span
          role="tooltip"
          style={{
            position: 'fixed',
            top: `${coords.top}px`,
            left: `${coords.left}px`,
            transform: 'translate(-50%, -100%)',
          }}
          className="w-72 p-3 rounded-[6px] bg-white border border-[#E4E4E0] text-left shadow-md z-[100] pointer-events-none block font-sans normal-case"
        >
          <span className="flex items-center justify-between gap-2 mb-1">
            <span className="font-mono text-[11px] font-semibold text-[#0B4F8A] bg-[#EDF4FA] px-1.5 py-0.5 rounded-[4px]">
              [{source.sid}] {source.type.toUpperCase()}
            </span>
            <span className="text-[11px] font-medium text-[#525458] border border-[#E4E4E0] px-1.5 py-0.5 rounded-[4px] bg-[#FAFAF8]">
              {TIER_LABELS[source.reliability_tier] || `Tier ${source.reliability_tier}`}
            </span>
          </span>
          <span className="block text-[13px] font-semibold text-[#1C1D1F] leading-snug mb-1">
            {source.title}
          </span>
          {source.publisher && (
            <span className="block text-[11px] text-[#525458] mb-1">
              {source.publisher}
            </span>
          )}
          <span className="block text-[11px] text-[#76787C] leading-relaxed border-t border-[#E4E4E0] pt-1.5 mt-1">
            {source.reliability_reason}
          </span>
          {source.url && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-[#0B4F8A] mt-1.5">
              <ExternalLink className="w-3 h-3" />
              <span>Click chip to open source</span>
            </span>
          )}
        </span>
      )}
    </span>
  );
};

/**
 * Replaces [S1], [S2], or [S1, S2] outside of fenced/inline code blocks with markdown links [S1](#cite-S1)
 * so ReactMarkdown renders them via our custom `a` component inside paragraphs, lists, and table cells.
 */
function injectCitationLinks(markdown: string): string {
  if (!markdown) return '';
  // Split by fenced code blocks and inline code spans to avoid modifying code
  const segments = markdown.split(/(```[\s\S]*?```|`[^`\n]+`)/g);
  return segments
    .map((segment, index) => {
      // Odd indices are matched code blocks/spans
      if (index % 2 === 1) return segment;
      // Normalize grouped citations like [S3, S5] first if any exist
      const normalized = segment.replace(
        /\[(S\d+(?:\s*[,;]\s*S\d+)+)\]/g,
        (_match, group: string) => {
          const sids = group.match(/S\d+/g) || [];
          return sids.map((s) => `[${s}]`).join(', ');
        }
      );
      return normalized.replace(/\[(S\d+)\](?!\()/g, '[$1](#cite-$1)');
    })
    .join('');
}

interface MarkdownWithCitationsProps {
  content: string;
  sourcesBySid: Record<string, SourceItem>;
  className?: string;
}

export const MarkdownWithCitations: React.FC<MarkdownWithCitationsProps> = ({
  content,
  sourcesBySid,
  className = '',
}) => {
  const processed = injectCitationLinks(content);

  return (
    <div className={`lesson-markdown text-[#1C1D1F] leading-[1.7] text-[16px] ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href && href.startsWith('#cite-')) {
              const sid = href.replace('#cite-', '');
              return <CitationChip sid={sid} source={sourcesBySid[sid]} />;
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#0B4F8A] underline underline-offset-2 hover:text-[#083D6B]"
              >
                {children}
              </a>
            );
          },
          h1: ({ children }) => (
            <h1 className="font-serif text-[24px] font-semibold text-[#1C1D1F] mt-6 mb-3 leading-snug">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-serif text-[20px] font-semibold text-[#1C1D1F] mt-6 mb-2.5 leading-snug">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-serif text-[18px] font-semibold text-[#1C1D1F] mt-5 mb-2 leading-snug">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="font-sans text-[16px] font-semibold text-[#1C1D1F] mt-4 mb-1.5">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="mb-4 last:mb-0 text-[#1C1D1F] leading-[1.72]">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-6 mb-4 space-y-1.5 text-[#1C1D1F]">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-6 mb-4 space-y-1.5 text-[#1C1D1F]">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-[1.68]">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[#0B4F8A] pl-4 py-1 my-4 bg-[#FAFAF8] text-[#525458] italic rounded-r-[6px]">
              {children}
            </blockquote>
          ),
          code: ({ className: codeClass, children, ...props }) => {
            const isBlock = Boolean(codeClass && codeClass.includes('language-'));
            if (isBlock) {
              return (
                <code className="font-mono text-[13.5px] leading-relaxed text-[#1C1D1F]" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code
                className="font-mono text-[13.5px] px-1.5 py-0.5 rounded-[4px] bg-[#F3F3EF] border border-[#E4E4E0] text-[#1C1D1F]"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="my-4 p-4 rounded-[6px] bg-[#F3F3EF] border border-[#E4E4E0] overflow-x-auto font-mono text-[13.5px] leading-relaxed text-[#1C1D1F]">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-5 overflow-x-auto rounded-[6px] border border-[#E4E4E0]">
              <table className="w-full border-collapse text-left text-[14.5px]">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[#F3F3EF] border-b border-[#E4E4E0] text-[#1C1D1F] font-semibold">
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th className="py-2.5 px-3.5 border-b border-[#E4E4E0] text-[13px] uppercase tracking-wider text-[#525458] font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="py-2.5 px-3.5 border-b border-[#E4E4E0] text-[#1C1D1F] align-top">
              {children}
            </td>
          ),
          hr: () => <hr className="my-6 border-[#E4E4E0]" />,
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
};
