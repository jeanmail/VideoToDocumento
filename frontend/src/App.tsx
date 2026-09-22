import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Step1Upload } from './components/Step1Upload';
import { Step2Audit } from './components/Step2Audit';
import { Step3Export } from './components/Step3Export';
import { FrameItem, ExtractResponse } from './api';

export default function App() {
  const [step, setStep] = useState(1);
  const [completed, setCompleted] = useState<number[]>([]);
  const [videoName, setVideoName] = useState('');
  const [frames, setFrames] = useState<FrameItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string>('');

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
    <div className="min-h-screen bg-[#F8F9FB] flex">
      <Sidebar currentStep={step} completedSteps={completed} onRestart={restart} />

      <main className="ml-60 flex-1 min-h-screen overflow-y-auto">
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
