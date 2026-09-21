import { Video, RotateCcw, CheckCircle, Circle, ChevronRight } from 'lucide-react';

const steps = [
  { id: 1, label: 'Upload & Configuração', sublabel: 'Vídeo e transcrição' },
  { id: 2, label: 'Auditoria de Prints', sublabel: 'Validação visual' },
  { id: 3, label: 'Compilação do Documento', sublabel: 'Exportação e nuvem' },
];

interface SidebarProps {
  currentStep: number;
  completedSteps: number[];
  onRestart: () => void;
}

export function Sidebar({ currentStep, completedSteps, onRestart }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 bg-white border-r border-[#E5E7EB] flex flex-col z-10">
      {/* Brand */}
      <div className="px-5 pt-6 pb-5">
        <div className="flex items-center gap-2.5 mb-1">
          <div className="w-8 h-8 rounded-lg bg-[#10B981] flex items-center justify-center flex-shrink-0">
            <Video className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-[#111827] text-sm leading-tight">VideoToDocument</span>
        </div>
        <p className="text-[11px] text-[#9CA3AF] leading-snug pl-[42px]">
          Vídeo + Legenda SRT → Documento Passo a Passo para NotebookLM
        </p>
      </div>

      <div className="mx-5 h-px bg-[#E5E7EB]" />

      {/* Stepper */}
      <div className="px-5 pt-5 flex-1">
        <p className="text-[11px] font-semibold text-[#9CA3AF] uppercase tracking-widest mb-4">
          Fluxo de Trabalho
        </p>
        <nav className="flex flex-col gap-1">
          {steps.map((step) => {
            const isDone = completedSteps.includes(step.id);
            const isActive = currentStep === step.id;
            const isPending = !isDone && !isActive;

            return (
              <div
                key={step.id}
                className={`flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  isActive ? 'bg-[#ECFDF5]' : 'hover:bg-[#F9FAFB]'
                }`}
              >
                <div className="mt-0.5 flex-shrink-0">
                  {isDone ? (
                    <CheckCircle className="w-4 h-4 text-[#10B981]" />
                  ) : isActive ? (
                    <ChevronRight className="w-4 h-4 text-[#10B981]" />
                  ) : (
                    <Circle className="w-4 h-4 text-[#D1D5DB]" />
                  )}
                </div>
                <div>
                  <p
                    className={`text-[13px] font-medium leading-tight ${
                      isActive ? 'text-[#065F46]' : isDone ? 'text-[#374151]' : 'text-[#9CA3AF]'
                    }`}
                  >
                    {step.id}. {step.label}
                  </p>
                  <p className={`text-[11px] mt-0.5 ${isActive ? 'text-[#6EE7B7]' : 'text-[#D1D5DB]'}`}>
                    {step.sublabel}
                  </p>
                </div>
              </div>
            );
          })}
        </nav>
      </div>

      <div className="mx-5 h-px bg-[#E5E7EB]" />

      {/* Restart */}
      <div className="px-5 py-4">
        <button
          onClick={onRestart}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-[13px] text-[#6B7280] border border-[#E5E7EB] rounded-lg hover:bg-[#F9FAFB] hover:text-[#374151] transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reiniciar Sessão / Novo Vídeo
        </button>
      </div>

      <div className="mx-5 h-px bg-[#E5E7EB]" />

      {/* Version */}
      <div className="px-5 py-3 flex flex-col gap-0.5">
        <span className="text-[11px] text-[#9CA3AF]">
          <span className="font-medium text-[#6B7280]">Versão:</span>{' '}
          <span className="font-mono text-[10px] text-[#10B981]">v1.2.0</span>
        </span>
        <span className="text-[10px] text-[#C4C9D4]">Build: main (sem OCR)</span>
      </div>
    </aside>
  );
}
