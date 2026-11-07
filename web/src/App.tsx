import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { api, API_BASE_URL } from './api/client';
import { StepOut } from './types/api';
import { HomeScreen } from './components/HomeScreen';
import { DottedGlobeScreen } from './components/DottedGlobeScreen';
import { CoursePlayerScreen } from './components/CoursePlayerScreen';

type ScreenView =
  | { type: 'home' }
  | { type: 'globe'; lessonId: number; initialSteps: StepOut[] }
  | { type: 'player'; lessonId: number };

function parseHash(): ScreenView {
  const hash = window.location.hash.replace(/^#/, '');
  const globeMatch = hash.match(/^\/?globe\/(\d+)$/);
  if (globeMatch) {
    return { type: 'globe', lessonId: Number(globeMatch[1]), initialSteps: [] };
  }
  const lessonMatch = hash.match(/^\/?lesson\/(\d+)$/);
  if (lessonMatch) {
    return { type: 'player', lessonId: Number(lessonMatch[1]) };
  }
  return { type: 'home' };
}

export const App: React.FC = () => {
  const [view, setView] = useState<ScreenView>(() => parseHash());
  const [backendDownMsg, setBackendDownMsg] = useState<string | null>(null);
  const [retryingHealth, setRetryingHealth] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    const onHashChange = () => {
      setView(parseHash());
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const handleNetworkError = useCallback((msg: string | null) => {
    setBackendDownMsg(msg);
  }, []);

  const handleRetryBackend = async () => {
    setRetryingHealth(true);
    try {
      await api.checkHealth();
      setBackendDownMsg(null);
      setRefreshTrigger((prev) => prev + 1);
    } catch {
      const hostDisplay = API_BASE_URL.replace(/^https?:\/\//, '');
      setBackendDownMsg(`Can't reach the backend at ${hostDisplay}. Start it and retry.`);
    } finally {
      setRetryingHealth(false);
    }
  };

  const handleStartPipeline = (lessonId: number, initialSteps: StepOut[]) => {
    window.location.hash = `/globe/${lessonId}`;
    setView({ type: 'globe', lessonId, initialSteps });
  };

  const handleOpenLesson = (lessonId: number) => {
    window.location.hash = `/lesson/${lessonId}`;
    setView({ type: 'player', lessonId });
  };

  const handleBackHome = () => {
    window.location.hash = '/';
    setView({ type: 'home' });
    setRefreshTrigger((prev) => prev + 1);
  };

  const hostDisplay = API_BASE_URL.replace(/^https?:\/\//, '');

  return (
    <div className="min-h-screen bg-[#FAFAF8] text-[#1C1D1F] flex flex-col">
      {/* Top Banner when Backend is Down */}
      {backendDownMsg && (
        <div
          role="alert"
          className="w-full bg-[#FDECEB] border-b border-[#F5BDBA] px-4 py-2.5 text-[#B42318] flex items-center justify-between gap-4 z-50"
        >
          <div className="flex items-center gap-2 text-[13.5px] font-medium">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              Can't reach the backend at {hostDisplay}. Start it and retry.
            </span>
          </div>
          <button
            type="button"
            disabled={retryingHealth}
            onClick={handleRetryBackend}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-[5px] bg-white border border-[#F5BDBA] text-[#B42318] hover:bg-[#FDECEB] text-[12.5px] font-semibold shrink-0"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${retryingHealth ? 'animate-spin' : ''}`} />
            <span>{retryingHealth ? 'Checking…' : 'Retry'}</span>
          </button>
        </div>
      )}

      {/* Main Screen Router with subtle motion */}
      <div className="flex-1 relative">
        <AnimatePresence mode="wait">
          {view.type === 'home' && (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              <HomeScreen
                onStartPipeline={handleStartPipeline}
                onOpenLesson={handleOpenLesson}
                onNetworkError={handleNetworkError}
                refreshTrigger={refreshTrigger}
              />
            </motion.div>
          )}

          {view.type === 'globe' && (
            <motion.div
              key={`globe-${view.lessonId}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <DottedGlobeScreen
                lessonId={view.lessonId}
                initialSteps={view.initialSteps}
                onComplete={() => handleOpenLesson(view.lessonId)}
                onBackHome={handleBackHome}
                onNetworkError={handleNetworkError}
              />
            </motion.div>
          )}

          {view.type === 'player' && (
            <motion.div
              key={`player-${view.lessonId}-${refreshTrigger}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              <CoursePlayerScreen
                lessonId={view.lessonId}
                onBackHome={handleBackHome}
                onNetworkError={handleNetworkError}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default App;
