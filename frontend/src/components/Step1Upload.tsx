import { useState, useRef } from 'react';
import { UploadCloud, SlidersHorizontal, ChevronDown, FileText, X, Loader, Sparkles, Layers, CheckCircle2 } from 'lucide-react';
import { api, ExtractResponse } from '../api';

interface Step1Props {
  onExtractSuccess: (res: ExtractResponse) => void;
}

export function Step1Upload({ onExtractSuccess }: Step1Props) {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [language, setLanguage] = useState('pt');
  const [minInterval, setMinInterval] = useState(2.5);
  const [subtitleFile, setSubtitleFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [progressStage, setProgressStage] = useState<'upload' | 'transcription' | 'extraction' | 'done'>('upload');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const videoRef = useRef<HTMLInputElement>(null);
  const subtitleRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) setVideoFile(file);
  };

  const fmt = (b: number) => b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${(b / 1e6).toFixed(1)} MB`;

  const ctaLabel = subtitleFile
    ? 'Extrair prints com legenda fornecida'
    : 'Extrair prints e transcrição';

  const handleProcess = async () => {
    if (!videoFile || loading) return;
    setLoading(true);
    setErrorMsg(null);
    setProgressPercent(2);
    setProgressStage('upload');
    setProgressMessage('Iniciando envio do vídeo...');

    try {
      const res = await api.extractVideo(
        videoFile,
        subtitleFile,
        language,
        minInterval,
        88,
        (percent, message, stage) => {
          setProgressPercent(percent);
          setProgressMessage(message);
          setProgressStage(stage as any);
        }
      );
      onExtractSuccess(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Ocorreu um erro ao processar o vídeo.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-8 py-16">
      <div className="w-full max-w-xl">

        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-[28px] font-semibold text-[#111827] tracking-tight mb-2">
            Carregue o vídeo de treinamento
          </h1>
          <p className="text-[15px] text-[#9CA3AF]">
            A transcrição e os prints serão extraídos automaticamente.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !videoFile && videoRef.current?.click()}
          className={`relative rounded-2xl border-2 border-dashed transition-all duration-200 cursor-pointer ${
            dragging
              ? 'border-[#10B981] bg-[#ECFDF5] scale-[1.01]'
              : videoFile
              ? 'border-[#10B981] bg-[#F0FDF9] cursor-default'
              : 'border-[#E5E7EB] bg-white hover:border-[#10B981] hover:bg-[#F9FAFB]'
          }`}
        >
          <input
            ref={videoRef}
            type="file"
            accept=".mp4,.mkv,.mov,.avi,.webm"
            className="hidden"
            onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
          />

          <div className="px-8 py-12 flex flex-col items-center gap-4 text-center">
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors ${
              videoFile ? 'bg-[#10B981]' : 'bg-[#F3F4F6]'
            }`}>
              <UploadCloud className={`w-7 h-7 ${videoFile ? 'text-white' : 'text-[#9CA3AF]'}`} />
            </div>

            {videoFile ? (
              <div>
                <p className="text-[16px] font-semibold text-[#111827]">{videoFile.name}</p>
                <p className="text-[13px] text-[#6B7280] mt-1">{fmt(videoFile.size)}</p>
                <button
                  onClick={(e) => { e.stopPropagation(); setVideoFile(null); }}
                  className="mt-3 text-[12px] text-[#9CA3AF] hover:text-[#EF4444] transition-colors underline underline-offset-2"
                >
                  Remover arquivo
                </button>
              </div>
            ) : (
              <div>
                <p className="text-[15px] font-medium text-[#374151]">
                  Arraste o arquivo aqui ou{' '}
                  <span className="text-[#10B981]">clique para selecionar</span>
                </p>
                <p className="text-[12px] text-[#C4C9D4] mt-1.5">MP4, MKV, MOV, AVI, WEBM · até 10 GB</p>
              </div>
            )}
          </div>
        </div>

        {/* Error Feedback */}
        {errorMsg && (
          <div className="mt-4 p-4 bg-[#FEF2F2] border border-[#FECACA] rounded-xl text-[13px] text-[#B91C1C]">
            {errorMsg}
          </div>
        )}

        {/* Progress Card durante processamento */}
        {loading && (
          <div className="mt-5 p-5 bg-white border border-[#E5E7EB] rounded-2xl shadow-sm flex flex-col gap-3.5">
            {/* Header com indicador de etapa e porcentagem */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[#ECFDF5] flex items-center justify-center text-[#10B981] flex-shrink-0">
                  {progressStage === 'upload' && <UploadCloud className="w-5 h-5 animate-pulse" />}
                  {progressStage === 'transcription' && <Sparkles className="w-5 h-5 animate-spin" />}
                  {progressStage === 'extraction' && <Layers className="w-5 h-5 animate-pulse" />}
                  {progressStage === 'done' && <CheckCircle2 className="w-5 h-5 text-[#10B981]" />}
                </div>
                <div>
                  <span className="text-[11px] uppercase tracking-wider font-semibold text-[#10B981]">
                    {progressStage === 'upload' && 'Fase 1 de 3 · Upload do Vídeo'}
                    {progressStage === 'transcription' && 'Fase 2 de 3 · Transcrição de Fala'}
                    {progressStage === 'extraction' && 'Fase 3 de 3 · Extração & Similaridade de Telas'}
                    {progressStage === 'done' && 'Concluído · Preparando Auditoria'}
                  </span>
                  <p className="text-[14px] font-medium text-[#111827] mt-0.5">{progressMessage}</p>
                </div>
              </div>

              <div className="text-right">
                <span className="text-[22px] font-bold font-mono text-[#111827] leading-none">
                  {progressPercent}%
                </span>
              </div>
            </div>

            {/* Barra de Progresso com Gradiente Esmeralda */}
            <div className="w-full bg-[#F3F4F6] rounded-full h-3 overflow-hidden p-0.5">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#10B981] to-[#059669] transition-all duration-300 ease-out"
                style={{ width: `${Math.max(4, Math.min(100, progressPercent))}%` }}
              />
            </div>

            {/* Rodapé explicativo */}
            <div className="flex items-center justify-between text-[12px] text-[#9CA3AF] pt-1 border-t border-[#F3F4F6]">
              <span>
                {progressStage === 'transcription'
                  ? 'Identificando falas e gerando timestamps sincronizados'
                  : progressStage === 'extraction'
                  ? 'Comparando similaridade e filtrando telas duplicadas'
                  : 'Transmitindo vídeo de treinamento para o servidor...'}
              </span>
              <span className="font-medium text-[#6B7280]">
                {progressPercent < 100 ? 'Processamento local' : 'Finalizando...'}
              </span>
            </div>
          </div>
        )}

        {/* CTA */}
        <button
          onClick={handleProcess}
          disabled={!videoFile || loading}
          className={`w-full mt-4 py-4 rounded-xl text-[15px] font-semibold transition-all duration-200 flex items-center justify-center gap-2 ${
            loading
              ? 'bg-[#1F2937] text-white opacity-90 cursor-wait'
              : videoFile
              ? 'bg-[#111827] text-white hover:bg-[#1F2937] shadow-sm hover:shadow'
              : 'bg-[#F3F4F6] text-[#C4C9D4] cursor-not-allowed'
          }`}
        >
          {loading ? (
            <>
              <Loader className="w-5 h-5 animate-spin" />
              <span>Processando... ({progressPercent}%)</span>
            </>
          ) : (
            ctaLabel
          )}
        </button>

        {/* Preferences */}
        <div className="mt-8">
          <button
            onClick={() => setPrefsOpen(!prefsOpen)}
            className="w-full flex items-center justify-between text-[13px] text-[#9CA3AF] hover:text-[#6B7280] transition-colors py-2"
          >
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Preferências de extração</span>
            </div>
            <ChevronDown className={`w-4 h-4 transition-transform ${prefsOpen ? 'rotate-180' : ''}`} />
          </button>

          {prefsOpen && (
            <div className="mt-3 bg-white border border-[#E5E7EB] rounded-xl px-5 py-5 flex flex-col gap-6">

              {/* Subtitle file */}
              <div>
                <label className="block text-[12px] font-medium text-[#374151] mb-1.5">
                  Arquivo de legenda <span className="font-normal text-[#9CA3AF]">— opcional, acelera o processamento</span>
                </label>
                <input
                  ref={subtitleRef}
                  type="file"
                  accept=".srt,.vtt,.sbv"
                  className="hidden"
                  onChange={(e) => setSubtitleFile(e.target.files?.[0] || null)}
                />
                {subtitleFile ? (
                  <div className="flex items-center gap-3 px-4 py-3 bg-[#F0FDF9] border border-[#6EE7B7] rounded-xl">
                    <FileText className="w-4 h-4 text-[#10B981] flex-shrink-0" />
                    <span className="text-[13px] text-[#065F46] flex-1 truncate">{subtitleFile.name}</span>
                    <button
                      onClick={() => setSubtitleFile(null)}
                      className="text-[#9CA3AF] hover:text-[#EF4444] transition-colors flex-shrink-0"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => subtitleRef.current?.click()}
                    className="w-full flex items-center gap-3 px-4 py-3 border border-dashed border-[#E5E7EB] rounded-xl text-[13px] text-[#9CA3AF] hover:border-[#10B981] hover:text-[#374151] transition-colors"
                  >
                    <FileText className="w-4 h-4" />
                    Selecionar arquivo .srt, .vtt ou .sbv
                  </button>
                )}
              </div>

              {/* Language */}
              <div>
                <label className="block text-[12px] font-medium text-[#374151] mb-1.5">Idioma da fala</label>
                <div className="flex gap-2">
                  {[
                    { id: 'pt', label: 'Português' },
                    { id: 'en', label: 'Inglês' },
                    { id: 'auto', label: 'Auto' },
                  ].map((l) => (
                    <button
                      key={l.id}
                      onClick={() => setLanguage(l.id)}
                      className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                        language === l.id
                          ? 'bg-[#111827] text-white'
                          : 'bg-[#F3F4F6] text-[#6B7280] hover:bg-[#E5E7EB]'
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Min interval */}
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-[12px] font-medium text-[#374151]">Intervalo mínimo entre prints</label>
                  <span className="font-mono text-[12px] text-[#10B981] font-semibold">{minInterval.toFixed(1)}s</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="0.5"
                  value={minInterval}
                  onChange={(e) => setMinInterval(parseFloat(e.target.value))}
                  className="w-full accent-[#10B981] cursor-pointer"
                />
                <div className="flex justify-between text-[11px] text-[#C4C9D4] mt-1">
                  <span>1s (mais prints)</span>
                  <span>10s (menos prints)</span>
                </div>
              </div>

            </div>
          )}
        </div>

      </div>
    </div>
  );
}
