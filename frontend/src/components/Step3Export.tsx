import { useState } from 'react';
import { FileText, File, FolderArchive, Cloud, Download, ChevronDown, CheckCircle, Loader } from 'lucide-react';
import { api } from '../api';

const PRODUCTS = [
  { id: 'prescricao-digital', label: 'Prescrição Digital', icon: '💊' },
  { id: 'automation', label: 'Automation', icon: '⚙️' },
  { id: 'onetouch', label: 'OneTouch', icon: '👆' },
  { id: 'personal', label: 'Personal', icon: '👤' },
  { id: 'clinic', label: 'Clinic', icon: '🏥' },
  { id: 'monitoring', label: 'Monitoring', icon: '📊' },
  { id: 'agenda-online', label: 'Agenda Online', icon: '📅' },
];

interface Step3Props {
  onBack: () => void;
  videoName?: string;
  selectedFrameIds: string[];
  jobId: string;
}

export function Step3Export({ onBack, videoName = '', selectedFrameIds, jobId }: Step3Props) {
  const [title, setTitle] = useState(videoName || 'Guia de Treinamento');
  const [description, setDescription] = useState('');
  const [product, setProduct] = useState('');
  const [bucketName, setBucketName] = useState('kb-contact-center');
  const [gcsExpanded, setGcsExpanded] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [gcsMessage, setGcsMessage] = useState<string | null>(null);

  const slug = String(title || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const effectiveBucket = bucketName.trim() || 'kb-contact-center';
  const gcsPath = product && slug ? `gs://${effectiveBucket}/${product}/${slug}/` : null;

  const handleDownload = (format: 'docx' | 'pdf' | 'zip') => {
    setGenerating(format);
    let url = '';
    if (format === 'docx') url = api.getDocxDownloadUrl(title, selectedFrameIds, jobId);
    else if (format === 'pdf') url = api.getPdfDownloadUrl(title, selectedFrameIds, jobId);
    else if (format === 'zip') url = api.getZipDownloadUrl(title, selectedFrameIds, jobId);

    // Dispara download no navegador
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => {
      setGenerating(null);
      setDone(prev => new Set([...prev, format]));
    }, 1200);
  };

  const handlePublishGCS = async () => {
    if (!product || !slug || generating) return;
    setGenerating('gcs');
    setGcsMessage(null);

    try {
      const res = await api.publishToGCS({
        title,
        description,
        product_slug: product,
        bucket_name: effectiveBucket,
        selected_frame_ids: selectedFrameIds,
        job_id: jobId,
      });

      if (res.success) {
        setDone(prev => new Set([...prev, 'gcs']));
        setGcsMessage(`✅ ${res.message}`);
      } else {
        setGcsMessage(`⚠️ ${res.message}`);
      }
    } catch (e: any) {
      setGcsMessage(`❌ ${e.message || 'Falha na comunicação com o GCS'}`);
    } finally {
      setGenerating(null);
    }
  };

  const metaFilled = title.trim().length > 0;

  return (
    <div className="min-h-full flex flex-col items-center justify-center px-4 sm:px-6 md:px-8 py-8 md:py-16">
      <div className="w-full max-w-xl">

        {/* Header */}
        <div className="mb-6 md:mb-10 text-center sm:text-left">
          <h1 className="text-[22px] sm:text-[26px] md:text-[28px] font-semibold text-[#111827] tracking-tight mb-2">
            Exporte o documento
          </h1>
          <p className="text-[14px] md:text-[15px] text-[#9CA3AF]">
            Preencha os dados e escolha o formato de saída.
          </p>
        </div>

        {/* Metadata */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl px-4 sm:px-6 py-4 sm:py-6 mb-5 sm:mb-6 flex flex-col gap-4">
          <div>
            <label className="block text-[12px] font-medium text-[#374151] mb-1.5">
              Título do documento <span className="text-[#EF4444]">*</span>
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex: Guia de Onboarding — Prescrição Digital"
              className="w-full border border-[#E5E7EB] rounded-xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-[13px] sm:text-[14px] text-[#111827] placeholder:text-[#D1D5DB] focus:outline-none focus:ring-2 focus:ring-[#111827] focus:border-transparent transition-shadow"
            />
          </div>
          <div>
            <label className="block text-[12px] font-medium text-[#374151] mb-1.5">Descrição breve</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Descreva o conteúdo coberto neste treinamento..."
              rows={3}
              className="w-full border border-[#E5E7EB] rounded-xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-[13px] sm:text-[14px] text-[#111827] placeholder:text-[#D1D5DB] focus:outline-none focus:ring-2 focus:ring-[#111827] focus:border-transparent transition-shadow resize-none"
            />
          </div>
        </div>

        {/* Export options */}
        <div className="flex flex-col gap-3 mb-6">

          {/* DOCX */}
          <ExportCard
            icon={<FileText className="w-5 h-5 text-[#6366F1]" />}
            iconBg="bg-[#EEF2FF]"
            label="Documento Word"
            sub=".docx — transcrição completa intercalada com prints"
            disabled={!metaFilled}
            state={done.has('docx') ? 'done' : generating === 'docx' ? 'loading' : 'idle'}
            onClick={() => handleDownload('docx')}
          />

          {/* PDF */}
          <ExportCard
            icon={<File className="w-5 h-5 text-[#EF4444]" />}
            iconBg="bg-[#FEF2F2]"
            label="Documento PDF"
            sub=".pdf — visualização portátil formatada"
            disabled={!metaFilled}
            state={done.has('pdf') ? 'done' : generating === 'pdf' ? 'loading' : 'idle'}
            onClick={() => handleDownload('pdf')}
          />

          {/* Project ZIP */}
          <ExportCard
            icon={<FolderArchive className="w-5 h-5 text-[#10B981]" />}
            iconBg="bg-[#ECFDF5]"
            label="Projeto exportável"
            sub=".zip — documento PDF + imagens + knowledge_base.md"
            disabled={!metaFilled}
            state={done.has('zip') ? 'done' : generating === 'zip' ? 'loading' : 'idle'}
            onClick={() => handleDownload('zip')}
          />

          {/* GCS Cloud */}
          <div className={`bg-white border rounded-2xl overflow-hidden transition-all ${
            gcsExpanded ? 'border-[#3B82F6]' : 'border-[#E5E7EB]'
          }`}>
            <button
              disabled={!metaFilled}
              onClick={() => setGcsExpanded(!gcsExpanded)}
              className={`w-full flex items-center gap-4 px-5 py-4 transition-colors ${
                !metaFilled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#F8FAFF]'
              }`}
            >
              <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] flex items-center justify-center flex-shrink-0">
                <Cloud className="w-5 h-5 text-[#3B82F6]" />
              </div>
              <div className="flex-1 text-left">
                <p className="text-[14px] font-semibold text-[#111827]">Publicar na base de conhecimento</p>
                <p className="text-[12px] text-[#9CA3AF]">GCS · configurar destino</p>
              </div>
              <ChevronDown className={`w-4 h-4 text-[#9CA3AF] transition-transform ${gcsExpanded ? 'rotate-180' : ''}`} />
            </button>

            {gcsExpanded && (
              <div className="border-t border-[#EFF6FF] px-4 sm:px-5 py-4 sm:py-5 flex flex-col gap-4">

                {/* Bucket name editable */}
                <div>
                  <label className="block text-[12px] font-medium text-[#374151] mb-1.5">
                    Nome do Bucket no GCS
                  </label>
                  <input
                    type="text"
                    value={bucketName}
                    onChange={(e) => setBucketName(e.target.value)}
                    placeholder="Ex: kb-contact-center"
                    className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-[12px] sm:text-[13px] font-mono text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#3B82F6] focus:border-transparent transition-shadow"
                  />
                  <p className="text-[11px] text-[#9CA3AF] mt-1">Bucket central onde serão criadas as pastas dos produtos.</p>
                </div>

                {/* Product */}
                <div>
                  <label className="block text-[12px] font-medium text-[#374151] mb-2">Produto de destino</label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {PRODUCTS.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setProduct(p.id)}
                        className={`flex flex-col items-center gap-1 px-2 py-3 rounded-xl border text-center transition-all cursor-pointer ${
                          product === p.id
                            ? 'border-[#3B82F6] bg-[#EFF6FF]'
                            : 'border-[#E5E7EB] bg-white hover:border-[#BFDBFE]'
                        }`}
                      >
                        <span className="text-lg">{p.icon}</span>
                        <span className={`text-[10px] font-medium leading-tight ${
                          product === p.id ? 'text-[#1D4ED8]' : 'text-[#6B7280]'
                        }`}>
                          {p.label}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* GCS path preview */}
                {gcsPath && (
                  <div className="bg-[#F0F9FF] border border-[#BAE6FD] rounded-xl px-4 py-3">
                    <p className="text-[10px] font-medium text-[#0369A1] mb-0.5 uppercase tracking-wide">Destino no GCS</p>
                    <p className="text-[13px] font-mono text-[#0284C7] break-all">{gcsPath}</p>
                  </div>
                )}

                {/* GCS message feedback */}
                {gcsMessage && (
                  <div className="text-[12px] text-[#374151] p-3 rounded-lg bg-[#F3F4F6]">
                    {gcsMessage}
                  </div>
                )}

                {/* Publish button */}
                <button
                  onClick={handlePublishGCS}
                  disabled={!product || !slug || !!generating}
                  className={`w-full py-3.5 rounded-xl text-[14px] font-semibold transition-all flex items-center justify-center gap-2 ${
                    done.has('gcs')
                      ? 'bg-[#ECFDF5] text-[#065F46]'
                      : generating === 'gcs'
                      ? 'bg-[#DBEAFE] text-[#3B82F6] cursor-not-allowed'
                      : !product || !slug
                      ? 'bg-[#F3F4F6] text-[#C4C9D4] cursor-not-allowed'
                      : 'bg-[#3B82F6] text-white hover:bg-[#2563EB]'
                  }`}
                >
                  {done.has('gcs') ? (
                    <><CheckCircle className="w-4 h-4" /> Publicado com sucesso</>
                  ) : generating === 'gcs' ? (
                    <><Loader className="w-4 h-4 animate-spin" /> Publicando...</>
                  ) : (
                    <>☁️ Publicar na base de conhecimento</>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Back */}
        <button onClick={onBack} className="text-[13px] text-[#9CA3AF] hover:text-[#374151] transition-colors">
          ← Voltar à auditoria
        </button>
      </div>
    </div>
  );
}

// ── Sub-component ──────────────────────────────────────────────

interface ExportCardProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  sub: string;
  disabled: boolean;
  state: 'idle' | 'loading' | 'done';
  onClick: () => void;
}

function ExportCard({ icon, iconBg, label, sub, disabled, state, onClick }: ExportCardProps) {
  return (
    <div className={`bg-white border border-[#E5E7EB] rounded-2xl px-4 sm:px-5 py-3.5 sm:py-4 flex items-center justify-between gap-3 sm:gap-4 transition-all ${
      disabled ? 'opacity-40' : 'hover:border-[#9CA3AF] hover:shadow-sm'
    }`}>
      <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
        <div className={`w-9 h-9 sm:w-10 sm:h-10 rounded-xl ${iconBg} flex items-center justify-center flex-shrink-0`}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] sm:text-[14px] font-semibold text-[#111827] truncate">{label}</p>
          <p className="text-[11px] sm:text-[12px] text-[#9CA3AF] line-clamp-1">{sub}</p>
        </div>
      </div>
      <button
        onClick={onClick}
        disabled={disabled || state === 'loading'}
        className={`flex items-center justify-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-xl text-[12px] sm:text-[13px] font-medium transition-all flex-shrink-0 cursor-pointer ${
          state === 'done'
            ? 'bg-[#ECFDF5] text-[#065F46]'
            : state === 'loading'
            ? 'bg-[#F3F4F6] text-[#9CA3AF] cursor-not-allowed'
            : disabled
            ? 'bg-[#F3F4F6] text-[#C4C9D4] cursor-not-allowed'
            : 'bg-[#111827] text-white hover:bg-[#1F2937]'
        }`}
      >
        {state === 'done' ? (
          <><CheckCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4" /> <span className="hidden xs:inline">Baixado</span></>
        ) : state === 'loading' ? (
          <><Loader className="w-3.5 h-3.5 sm:w-4 sm:h-4 animate-spin" /> <span className="hidden xs:inline">Gerando...</span></>
        ) : (
          <><Download className="w-3.5 h-3.5 sm:w-4 sm:h-4" /> <span>Baixar</span></>
        )}
      </button>
    </div>
  );
}
