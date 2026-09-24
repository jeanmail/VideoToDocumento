import { useState } from 'react';
import { Menu, Video } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Step1Upload } from './components/Step1Upload';
import { Step2Audit } from './components/Step2Audit';
import { Step3Export } from './components/Step3Export';
import { FrameItem, ExtractResponse } from './api';
import { APP_VERSION } from './version';

export default function App() {
  const [step, setStep] = useState(1);
  const [completed, setCompleted] = useState<number[]>([]);
  const [videoName, setVideoName] = useState('');
  const [frames, setFrames] = useState<FrameItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string>('');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleExtractSuccess = (res: ExtractResponse) => {
    setVideoName(res.video_name);
    setFrames(res.frames);
    setSelectedIds(res.frames.filter(f => f.selected).map(f => f.id));
    setJobId((res as any).job_id || '');
    setCompleted(prev => prev.includes(1) ? prev : [...prev, 1]);
    setStep(2);
  };

  const handleAuditAdvance = (approvedFrameIds: string[]) => {
    setSelectedIds(approvedFrameIds);
    setCompleted(prev => prev.includes(2) ? prev : [...prev, 2]);
    setStep(3);
  };

  const back = () => setStep(s => Math.max(1, s - 1));

  const restart = () => {
    setStep(1);
    setCompleted([]);
    setVideoName('');
    setFrames([]);
    setSelectedIds([]);
    setJobId('');
  };

  return (
    <div className="min-h-screen bg-[#F8F9FB] flex flex-col md:flex-row">
      {/* Barra de Navegação Superior Mobile (visível apenas em telas menores que md) */}
      <header className="md:hidden sticky top-0 z-30 bg-white border-b border-[#E5E7EB] px-4 py-3 flex items-center justify-between shadow-2xs">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-1 text-[#374151] hover:text-[#111827] hover:bg-[#F3F4F6] rounded-xl transition-colors cursor-pointer"
            aria-label="Abrir menu de navegação"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#10B981] flex items-center justify-center flex-shrink-0">
              <Video className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-semibold text-[#111827] text-sm">VideoToDocument</span>
          </div>
        </div>

        <span className="font-mono text-[11px] text-[#10B981] bg-[#ECFDF5] px-2 py-0.5 rounded-md font-semibold">
          {APP_VERSION}
        </span>
      </header>

      {/* Sidebar (Gaveta no Mobile, Fixa no Desktop) */}
      <Sidebar
        currentStep={step}
        completedSteps={completed}
        onRestart={restart}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Conteúdo Principal Adaptativo */}
      <main className="flex-1 md:ml-60 min-h-[calc(100vh-57px)] md:min-h-screen overflow-y-auto">
        {step === 1 && <Step1Upload onExtractSuccess={handleExtractSuccess} />}
        {step === 2 && (
          <Step2Audit
            initialFrames={frames}
            onAdvance={handleAuditAdvance}
            onBack={back}
          />
        )}
        {step === 3 && (
          <Step3Export
            onBack={back}
            videoName={videoName}
            selectedFrameIds={selectedIds}
            jobId={jobId}
          />
        )}
      </main>
    </div>
  );
}
