import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, RotateCcw, ArrowLeft } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { StepOut } from '../types/api';

const STEP_LABELS: Record<string, string> = {
  plan: 'Planning learning outcomes and research queries…',
  research_web: 'Researching web sources…',
  research_youtube: 'Searching educational videos…',
  research_books: 'Checking book catalogues…',
  score_sources: 'Scoring source reliability…',
  generate: 'Writing lesson…',
  timebudget: 'Calculating 45-minute time budget…',
  qc_factual: 'Running fact check…',
  qc_instructional: 'Running teaching quality review…',
};

const OPTIONAL_STEPS = new Set(['research_youtube', 'research_books']);
const NUM_DOTS = 1200;
const MIN_DISPLAY_MS = 2500;
const POLL_INTERVAL_MS = 2000;
const TILT_RAD = (20 * Math.PI) / 180; // 20° axial tilt

interface Point3D {
  x: number;
  y: number;
  z: number;
}

function generateFibonacciSphere(count: number): Point3D[] {
  const points: Point3D[] = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2; // y from 1 to -1
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * radius;
    const z = Math.sin(theta) * radius;
    points.push({ x, y, z });
  }
  return points;
}

interface DottedGlobeScreenProps {
  lessonId: number;
  initialSteps?: StepOut[];
  onComplete: () => void;
  onBackHome: () => void;
  onNetworkError?: (msg: string | null) => void;
}

export const DottedGlobeScreen: React.FC<DottedGlobeScreenProps> = ({
  lessonId,
  initialSteps = [],
  onComplete,
  onBackHome,
  onNetworkError,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const startTimeRef = useRef<number>(performance.now());
  const [steps, setSteps] = useState<StepOut[]>(initialSteps);
  const [failedStep, setFailedStep] = useState<StepOut | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [exiting, setExiting] = useState(false);

  const spherePoints = useMemo(() => generateFibonacciSphere(NUM_DOTS), []);
  const pausedRef = useRef<boolean>(false);
  pausedRef.current = Boolean(failedStep);

  // Determine the current step label to show under the globe
  const currentStepText = useMemo(() => {
    if (failedStep) {
      return `Step "${failedStep.name}" encountered an error.`;
    }
    const running = steps.find((s) => s.status === 'running');
    if (running) {
      return STEP_LABELS[running.name] || `Running ${running.name}…`;
    }
    const pending = steps.find((s) => s.status === 'pending');
    if (pending) {
      return STEP_LABELS[pending.name] || `Preparing ${pending.name}…`;
    }
    if (steps.length > 0 && steps.every((s) => s.status === 'done' || OPTIONAL_STEPS.has(s.name))) {
      return 'Finalizing lesson workspace…';
    }
    return 'Researching sources…';
  }, [steps, failedStep]);

  // 60fps Canvas Fibonacci Globe Renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let rotationY = 0;
    let lastTime = performance.now();

    const cosTilt = Math.cos(TILT_RAD);
    const sinTilt = Math.sin(TILT_RAD);

    const resizeCanvas = () => {
      const dpr = window.devicePixelRatio || 1;
      const size = Math.min(window.innerWidth * 0.72, 340);
      canvas.style.width = `${size}px`;
      canvas.style.height = `${size}px`;
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Pre-allocate projection array to avoid GC pressure at 60fps
    const projected: Array<{ sx: number; sy: number; z: number; alpha: number; r: number }> =
      new Array(NUM_DOTS);

    const render = (now: number) => {
      const dt = Math.min(0.05, (now - lastTime) / 1000);
      lastTime = now;

      if (!pausedRef.current) {
        rotationY += dt * 0.42; // Calm, steady rotation speed
      }

      const dpr = window.devicePixelRatio || 1;
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      const cx = width / 2;
      const cy = height / 2;
      const sphereRadius = Math.min(width, height) * 0.41;

      ctx.clearRect(0, 0, width, height);

      const cosY = Math.cos(rotationY);
      const sinY = Math.sin(rotationY);

      for (let i = 0; i < NUM_DOTS; i++) {
        const p = spherePoints[i];
        // Rotate around Y axis
        const rx = p.x * cosY + p.z * sinY;
        const ry = p.y;
        const rz = -p.x * sinY + p.z * cosY;

        // Apply ~20° tilt around X/Z
        const tx = rx * cosTilt - ry * sinTilt;
        const ty = rx * sinTilt + ry * cosTilt;
        const tz = rz; // -1 (back) to +1 (front)

        // Perspective factor
        const perspective = 1 + tz * 0.14;
        const sx = cx + tx * sphereRadius * perspective;
        const sy = cy + ty * sphereRadius * perspective;

        // Back hemisphere fades smoothly to ~15% opacity (0.15), front reaches ~0.95
        const normalizedDepth = (tz + 1) * 0.5; // 0 at back, 1 at front
        const alpha =
          tz < 0
            ? 0.15 + Math.pow((tz + 1), 2) * 0.25
            : 0.4 + normalizedDepth * 0.55;

        const dotRadius = 1.15 + normalizedDepth * 0.95;

        projected[i] = { sx, sy, z: tz, alpha, r: dotRadius };
      }

      // Depth-sort back-to-front
      projected.sort((a, b) => a.z - b.z);

      for (let i = 0; i < NUM_DOTS; i++) {
        const dot = projected[i];
        ctx.beginPath();
        ctx.arc(dot.sx, dot.sy, dot.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(11, 79, 138, ${dot.alpha.toFixed(3)})`; // #0B4F8A
        ctx.fill();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [spherePoints]);

  // Poll GET /lessons/{id}/steps every 2s and enforce minimum 2.5s display time
  useEffect(() => {
    let cancelled = false;
    let pollTimer: number | undefined;
    let completionTimer: number | undefined;

    const checkSteps = async () => {
      try {
        const fetched = await api.getSteps(lessonId, false);
        if (cancelled) return;
        onNetworkError?.(null);
        setSteps(fetched);

        // Check if any required step failed, or if pipeline stopped with a failed step
        const anyRunningOrPending = fetched.some(
          (s) => s.status === 'running' || s.status === 'pending'
        );
        const requiredFailed = fetched.find(
          (s) => s.status === 'failed' && !OPTIONAL_STEPS.has(s.name)
        );

        if (requiredFailed && !anyRunningOrPending) {
          setFailedStep(requiredFailed);
          return;
        }

        if (!anyRunningOrPending && fetched.length > 0) {
          // Pipeline finished! Wait out remaining minimum 2.5s if needed, then exit (400ms)
          const elapsed = performance.now() - startTimeRef.current;
          const remaining = Math.max(0, MIN_DISPLAY_MS - elapsed);
          completionTimer = window.setTimeout(() => {
            if (cancelled) return;
            setExiting(true);
            window.setTimeout(() => {
              if (!cancelled) onComplete();
            }, 400);
          }, remaining);
          return;
        }

        pollTimer = window.setTimeout(checkSteps, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.isNetworkError) {
          onNetworkError?.(err.detail);
        }
        pollTimer = window.setTimeout(checkSteps, POLL_INTERVAL_MS);
      }
    };

    checkSteps();

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
      if (completionTimer) clearTimeout(completionTimer);
    };
  }, [lessonId, onComplete, onNetworkError, retrying]);

  const handleRetryFailedStep = async () => {
    if (!failedStep) return;
    setRetryError(null);
    setRetrying(true);
    try {
      await api.retryStep(lessonId, failedStep.name);
      setFailedStep(null);
      startTimeRef.current = performance.now();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : String(err);
      setRetryError(msg);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-[#FAFAF8] flex flex-col items-center justify-center select-none overflow-hidden z-40 px-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={
          exiting
            ? { opacity: 0, scale: 0.84, transition: { duration: 0.4, ease: 'easeOut' } }
            : { opacity: 1, scale: 1, transition: { duration: 0.25, ease: 'easeOut' } }
        }
        className="flex flex-col items-center justify-center"
      >
        <canvas
          ref={canvasRef}
          aria-label="Lesson generation progress globe"
          className="block"
        />

        {/* Single low-contrast status line cross-fading between pipeline steps */}
        {!failedStep && (
          <div className="h-8 mt-6 flex items-center justify-center">
            <AnimatePresence mode="wait">
              <motion.p
                key={currentStepText}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="text-[14px] text-[#76787C] font-normal tracking-wide text-center"
              >
                {currentStepText}
              </motion.p>
            </AnimatePresence>
          </div>
        )}

        {/* Centered failure card if a step fails */}
        {failedStep && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="mt-6 w-full max-w-md bg-white border border-[#E4E4E0] rounded-[8px] p-5 text-left"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-[#B42318] shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-serif text-[16px] font-semibold text-[#1C1D1F]">
                    Step failed: <span className="font-mono text-[14px]">{failedStep.name}</span>
                  </h3>
                  <span className="text-[12px] text-[#76787C]">
                    Attempt {failedStep.attempt}
                  </span>
                </div>
                <p className="mt-2 text-[13.5px] text-[#B42318] bg-[#FDECEB] border border-[#F5BDBA] rounded-[6px] p-3 font-mono whitespace-pre-wrap break-words leading-relaxed">
                  {failedStep.error || 'Step failed without an error message.'}
                </p>
                {retryError && (
                  <p className="mt-2 text-[13px] text-[#B42318]">{retryError}</p>
                )}
                <div className="mt-4 flex items-center gap-2.5">
                  <button
                    type="button"
                    disabled={retrying}
                    onClick={handleRetryFailedStep}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[6px] bg-[#0B4F8A] hover:bg-[#083D6B] text-white text-[13.5px] font-medium transition-colors disabled:opacity-50"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>{retrying ? 'Retrying…' : 'Retry this step'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={onBackHome}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[6px] border border-[#E4E4E0] bg-white hover:bg-[#F3F3EF] text-[#1C1D1F] text-[13.5px] font-medium transition-colors"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    <span>Back to home</span>
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
};
