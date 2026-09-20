"""
Módulo de OCR e enriquecimento textual de interfaces gráficas.
Oferece suporte modular e seguro contra falhas caso bibliotecas pesadas não estejam instaladas.
"""

import os
from typing import Optional, List


class OCREngine:
    def __init__(self, languages: Optional[List[str]] = None, enabled: bool = True):
        self.languages = languages or ['pt', 'en']
        self.enabled = enabled
        self._reader = None
        self._initialized = False

    def _init_reader(self):
        if not self.enabled or self._initialized:
            return
        
        try:
            import easyocr
            self._reader = easyocr.Reader(self.languages, gpu=False)
            self._initialized = True
        except ImportError:
            # EasyOCR não está instalado, manter reader nulo e seguir silenciosamente
            self._initialized = True
            self._reader = None
        except Exception:
            self._initialized = True
            self._reader = None

    def extract_text(self, image_path: str) -> str:
        """
        Executa OCR na imagem e retorna o texto detectado estruturado.
        Retorna string vazia caso o OCR esteja desativado ou indisponível.
        """
        if not self.enabled:
            return ""

        if not os.path.exists(image_path):
            return ""

        if not self._initialized:
            self._init_reader()

        if self._reader is None:
            return ""

        try:
            results = self._reader.readtext(image_path)
            # results é uma lista de tuplas (bbox, text, prob)
            detected_texts = [text.strip() for (_, text, prob) in results if prob >= 0.35 and text.strip()]
            return " | ".join(detected_texts)
        except Exception:
            return ""
