import { useState } from 'react';
import { X, ZoomIn } from 'lucide-react';
import { FrameItem, api } from '../api';

type FilterType = 'approved' | 'all';

interface Step2Props {
  initialFrames: FrameItem[];
  onAdvance: (selectedIds: string[]) => void;
  onBack: () => void;
}

export function Step2Audit({ initialFrames, onAdvance, onBack }: Step2Props) {
  const [frames, setFrames] = useState<FrameItem[]>(initialFrames);
  const [filter, setFilter] = useState<FilterType>('approved');
  const [selected, setSelected] = useState<Set<string>>(
    new Set(initialFrames.filter(f => f.selected).map(f => f.id))
  );
  const [page, setPage] = useState(1);
  const [perPage] = useState(12);
  const [zoom, setZoom] = useState<FrameItem | null>(null);
  const [similarityThreshold, setSimilarityThreshold] = useState(85);

  // Aplica o limiar de similaridade de forma reativa conforme a spec
  const effectiveFrames = frames.map(f => {
    if (f.similarity_score > 0) {
      const isDup = (f.similarity_score * 100) >= similarityThreshold;
      return { ...f, is_duplicate_candidate: isDup };
    }
    return f;
  });

  const handleThresholdChange = (val: number) => {
    setSimilarityThreshold(val);
    setSelected(prev => {
      const next = new Set(prev);
      frames.forEach(f => {
        if (f.similarity_score > 0) {
          const simPct = f.similarity_score * 100;
          if (simPct >= val) {
            next.delete(f.id);
          } else {
            next.add(f.id);
          }
        }
      });
      return next;
    });
  };

  const filtered = effectiveFrames.filter(f => {
    if (filter === 'approved') {
      return !f.is_duplicate_candidate && !f.is_non_system_candidate;
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(filtered.map(f => f.id)));
  const deselectAll = () => setSelected(new Set());

  const updateTitle = (id: string, title: string) => {
    setFrames(prev => prev.map(f => f.id === id ? { ...f, step_title: title } : f));
  };

  const handleTimeAdjust = async (id: string, delta: number) => {
    try {
      const res = await api.adjustFrameTime(id, delta);
      if (res.success && res.frame) {
        setFrames(prev => prev.map(f => f.id === id ? { ...f, ...res.frame } : f));
        if (zoom && zoom.id === id) {
          setZoom(prev => prev ? { ...prev, ...res.frame } : null);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const approvedCount = effectiveFrames.filter(f => !f.is_duplicate_candidate && !f.is_non_system_candidate).length;
  const hiddenCount = effectiveFrames.filter(f => f.is_duplicate_candidate || f.is_non_system_candidate).length;

  return (
    <div className="flex flex-col h-screen">

      {/* Top bar */}
      <div className="bg-white border-b border-[#E5E7EB] px-8 py-4 flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-[17px] font-semibold text-[#111827]">Selecione os prints do treinamento</h1>
          <p className="text-[13px] text-[#9CA3AF] mt-0.5">
            {approvedCount} imagens únicas · {hiddenCount} similares/câmeras filtradas
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Filter toggle */}
          <div className="flex items-center bg-[#F3F4F6] rounded-lg p-0.5">
            <button
              onClick={() => { setFilter('approved'); setPage(1); }}
              className={`px-3.5 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                filter === 'approved'
                  ? 'bg-white text-[#111827] shadow-xs'
                  : 'text-[#6B7280] hover:text-[#111827]'
              }`}
            >
              Aprovadas
            </button>
            <button
              onClick={() => { setFilter('all'); setPage(1); }}
              className={`px-3.5 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                filter === 'all'
                  ? 'bg-white text-[#111827] shadow-xs'
                  : 'text-[#6B7280] hover:text-[#111827]'
              }`}
            >
              Todas
            </button>
          </div>

          <div className="h-4 w-px bg-[#E5E7EB]" />

          {/* Batch actions */}
          <button
            onClick={selectAll}
            className="text-[12px] text-[#6B7280] hover:text-[#111827] transition-colors"
          >
            Selecionar todas
          </button>
          <span className="text-[#D1D5DB]">·</span>
          <button
            onClick={deselectAll}
            className="text-[12px] text-[#6B7280] hover:text-[#111827] transition-colors"
          >
            Desmarcar todas
          </button>

          <div className="h-4 w-px bg-[#E5E7EB]" />

          {/* Advance button */}
          <button
            onClick={() => onAdvance(Array.from(selected))}
            disabled={selected.size === 0}
            className={`px-4 py-2 rounded-xl text-[13px] font-semibold transition-all ${
              selected.size > 0
                ? 'bg-[#111827] text-white hover:bg-[#1F2937]'
                : 'bg-[#F3F4F6] text-[#C4C9D4] cursor-not-allowed'
            }`}
          >
            Gerar documento ({selected.size})
          </button>
        </div>
      </div>

      {/* Similarity threshold strip - Fixo e alinhado à direita */}
      <div className="bg-[#FAFBFD] border-b border-[#E5E7EB] px-8 py-2 flex items-center justify-end text-[12px]">
        <div className="flex items-center gap-3">
          <span className="text-[#6B7280] font-medium">Ajustar Similaridade de Telas:</span>
          <input
            type="range"
            min="70"
            max="98"
            step="1"
            value={similarityThreshold}
            onChange={(e) => handleThresholdChange(parseInt(e.target.value))}
            className="w-36 accent-[#10B981] cursor-pointer"
          />
          <span className="font-mono text-[12px] text-[#10B981] font-semibold w-8 text-right">
            {similarityThreshold}%
          </span>
        </div>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="grid grid-cols-3 xl:grid-cols-4 gap-4">
          {paginated.map((p) => {
            const isSelected = selected.has(p.id);
            const isSimilar = p.is_duplicate_candidate;
            const isCamera = p.is_non_system_candidate;

            return (
              <div
                key={p.id}
                onClick={() => toggleSelect(p.id)}
                className={`bg-white rounded-xl border overflow-hidden cursor-pointer transition-all duration-150 ${
                  isSelected
                    ? 'border-[#111827] shadow-md ring-2 ring-[#111827] ring-offset-1'
                    : 'border-[#E5E7EB] hover:border-[#9CA3AF]'
                } ${(isSimilar || isCamera) && !isSelected ? 'opacity-50' : ''}`}
              >
                {/* Image */}
                <div className="relative aspect-video bg-[#F3F4F6] overflow-hidden group">
                  <img
                    src={p.thumb_url || p.image_url}
                    alt={p.step_title}
                    className="w-full h-full object-cover"
                    draggable={false}
                  />

                  {/* Zoom button */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setZoom(p); }}
                    className="absolute top-2 right-2 w-7 h-7 bg-black/50 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <ZoomIn className="w-3.5 h-3.5 text-white" />
                  </button>

                  {/* Status badge */}
                  {(isSimilar || isCamera) && (
                    <div className="absolute bottom-2 left-2">
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                        isSimilar
                          ? 'bg-[#FEF3C7] text-[#92400E]'
                          : 'bg-[#DBEAFE] text-[#1E40AF]'
                      }`}>
                        {isSimilar ? `${Math.round(p.similarity_score * 100)}% similar` : 'câmera'}
                      </span>
                    </div>
                  )}

                  {/* Checkbox overlay */}
                  <div className="absolute top-2 left-2">
                    <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
                      isSelected ? 'bg-[#111827] border-[#111827]' : 'bg-white/80 border-[#D1D5DB]'
                    }`}>
                      {isSelected && (
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 12 12">
                          <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>
                  </div>
                </div>

                {/* Title */}
                <div className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                  <input
                    value={p.step_title}
                    onChange={(e) => updateTitle(p.id, e.target.value)}
                    className="w-full text-[13px] font-medium text-[#111827] bg-transparent border-b border-transparent hover:border-[#D1D5DB] focus:border-[#111827] focus:outline-none transition-colors truncate"
                  />
                  <p className="font-mono text-[11px] text-[#9CA3AF] mt-0.5">{p.timestamp_str}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Pagination & Back */}
      <div className="bg-white border-t border-[#E5E7EB] px-8 py-3 flex items-center justify-between flex-shrink-0">
        <button
          onClick={onBack}
          className="text-[13px] text-[#9CA3AF] hover:text-[#374151] transition-colors"
        >
          ← Voltar ao upload
        </button>

        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded-lg text-[12px] border border-[#E5E7EB] text-[#374151] disabled:opacity-40"
            >
              Anterior
            </button>
            <span className="text-[12px] text-[#9CA3AF]">
              Página {page} de {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 rounded-lg text-[12px] border border-[#E5E7EB] text-[#374151] disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        )}
      </div>

      {/* Zoom modal */}
      {zoom && (
        <div
          onClick={() => setZoom(null)}
          className="fixed inset-0 bg-black/70 flex items-center justify-center p-8 z-50 animate-in fade-in duration-150"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl max-w-3xl w-full overflow-hidden shadow-2xl flex flex-col"
          >
            <div className="px-6 py-4 border-b border-[#E5E7EB] flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-[#111827] text-[15px]">{zoom.step_title}</h3>
                <span className="font-mono text-[11px] text-[#9CA3AF]">{zoom.timestamp_str}</span>
              </div>
              <button
                onClick={() => setZoom(null)}
                className="w-8 h-8 rounded-lg hover:bg-[#F3F4F6] flex items-center justify-center text-[#9CA3AF] hover:text-[#111827]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="aspect-video bg-black flex items-center justify-center">
              <img
                src={zoom.image_url}
                alt={zoom.step_title}
                className="max-h-full max-w-full object-contain"
              />
            </div>

            <div className="px-6 py-4 bg-[#F9FAFB] border-t border-[#E5E7EB] flex flex-col gap-3">
              {zoom.subtitle_text && (
                <div>
                  <p className="text-[11px] font-semibold text-[#9CA3AF] uppercase tracking-wider mb-1">Transcrição no momento:</p>
                  <p className="text-[13px] text-[#374151] italic leading-relaxed">"{zoom.subtitle_text}"</p>
                </div>
              )}

              {/* Botões de ajuste fino no modal */}
              <div className="flex items-center justify-between pt-2 border-t border-[#E5E7EB]">
                <span className="text-[12px] text-[#6B7280]">Ajuste fino de tempo no vídeo:</span>
                <div className="flex gap-2">
                  <button onClick={() => handleTimeAdjust(zoom.id, -1.0)} className="px-2.5 py-1 text-[11px] font-medium bg-white border border-[#D1D5DB] rounded-md hover:bg-[#F3F4F6]">⏪ -1s</button>
                  <button onClick={() => handleTimeAdjust(zoom.id, -0.5)} className="px-2.5 py-1 text-[11px] font-medium bg-white border border-[#D1D5DB] rounded-md hover:bg-[#F3F4F6]">◀ -0.5s</button>
                  <button onClick={() => handleTimeAdjust(zoom.id, 0.5)} className="px-2.5 py-1 text-[11px] font-medium bg-white border border-[#D1D5DB] rounded-md hover:bg-[#F3F4F6]">+0.5s ▶</button>
                  <button onClick={() => handleTimeAdjust(zoom.id, 1.0)} className="px-2.5 py-1 text-[11px] font-medium bg-white border border-[#D1D5DB] rounded-md hover:bg-[#F3F4F6]">+1s ⏩</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
