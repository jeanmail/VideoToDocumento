"""
Testes unitários para o módulo core/srt_parser.py.
"""

from core.srt_parser import parse_srt, group_subtitles, time_to_seconds, SubtitleItem

SAMPLE_SRT = """1
00:00:01,500 --> 00:00:04,200
Olá, bem-vindo ao <i>treinamento</i> do sistema.

2
00:00:04,500 --> 00:00:07,800
Neste passo, vamos abrir o menu de configurações.

3
00:00:10,000 --> 00:00:13,000
Por fim, salve as alterações efetuadas.
"""

def test_time_to_seconds():
    assert time_to_seconds("00:00:01,500") == 1.5
    assert time_to_seconds("00:01:05,000") == 65.0
    assert time_to_seconds("01:00:00.000") == 3600.0

def test_parse_srt():
    items = parse_srt(SAMPLE_SRT)
    assert len(items) == 3

    assert items[0].index == 1
    assert items[0].start_seconds == 1.5
    assert items[0].end_seconds == 4.2
    assert "Olá, bem-vindo ao treinamento do sistema." == items[0].text
    assert items[0].start_time_str == "00:00:01"

    assert items[1].index == 2
    assert items[1].start_seconds == 4.5
    assert items[1].end_seconds == 7.8
    assert "Neste passo, vamos abrir o menu de configurações." == items[1].text

def test_group_subtitles():
    items = parse_srt(SAMPLE_SRT)
    # Entre item 1 (fim 4.2) e item 2 (inicio 4.5), gap é 0.3s -> devem ser agrupados
    # Entre item 2 (fim 7.8) e item 3 (inicio 10.0), gap é 2.2s -> não agrupa
    grouped = group_subtitles(items, max_gap_seconds=1.0)
    assert len(grouped) == 2
    assert "Olá, bem-vindo ao treinamento do sistema. Neste passo, vamos abrir o menu de configurações." == grouped[0].text
    assert grouped[0].start_seconds == 1.5
    assert grouped[0].end_seconds == 7.8
