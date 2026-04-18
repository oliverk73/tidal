#!/usr/bin/env python3
"""Generate ODT listing remaining high-tidal-range countries not yet covered."""
from odf.opendocument import OpenDocumentText
from odf.style import (Style, TextProperties, ParagraphProperties,
                       TableColumnProperties, TableCellProperties)
from odf.text import H, P, Span, A, List, ListItem
from odf.table import Table, TableColumn, TableRow, TableCell

doc = OpenDocumentText()

st_h1 = Style(name='H1', family='paragraph')
st_h1.addElement(TextProperties(fontsize='18pt', fontweight='bold'))
doc.styles.addElement(st_h1)

st_h2 = Style(name='H2', family='paragraph')
st_h2.addElement(TextProperties(fontsize='14pt', fontweight='bold'))
doc.styles.addElement(st_h2)

st_body = Style(name='Body', family='paragraph')
st_body.addElement(TextProperties(fontsize='11pt'))
doc.styles.addElement(st_body)

st_bold = Style(name='Bold', family='text')
st_bold.addElement(TextProperties(fontweight='bold'))
doc.styles.addElement(st_bold)

st_italic = Style(name='Italic', family='text')
st_italic.addElement(TextProperties(fontstyle='italic'))
doc.styles.addElement(st_italic)

st_col_narrow = Style(name='ColNarrow', family='table-column')
st_col_narrow.addElement(TableColumnProperties(columnwidth='3.5cm'))
doc.automaticstyles.addElement(st_col_narrow)

st_col_mid = Style(name='ColMid', family='table-column')
st_col_mid.addElement(TableColumnProperties(columnwidth='4.0cm'))
doc.automaticstyles.addElement(st_col_mid)

st_col_wide = Style(name='ColWide', family='table-column')
st_col_wide.addElement(TableColumnProperties(columnwidth='6.5cm'))
doc.automaticstyles.addElement(st_col_wide)

st_cell = Style(name='Cell', family='table-cell')
st_cell.addElement(TableCellProperties(padding='0.1cm', border='0.5pt solid #000000'))
doc.automaticstyles.addElement(st_cell)

st_head_cell = Style(name='HeadCell', family='table-cell')
st_head_cell.addElement(TableCellProperties(padding='0.1cm', border='0.5pt solid #000000',
                                            backgroundcolor='#dddddd'))
doc.automaticstyles.addElement(st_head_cell)

st_head_para = Style(name='HeadPara', family='paragraph')
st_head_para.addElement(TextProperties(fontweight='bold'))
doc.styles.addElement(st_head_para)


def heading(level, text):
    style_map = {1: 'H1', 2: 'H2'}
    return H(outlinelevel=level, stylename=style_map[level], text=text)


def para(text, bold=False, italic=False):
    p = P(stylename='Body')
    if bold:
        p.addElement(Span(stylename='Bold', text=text))
    elif italic:
        p.addElement(Span(stylename='Italic', text=text))
    else:
        p.addText(text)
    return p


def mixed_para(parts):
    """parts: list of (text, style) where style in {None, 'Bold', 'Italic'}"""
    p = P(stylename='Body')
    for text, sty in parts:
        if sty:
            p.addElement(Span(stylename=sty, text=text))
        else:
            p.addText(text)
    return p


def head_cell(text):
    c = TableCell(stylename='Cell')
    c.addElement(P(stylename='HeadPara', text=text))
    return c


def cell(text):
    c = TableCell(stylename='Cell')
    c.addElement(P(stylename='Body', text=text))
    return c


doc.text.addElement(heading(1, 'Noch offene Länder mit bedeutendem Tidenhub'))
doc.text.addElement(para('Stand: 2026-04-18. Liste von Ländern/Regionen mit hohem Tidenhub, '
                         'für die bisher keine eigenen UTide-Harmonics erzeugt wurden.'))

doc.text.addElement(heading(2, 'Übersicht'))

rows = [
    ('China', 'bis 9 m',
     'Hangzhou-Bucht / Qiantang-Mündung (weltweit größter Tidenbore).',
     'Keine offene Quelle. China MSA veröffentlicht nur Tidenkalender als PDF mit '
     'Copyright-Sperre. Hongkong HKO deckt nur Nachbarschaft ab.'),
    ('Russland', 'bis 13 m',
     'Penzhina-Bucht / Ochotskisches Meer (zweithöchster Tidenhub der Welt); '
     'Weißes Meer (Mezen-Mündung bis 7 m).',
     'ESIMO/AARI-Daten formal öffentlich, praktisch aber schwer zugänglich '
     '(Registrierung, Russisch). Keine UHSLC-Stationen.'),
    ('Myanmar', 'bis 7 m',
     'Golf von Martaban, Yangon-Mündung.',
     'UHSLC hat Yangon (hourly). Machbar über bestehende Pipeline.'),
    ('Bangladesch', 'bis 6 m',
     'Meghna-Mündung / Ganges-Brahmaputra-Delta.',
     'UHSLC hat Chittagong und Cox\'s Bazar. Machbar.'),
    ('Pakistan', '2–3 m',
     'Indus-Delta, Karatschi.',
     'UHSLC hat Karachi. Tidenhub moderat, nicht prioritär.'),
    ('Französisch-Guayana / Suriname / Guyana', '3–5 m',
     'Amazonas-Schelf, Cayenne, Paramaribo.',
     'SHOM-Harmonics für Cayenne; UHSLC hat einzelne Stationen. Machbar.'),
    ('Madagaskar', 'bis 5 m',
     'Mosambik-Kanal Westküste, Mahajanga.',
     'UHSLC hat Nosy Be und Toamasina. Machbar.'),
    ('Mosambik', '3–5 m',
     'Beira, Maputo.',
     'UHSLC hat Inhambane, Maputo. Machbar.'),
    ('Papua-Neuguinea', '4–5 m',
     'Golf von Papua, Daru / Port Moresby.',
     'UHSLC hat Manus, Lombrum, Rabaul. Prüfen, ob Hochtide-Standorte dabei sind.'),
    ('Tansania / Kenia', '3–4 m',
     'Sansibar, Daressalam, Mombasa.',
     'UHSLC hat Zanzibar, Lamu. Machbar.'),
    ('Alaska (USA, separat)', 'bis 12 m',
     'Cook Inlet (Anchorage).',
     'NOAA-Stationen formal durch DWF abgedeckt, Qualität für Cook Inlet '
     'aber prüfen — extremer Tidenhub, häufige Nichtlinearitäten.'),
]

doc.text.addElement(para('Die Tabelle listet Länder, in denen der Tidenhub regional '
                         '3 m deutlich überschreitet und die bisher nicht oder nur am Rand '
                         'in unseren UTide-Harmonics auftauchen. Spalte „Datenlage" '
                         'bewertet, ob sich die bestehende Pipeline anwenden lässt.'))

tbl = Table()
tbl.addElement(TableColumn(stylename='ColMid'))
tbl.addElement(TableColumn(stylename='ColNarrow'))
tbl.addElement(TableColumn(stylename='ColWide'))
tbl.addElement(TableColumn(stylename='ColWide'))

hr = TableRow()
for h in ('Land / Region', 'Tidenhub', 'Hotspots', 'Datenlage'):
    c = TableCell(stylename='Cell')
    c.addElement(P(stylename='HeadPara', text=h))
    hr.addElement(c)
tbl.addElement(hr)

for country, rng, spots, data in rows:
    tr = TableRow()
    tr.addElement(cell(country))
    tr.addElement(cell(rng))
    tr.addElement(cell(spots))
    tr.addElement(cell(data))
    tbl.addElement(tr)

doc.text.addElement(tbl)

doc.text.addElement(heading(2, 'Empfohlene Reihenfolge'))
doc.text.addElement(para('Nach Datenverfügbarkeit × Tidenhub-Bedeutung:'))

doc.text.addElement(mixed_para([
    ('1. Myanmar + Bangladesch', 'Bold'),
    (' — UHSLC-Stationen vorhanden, 5–7 m Tidenhub, Lücke in Südasien. '
     'Direkt über bestehende Pipeline machbar.', None),
]))
doc.text.addElement(mixed_para([
    ('2. Madagaskar + Mosambik + Tansania', 'Bold'),
    (' — UHSLC hat mehrere Stationen im Mosambik-Kanal, ergänzt Südafrika-Abdeckung.', None),
]))
doc.text.addElement(mixed_para([
    ('3. Französisch-Guayana / Suriname / Guyana', 'Bold'),
    (' — SHOM + UHSLC, schließt die Lücke zwischen Karibik und Brasilien.', None),
]))
doc.text.addElement(mixed_para([
    ('4. Papua-Neuguinea', 'Bold'),
    (' — UHSLC-Bestand prüfen; ggf. nur Teilabdeckung.', None),
]))
doc.text.addElement(mixed_para([
    ('5. Cook Inlet / Alaska (Review)', 'Bold'),
    (' — keine neue Pipeline nötig, aber Qualität der DWF-Stationen dort prüfen '
     '(extreme Nichtlinearitäten bei 12 m Tidenhub).', None),
]))

doc.text.addElement(heading(2, 'Nicht machbar / ausgeschlossen'))
doc.text.addElement(mixed_para([
    ('China', 'Bold'),
    (' — keine offene, maschinenlesbare Quelle. China MSA Tidenkalender '
     'sind urheberrechtlich gesperrt, UHSLC hat keine chinesischen Stationen. '
     'Hongkong HKO ist bereits abgedeckt, deckt aber das Festland nicht ab.', None),
]))
doc.text.addElement(mixed_para([
    ('Russland (Ochotskisches Meer, Weißes Meer)', 'Bold'),
    (' — ESIMO/AARI formal öffentlich, praktisch aber nicht nutzbar: '
     'Registrierung erforderlich, Daten hinter russischsprachigem Portal, '
     'keine ERDDAP- oder offenes API-Angebot. Kein UHSLC-Bestand im Ochotskischen Meer.', None),
]))

out = '/home/oliver/harmonics/help/Offene_Tidenhub_Laender.odt'
doc.save(out)
print(f'Wrote {out}')
