#!/usr/bin/env python3
"""Generate ODT report for worldwide currents-data research + South Africa plan."""
from odf.opendocument import OpenDocumentText
from odf.style import (Style, TextProperties, ParagraphProperties,
                       TableColumnProperties, TableCellProperties)
from odf.text import H, P, Span, A
from odf.table import Table, TableColumn, TableRow, TableCell

doc = OpenDocumentText()

# --- styles
st_h1 = Style(name='H1', family='paragraph')
st_h1.addElement(TextProperties(fontsize='18pt', fontweight='bold'))
doc.styles.addElement(st_h1)

st_h2 = Style(name='H2', family='paragraph')
st_h2.addElement(TextProperties(fontsize='14pt', fontweight='bold'))
doc.styles.addElement(st_h2)

st_h3 = Style(name='H3', family='paragraph')
st_h3.addElement(TextProperties(fontsize='12pt', fontweight='bold'))
doc.styles.addElement(st_h3)

st_p = Style(name='Body', family='paragraph')
st_p.addElement(TextProperties(fontsize='11pt'))
doc.styles.addElement(st_p)

st_bold = Style(name='Bold', family='text')
st_bold.addElement(TextProperties(fontweight='bold'))
doc.styles.addElement(st_bold)

st_link = Style(name='Link', family='text')
st_link.addElement(TextProperties(color='#0000ee', textunderlinestyle='solid',
                                  textunderlinewidth='auto', textunderlinecolor='font-color'))
doc.styles.addElement(st_link)

st_tbl = Style(name='Tbl', family='table')
doc.automaticstyles.addElement(st_tbl)

st_col = Style(name='Col', family='table-column')
st_col.addElement(TableColumnProperties(columnwidth='4.5cm'))
doc.automaticstyles.addElement(st_col)

st_col_wide = Style(name='ColWide', family='table-column')
st_col_wide.addElement(TableColumnProperties(columnwidth='9cm'))
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


def para(text, style='Body', bold=False):
    p = P(stylename=style)
    if bold:
        p.addElement(Span(stylename='Bold', text=text))
    else:
        p.addText(text)
    return p


def link_para(label, href, style='Body'):
    p = P(stylename=style)
    a = A(href=href, type='simple')
    a.addElement(Span(stylename='Link', text=label))
    p.addElement(a)
    return p


def heading(level, text):
    style_map = {1: 'H1', 2: 'H2', 3: 'H3'}
    h = H(outlinelevel=level, stylename=style_map[level])
    h.addText(text)
    return h


def cell(text, header=False):
    cs = 'HeadCell' if header else 'Cell'
    ps = 'HeadPara' if header else 'Body'
    c = TableCell(stylename=cs)
    c.addElement(para(text, style=ps))
    return c


def make_table(header, rows, col_widths=None):
    t = Table(stylename='Tbl')
    n = len(header)
    for i in range(n):
        sn = 'ColWide' if (col_widths and col_widths[i] == 'wide') else 'Col'
        t.addElement(TableColumn(stylename=sn))
    hr = TableRow()
    for h in header:
        hr.addElement(cell(h, header=True))
    t.addElement(hr)
    for row in rows:
        r = TableRow()
        for c in row:
            r.addElement(cell(c))
        t.addElement(r)
    return t


# === content ===
doc.text.addElement(heading(1, 'Strömungsdaten weltweit — Recherche & Pipeline-Ergebnis'))
doc.text.addElement(para('Stand: 2026-04-17. Ziel: UTide-Harmonics aus Messreihen oder '
                         'Tidenkalendern für Strömungsstationen außerhalb Europas und USA. '
                         'Bereits abgedeckt: DE, NL, BE, CMEMS (DK/FR/IE/NO/PT/ES/UK), '
                         'USA (NOAA), CA (CHS).'))

# Ergebnis der automatischen Sequenz
doc.text.addElement(heading(2, 'Ergebnis der automatischen Sequenz'))
doc.text.addElement(para('Auftrag: nach Australien automatisch Philippinen, Brasilien, '
                         'Südkorea, Chile, Japan (wenn kostenfrei), Südafrika prüfen.'))

rows = [
    ['Australien (IMOS ANMN)', 'FERTIG', '60 Stationen aus 63 NetCDFs (3 zu wenig Daten). '
     'Harmonics-Datei erzeugt. TCD noch nach /usr/share/xtide/ verschieben.'],
    ['Philippinen (NAMRIA)', 'SKIP', 'Tide- und Currents-Tables nur als gedrucktes Buch — '
     'kein digitaler Bulk-Download.'],
    ['Brasilien (DHN/CHM)', 'SKIP', 'Strömungsmesswerte nur per E-Mail-Anfrage erhältlich; '
     'SISCORAR-Stationen ohne offene Schnittstelle.'],
    ['Südkorea (KHOA)', 'SKIP', 'Nur 2 SEANOE-Stationen offen verfügbar; Rest der KOON-Daten '
     'login-pflichtig.'],
    ['Chile (SHOA)', 'SKIP', 'Publikation N°3015 "Tabla de Corrientes de Marea" '
     'kostenpflichtig (~12 EUR).'],
    ['Japan (JODC/JMA/JCG)', 'SKIP', 'JODC verbietet Redistribution; JMA nur Kartenbilder; '
     'JCG-Tidenstromseiten decken nur wenige Meerengen ab.'],
    ['Südafrika (SAEON)', 'GEPLANT', 'SAEON Data Portal frei verfügbar (Sentinel Sites, ASCA). '
     'Katalog-Crawl wird aktuell aufgebaut.'],
]
doc.text.addElement(make_table(
    ['Land / Quelle', 'Status', 'Kurzbefund'],
    rows,
    col_widths=[None, None, 'wide'],
))

# Australien - Details
doc.text.addElement(heading(2, 'Australien — IMOS ANMN (umgesetzt)'))
doc.text.addElement(para('Zugriff über öffentliches S3-Bucket imos-data, kein Login. '
                         'ThreadPool-Download, depth-averaged UTide-Analyse, '
                         '60 Stationen erzeugt. Dateien:'))
doc.text.addElement(para('• py/download_imos_currents_australia.py'))
doc.text.addElement(para('• py/convert_imos_currents.py'))
doc.text.addElement(para('• batch/batch_utide_eu_currents.py (country-agnostisch)'))
doc.text.addElement(para('• harmonics/utide/harmonics_utide_australia_imos_currents.txt'))

doc.text.addElement(heading(3, 'Quellen Australien'))
doc.text.addElement(link_para('IMOS AODN Portal', 'https://portal.aodn.org.au/'))
doc.text.addElement(link_para('IMOS OceanCurrent Tidal Predictions',
                              'https://oceancurrent.aodn.org.au/tides/index.htm'))
doc.text.addElement(link_para('BOM National Tidal Centre',
                              'https://www.bom.gov.au/oceanography/projects/ntc/ntc.shtml'))
doc.text.addElement(link_para('S3 Bucket imos-data',
                              'https://s3-ap-southeast-2.amazonaws.com/imos-data'))

# Geprüfte Länder Details
doc.text.addElement(heading(2, 'Geprüfte Länder — Begründung für Skip'))

doc.text.addElement(heading(3, 'Philippinen — NAMRIA'))
doc.text.addElement(para('Jährliche Publikation "Tide and Current Tables" mit 37 Straits, '
                         'nur Print / Hardcopy. Keine offene PDF-Quelle gefunden.'))
doc.text.addElement(link_para('NAMRIA', 'https://www.namria.gov.ph/'))

doc.text.addElement(heading(3, 'Brasilien — DHN / CHM (Marinha do Brasil)'))
doc.text.addElement(para('SISCORAR: Vorhersagesystem für 5 Hafenbereiche (Guanabara, '
                         'Sepetiba, Santos, Paranaguá, Todos os Santos). Messreihen nur '
                         'per E-Mail auf Antrag.'))
doc.text.addElement(link_para('CHM SISCORAR',
                              'https://www.marinha.mil.br/chm/dados-do-smm/corrente-de-mare'))
doc.text.addElement(link_para('PAM — Previsão Ambiental Marinha',
                              'https://pam.dhn.mar.mil.br/'))

doc.text.addElement(heading(3, 'Südkorea — KHOA KOON'))
doc.text.addElement(para('264 Strömungsstationen (1999–2011) mit 10-min-Intervallen. '
                         'Rohdaten hinter KHOA-OceanGrid-Login; nur zwei Stationen via '
                         'SEANOE öffentlich.'))
doc.text.addElement(link_para('KHOA KOON Overview',
                              'https://www.khoa.go.kr/eng/kcom/cnt/selectContentsPage.do?cntId=21020100'))
doc.text.addElement(link_para('KHOA OceanGrid KOOFS',
                              'http://www.khoa.go.kr/oceangrid/koofs/eng/introduce/network.do'))

doc.text.addElement(heading(3, 'Chile — SHOA'))
doc.text.addElement(para('Pub. N°3015 "Tabla de Corrientes de Marea de la Costa de Chile" — '
                         'kostenpflichtig (~12 EUR pro Ausgabe).'))
doc.text.addElement(link_para('SHOA', 'https://www.shoa.cl/'))

doc.text.addElement(heading(3, 'Japan — JODC / JMA / JCG'))
doc.text.addElement(para('JODC J-DOSS: umfangreiches Ship-Drift/ADCP-Archiv, '
                         'Redistribution jedoch untersagt; für stationäre Mooring-UTide '
                         'wenig brauchbar. JMA veröffentlicht nur Kartenbilder. JCG-Tidal-'
                         'Current-Tables decken nur einige Meerengen ab, Harmonics nur im '
                         'kostenpflichtigen Buch Pub. Nr. 742 vertrieben.'))
doc.text.addElement(link_para('JODC J-DOSS Ocean Current',
                              'https://www.jodc.go.jp/jodcweb/JDOSS/infoTide.html'))
doc.text.addElement(link_para('JCG Tidal Current Tables (Eastern Japan)',
                              'https://www1.kaiho.mlit.go.jp/KAN7/tide/tide_ryu_e.html'))
doc.text.addElement(link_para('Japan Hydrographic Association Pub. 742',
                              'https://www.jha.or.jp/en/jha/business/b07.html'))

# Südafrika
doc.text.addElement(heading(2, 'Südafrika — SAEON (aktueller Pipeline-Aufbau)'))
doc.text.addElement(para('Entscheidung: Pipeline nur auf SAEON (Sentinel Sites + ASCA) '
                         'aufbauen. NOAA NCEI/AOML und CMEMS INSITU_GLO werden nicht '
                         'verfolgt (Forschungsarrays auf offener See, weniger relevant '
                         'für Küstenvorhersagen). SAN HO (Crown-Copyright) '
                         'bleibt ausgeschlossen.'))

doc.text.addElement(heading(3, 'Quellenstatus Südafrika'))
rows_sa = [
    ['SAEON Data Portal', 'FREI (DOIs)', 'NetCDF / OPeNDAP',
     'Sentinel Sites, ASCA, ACEP'],
    ['SAEON Egagasini Ocean Portal', 'frei', 'Web-Portal',
     'South Coast Moorings'],
    ['NOAA NCEI Acc. 0140939', 'frei', 'NetCDF pro Instrument',
     'Agulhas Array Apr 2010 – Feb 2013'],
    ['NOAA AOML SAMBA 34.5°S', 'frei', 'ASCII',
     '9 PIES/CPIES, seit 2009-10, laufend'],
    ['SEANOE SAMBA East raw', 'frei', 'NetCDF / ASCII',
     '34.5°S Ostteil'],
    ['CMEMS INSITU_GLO MO/AD', 'frei (Login)', 'NetCDF',
     'ZA-Abdeckung sehr dünn — nur Lückenfüller'],
    ['SAN Hydrographic Office', 'restriktiv', 'Print / PDF (Crown-Copyright)',
     'Tide Tables + Currents Atlas, keine API'],
    ['SAWS', 'n/a', '—', 'Keine Strömungsstationen'],
]
doc.text.addElement(make_table(
    ['Quelle', 'Zugang', 'Format', 'Abdeckung'],
    rows_sa,
    col_widths=[None, None, None, 'wide'],
))

doc.text.addElement(heading(3, 'URLs Südafrika'))
doc.text.addElement(link_para('SAEON Catalogue', 'https://catalogue.saeon.ac.za/'))
doc.text.addElement(link_para('SAEON uLwazi Open Data Platform',
                              'https://ulwazi.saeon.ac.za/projects/open-data-platform/'))
doc.text.addElement(link_para('SAEON Egagasini Ocean Portal',
                              'https://egagasini.saeon.ac.za/ocean-portal/'))
doc.text.addElement(link_para('NOAA NCEI Agulhas Array (Acc. 0140939)',
                              'https://catalog.data.gov/dataset/'
                              'in-situ-water-current-velocity-measurements-collected-from-'
                              'moored-current-meters-in-the-agulhas3'))
doc.text.addElement(link_para('NOAA AOML SAMOC Data',
                              'https://www.aoml.noaa.gov/phod/SAMOC_international/samoc_data.php'))
doc.text.addElement(link_para('NOAA AOML SAM Data Access',
                              'https://www.aoml.noaa.gov/phod/research/moc/samoc/sam/data_access.php'))
doc.text.addElement(link_para('SEANOE SAMBA East raw',
                              'https://www.seanoe.org/data/00592/70364/'))
doc.text.addElement(link_para('OceanSITES SAMBA Timeseries',
                              'http://www.oceansites.org/tma/samba.html'))
doc.text.addElement(link_para('CMEMS INSITU ERDDAP',
                              'https://nrt.cmems-du.eu/erddap/tabledap/'
                              'copernicus_GLO_insitu_nrt_MO.subset'))
doc.text.addElement(link_para('SAN Hydrographic Office', 'https://www.sanho.co.za/'))

doc.text.addElement(heading(3, 'SAN HO Kontaktdaten (nicht verfolgt)'))
doc.text.addElement(para('E-Mail: hydrosan@iafrica.com · Tel.: +27 (0)21 787 2403 · '
                         'Fax: +27 (0)21 787 2233 · Adresse: SAN Hydrographic Office, '
                         'Silvermine, Tokai, Cape Town. Lizenz Crown-Copyright-artig '
                         '(restriktiv).'))

# Ausblick
doc.text.addElement(heading(2, 'Nächste Schritte'))
doc.text.addElement(para('1. SAEON-Katalog-Crawl abschließen — Record-IDs, DOIs und '
                         'OPeNDAP-URLs für ASCA und Sentinel Sites sammeln.'))
doc.text.addElement(para('2. Downloader analog py/download_imos_currents_australia.py '
                         'anlegen.'))
doc.text.addElement(para('3. Konverter und batch_utide_eu_currents.py-Lauf für Südafrika — '
                         'ergibt harmonics_utide_south_africa_currents.txt.'))
doc.text.addElement(para('4. TCD erzeugen, Marker-Skript ergänzen, AU-TCD nach '
                         '/usr/share/xtide/ übernehmen.'))

out = '/home/oliver/Recherche_Stroemungsdaten_Welt.odt'
doc.save(out)
print(f'wrote {out}')
