"""
Testes unitários para formatos múltiplos de legenda (.srt, .vtt, .sbv do YouTube) e exportação SRT.
"""

from core.srt_parser import parse_subtitles, export_to_srt

SAMPLE_VTT = """WEBVTT
Kind: captions
Language: pt

00:00:01.000 --> 00:00:03.500
Olá pessoal, bem-vindos ao tutorial.

00:00:04.200 --> 00:00:07.800 position:10% align:start
Neste momento vamos abrir o painel principal.

00:08.500 --> 00:12.000
Note que o tempo pode ser formatado em minutos e segundos.
"""

SAMPLE_YOUTUBE_SBV = """0:00:01.500,0:00:04.200
Primeira fala exportada do YouTube Studio.

0:00:05.100,0:00:09.000
Segunda fala explicativa do software.

0:00:10.000,0:00:14.500
Finalização e clique no botão salvar.
"""


def test_parse_vtt():
    items = parse_subtitles(SAMPLE_VTT)
    assert len(items) == 3
    assert items[0].start_seconds == 1.0
    assert items[0].end_seconds == 3.5
    assert items[0].text == "Olá pessoal, bem-vindos ao tutorial."

    assert items[1].start_seconds == 4.2
    assert items[1].end_seconds == 7.8
    assert "abrir o painel principal" in items[1].text

    assert items[2].start_seconds == 8.5
    assert items[2].end_seconds == 12.0


def test_parse_youtube_sbv():
    items = parse_subtitles(SAMPLE_YOUTUBE_SBV)
    assert len(items) == 3
    assert items[0].start_seconds == 1.5
    assert items[0].end_seconds == 4.2
    assert items[0].text == "Primeira fala exportada do YouTube Studio."

    assert items[1].start_seconds == 5.1
    assert items[1].end_seconds == 9.0

    assert items[2].start_seconds == 10.0
    assert items[2].end_seconds == 14.5


def test_export_to_srt():
    items = parse_subtitles(SAMPLE_YOUTUBE_SBV)
    srt_output = export_to_srt(items)

    assert "00:00:01,500 --> 00:00:04,200" in srt_output
    assert "Primeira fala exportada do YouTube Studio." in srt_output
    assert "00:00:10,000 --> 00:00:14,500" in srt_output

    # Valida que o SRT exportado pode ser relido pelo parser perfeitamente
    reloaded = parse_subtitles(srt_output)
    assert len(reloaded) == 3
    assert reloaded[0].text == items[0].text
    assert reloaded[0].start_seconds == items[0].start_seconds
