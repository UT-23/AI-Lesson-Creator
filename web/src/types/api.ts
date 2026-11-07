export type LessonStatus =
  | 'created'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed';

export type StepStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'skipped';

export type SectionType =
  | 'hook'
  | 'concept'
  | 'example'
  | 'activity'
  | 'video'
  | 'knowledge_check'
  | 'summary';

export type SourceType = 'web' | 'book' | 'video';

export type VersionAuthor = 'ai' | 'instructor' | 'qc_fix';

export type QCLayer = 'factual' | 'instructional';

export type Severity = 'critical' | 'major' | 'minor';

export type IssueStatus = 'open' | 'applied' | 'dismissed';

export type ClaimVerdictLabel =
  | 'supported'
  | 'partially_supported'
  | 'unsupported'
  | 'contradicted'
  | 'uncited'
  | 'not_checked';

export interface LessonListItem {
  id: number;
  title: string;
  status: LessonStatus;
  updated_at: string;
}

export interface StepOut {
  name: string;
  position: number;
  status: StepStatus;
  attempt: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  output_json: Record<string, unknown> | null;
}

export interface LessonCreatedOut {
  id: number;
  title: string;
  objective: string;
  status: LessonStatus;
  created_at: string;
  updated_at: string;
  steps: StepOut[];
}

export interface RunAccepted {
  lesson_id: number;
  status: LessonStatus;
  from_step: string;
  message: string;
}

export interface LessonSection {
  id: string;
  type: SectionType;
  heading: string;
  minutes: number;
  content_md: string;
  outcomes_covered: string[];
}

export interface LessonVideo {
  sid: string;
  title: string;
  url: string;
  duration_min: number;
  why: string;
  watch_segment: string | null;
}

export interface QuizItem {
  q: string;
  options: string[];
  answer: string;
  explanation: string;
  outcome: string;
}

export interface LessonContent {
  title: string;
  objective: string;
  outcomes: string[];
  total_minutes: number;
  sections: LessonSection[];
  videos: LessonVideo[];
  knowledge_check: QuizItem[];
  references: string[];
  further_reading: string[];
}

export interface LessonVersionData {
  version_no: number;
  author: VersionAuthor;
  note: string | null;
  created_at?: string;
  content: LessonContent;
  markdown: string;
}

export interface VersionSummary {
  version_no: number;
  author: VersionAuthor;
  note: string | null;
  created_at: string;
}

export interface SourceItem {
  id: number;
  sid: string;
  type: SourceType;
  title: string;
  url: string | null;
  publisher: string | null;
  reliability_tier: number;
  reliability_reason: string;
  excerpt_text: string;
  metadata_json: {
    video_id?: string;
    duration_seconds?: number;
    channel_title?: string;
    authors?: string[];
    published_date?: string | null;
    query?: string;
    [key: string]: unknown;
  };
}

export interface SectionTime {
  id: string;
  type: string;
  heading: string;
  declared_min: number;
  computed_min: number;
  basis: string;
  flags: string[];
}

export interface TimeBudget {
  version_no?: number;
  budget_min: number;
  wpm: number;
  total_declared_min: number;
  total_computed_min: number;
  over_budget: boolean;
  sections: SectionTime[];
  flags: string[];
}

export interface GenerationMetadata {
  model: string | null;
  warnings: string[];
  minutes_adjusted: Array<{
    section: string;
    declared: number;
    measured: number;
  }>;
}

export interface LessonDetailResponse {
  lesson: {
    id: number;
    title: string;
    objective: string;
    status: LessonStatus;
  };
  version: LessonVersionData | null;
  generation: GenerationMetadata;
  time_budget: TimeBudget | null;
  sources: SourceItem[];
}

export interface QCIssueItem {
  id: number;
  issue_id: string;
  severity: Severity;
  category: string;
  location: string | null;
  claim_or_text: string;
  evidence: string;
  source_ids: string[];
  suggestion: string;
  status: IssueStatus;
}

export interface ClaimRow {
  id: string;
  location: string;
  text: string;
  sids: string[];
  verdict: ClaimVerdictLabel;
  source_id: string | null;
  evidence_quote: string;
  quote_verified: boolean;
  explanation: string;
}

export interface NumericCheckRow {
  location: string;
  expression: string;
  stated: number;
  computed: number;
  ok: boolean;
  detail: string;
}

export interface ResultCheckRow {
  location: string;
  line: string;
  stated: number;
  detail: string;
}

export interface ContradictionRow {
  location: string;
  description: string;
  suggestion: string;
}

export interface FactualDetails {
  method: string;
  model: string;
  counts: Partial<Record<ClaimVerdictLabel, number>>;
  claims: ClaimRow[];
  numeric_checks?: NumericCheckRow[];
  result_checks?: ResultCheckRow[];
  source_audit?: string[];
  outcome_gaps?: string[];
  contradictions?: ContradictionRow[];
}

export interface CoverageCell {
  present: boolean;
  sections: string[];
  note?: string;
}

export interface OutcomeCoverageRow {
  outcome: string;
  explanation: CoverageCell;
  example: CoverageCell;
  practice: CoverageCell;
  quiz: CoverageCell;
}

export interface VerbAlignmentRow {
  outcome: string;
  verb: string;
  bloom_level: string;
  aligned: boolean;
  evidence: string;
  suggestion: string;
}

export interface RubricRow {
  criterion: string;
  score: number;
  justification: string;
}

export interface InstructionalDetails {
  method: string;
  model: string;
  coverage_matrix: OutcomeCoverageRow[];
  verb_alignment: VerbAlignmentRow[];
  rubric: RubricRow[];
  rubric_average: number;
  time_budget: TimeBudget;
}

export interface QCReport<D = Record<string, unknown>> {
  report_id: number;
  layer: QCLayer;
  lesson_id: number;
  lesson_version_no: number;
  score: number;
  summary: string;
  created_at: string;
  details: D;
  issues: QCIssueItem[];
}

export interface QCResponse {
  factual: QCReport<FactualDetails> | null;
  instructional: QCReport<InstructionalDetails> | null;
}

export interface PreviewFixResponse {
  issue_id: number;
  kind?: 'quiz';
  quiz_index?: number;
  section_id: string | null;
  heading: string;
  base_version_no: number;
  before: string;
  after: string;
  after_item?: QuizItem;
  change_summary: string;
  citations_added: Record<string, number>;
  citations_removed: Record<string, number>;
  unchanged: boolean;
  model: string;
}

export interface ContentEditRequest {
  sections?: Record<string, { content_md: string; heading?: string | null }>;
  quiz?: Record<number, QuizItem>;
  note?: string | null;
}
