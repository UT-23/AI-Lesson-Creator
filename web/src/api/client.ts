import {
  ContentEditRequest,
  LessonCreatedOut,
  LessonDetailResponse,
  LessonListItem,
  PreviewFixResponse,
  QCLayer,
  QCResponse,
  QuizItem,
  RunAccepted,
  StepOut,
  VersionSummary,
  LessonVersionData,
} from '../types/api';
import { parseZipFileNames } from '../utils/zipInspect';

export const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

function resolveFetchUrl(path: string): string {
  // If VITE_API_URL is explicitly set, call it directly; otherwise in dev on port 3000 use Vite's same-origin proxy to avoid CORS mismatch with :8000
  if (import.meta.env.VITE_API_URL) {
    return `${API_BASE_URL}${path}`;
  }
  if (typeof window !== 'undefined' && window.location.port === '3000') {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  status: number;
  isNetworkError: boolean;
  detail: string;
  fieldErrors: Record<string, string>;

  constructor(
    detail: string,
    status = 0,
    isNetworkError = false,
    fieldErrors: Record<string, string> = {}
  ) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.isNetworkError = isNetworkError;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(resolveFetchUrl(path), {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new ApiError(
      `Can't reach the backend at ${API_BASE_URL}. Start it and retry. (${msg})`,
      0,
      true
    );
  }

  if (response.headers.get('X-Proxy-Backend-Down') === '1') {
    throw new ApiError(
      `Can't reach the backend at ${API_BASE_URL}. Start it and retry.`,
      0,
      true
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    const fieldErrors: Record<string, string> = {};
    try {
      const data = await response.json();
      if (data && typeof data === 'object') {
        if (typeof data.detail === 'string') {
          detail = data.detail;
        } else if (Array.isArray(data.detail)) {
          detail = data.detail
            .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
            .join('; ');
        }
        if (Array.isArray(data.errors)) {
          for (const item of data.errors) {
            if (item && typeof item.field === 'string' && typeof item.message === 'string') {
              fieldErrors[item.field] = item.message;
            }
          }
        }
      }
    } catch {
      const text = await response.text().catch(() => '');
      if (text) detail = text;
    }
    throw new ApiError(detail, response.status, false, fieldErrors);
  }

  return (await response.json()) as T;
}

export const api = {
  checkHealth: () => request<{ ok: boolean; demo_offline: boolean }>('/health'),

  listLessons: () => request<LessonListItem[]>('/lessons'),

  createLesson: (title: string, objective: string) =>
    request<LessonCreatedOut>('/lessons', {
      method: 'POST',
      body: JSON.stringify({ title, objective }),
    }),

  runLesson: (lessonId: number) =>
    request<RunAccepted>(`/lessons/${lessonId}/run`, {
      method: 'POST',
    }),

  getLesson: (lessonId: number) => request<LessonDetailResponse>(`/lessons/${lessonId}`),

  editContent: (lessonId: number, payload: ContentEditRequest) =>
    request<{ version_no: number; message: string }>(`/lessons/${lessonId}/content`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getPreview: (lessonId: number) =>
    request<{ version_no: number; markdown: string }>(`/lessons/${lessonId}/preview`),

  getSteps: (lessonId: number, includeOutput = false) =>
    request<StepOut[]>(
      `/lessons/${lessonId}/steps${includeOutput ? '?include_output=true' : ''}`
    ),

  retryStep: (lessonId: number, stepName: string) =>
    request<RunAccepted>(`/lessons/${lessonId}/steps/${encodeURIComponent(stepName)}/retry`, {
      method: 'POST',
    }),

  listVersions: (lessonId: number) =>
    request<VersionSummary[]>(`/lessons/${lessonId}/versions`),

  getVersion: (lessonId: number, versionNo: number) =>
    request<LessonVersionData>(`/lessons/${lessonId}/versions/${versionNo}`),

  restoreVersion: (lessonId: number, versionNo: number) =>
    request<{ version_no: number; message: string }>(
      `/lessons/${lessonId}/versions/${versionNo}/restore`,
      { method: 'POST' }
    ),

  getQC: (lessonId: number) => request<QCResponse>(`/lessons/${lessonId}/qc`),

  rerunQC: (lessonId: number, layer: QCLayer) =>
    request<{ message: string }>(`/lessons/${lessonId}/qc/${layer}`, {
      method: 'POST',
    }),

  previewFix: (issueId: number) =>
    request<PreviewFixResponse>(`/qc/issues/${issueId}/preview-fix`, {
      method: 'POST',
    }),

  applyFix: (
    issueId: number,
    payload: {
      section_id?: string | null;
      content_md?: string | null;
      quiz_index?: number | null;
      quiz_item?: QuizItem | null;
    }
  ) =>
    request<{ version_no: number; message: string }>(`/qc/issues/${issueId}/apply`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  dismissIssue: (issueId: number) =>
    request<{ message: string }>(`/qc/issues/${issueId}/dismiss`, {
      method: 'POST',
    }),

  fetchExportZip: async (
    lessonId: number
  ): Promise<{ blob: Blob; fileNames: string[]; filename: string }> => {
    let response: Response;
    try {
      response = await fetch(resolveFetchUrl(`/lessons/${lessonId}/export`));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new ApiError(
        `Can't reach the backend at ${API_BASE_URL}. Start it and retry. (${msg})`,
        0,
        true
      );
    }

    if (response.headers.get('X-Proxy-Backend-Down') === '1') {
      throw new ApiError(
        `Can't reach the backend at ${API_BASE_URL}. Start it and retry.`,
        0,
        true
      );
    }

    if (!response.ok) {
      let detail = `HTTP ${response.status} ${response.statusText}`;
      try {
        const data = await response.json();
        if (data && typeof data.detail === 'string') detail = data.detail;
      } catch {
        // ignore
      }
      throw new ApiError(detail, response.status, false);
    }

    const buffer = await response.arrayBuffer();
    const headerFiles = response.headers.get('X-Export-Files');
    const parsedFiles = parseZipFileNames(buffer);
    const fileNames =
      headerFiles && headerFiles.trim()
        ? headerFiles.split(',').map((s) => s.trim())
        : parsedFiles;

    return {
      blob: new Blob([buffer], { type: 'application/zip' }),
      fileNames,
      filename: `lesson-${lessonId}.zip`,
    };
  },
};
