#!/usr/bin/env python3
"""
Parse Brazilian DHN (Marinha do Brasil) tide table PDFs and create UTide harmonics.

Strategy:
1. Extract all HW/LW times+heights from PDFs (2024-2026, 3 years)
2. Interpolate to hourly time series using half-cosine segments
3. Run UTide harmonic analysis
4. Output in XTide harmonics format (175 constituents)

Supports 55 DHN stations. Image-based PDFs (DHN 27/28 for 2024) use OCR fallback.
"""

import re
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import fitz  # PyMuPDF
import utide

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

sys.path.insert(0, '/home/oliver/py')
from generate_brazil_harmonics import CONSTITUENTS_175, find_xtide_match

# ============================================================
# Station definitions — all 55 DHN stations
# ============================================================
BASE = '/home/oliver/annual_predictions/brazil/'

STATIONS = [
    # DHN 1
    {
        'dhn': 1,
        'name': 'Barra Norte - Arco Lamoso, Amapá, Brazil',
        'lat': 1.4383, 'lon': -49.2117,
        'state': 'Amapa', 'utc_offset': 3,
        'pdfs': {
            2024: 'barra_norte_arco_lamoso_2024.pdf',
            2025: '1_-_barra_norte_-_arco_lamoso_11-13.pdf',
            2026: '1 -BARRA NORTE - ARCO LAMOSO - 2026 - 13 - 15.pdf',
        },
    },
    # DHN 2
    {
        'dhn': 2,
        'name': 'Igarapé Grande do Curua, Amapá, Brazil',
        'lat': 0.7633, 'lon': -50.1183,
        'state': 'Amapa', 'utc_offset': 3,
        'pdfs': {
            2024: '02_-_igarape_grande_do_curui_2024_ok.pdf',
            2025: '2_-_igarape_grande_do_curua_14-16.pdf',
            2026: '2 -IGARAP\u00c9 GRANDE DO CURU\u00c1 - 2026 - 16 - 18.pdf',
        },
    },
    # DHN 3
    {
        'dhn': 3,
        'name': 'Porto de Santana, Amapá, Brazil',
        'lat': -0.067, 'lon': -51.167,
        'state': 'Amapa', 'utc_offset': 3,
        'pdfs': {
            2024: '03_-_porto_de_santana_2024_ok.pdf',
            2025: '1 - PORTO DE SANTANA - CIA DOCAS DE SANTANA (ESTADO DO AMAP\u00c1) - 2025 - P\u00e1ginas 17 a 19.pdf',
            2026: '3 - PORTO DE SANTANA - 19 - 21.pdf',
        },
    },
    # DHN 4
    {
        'dhn': 4,
        'name': 'Salinópolis, Pará, Brazil',
        'lat': -0.6167, 'lon': -47.35,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '04_-_salinopolis_2024_ok.pdf',
            2025: '5 - FUNDEADOURO DE SALIN\u00d3POLIS - PA 23 -25 2025.pdf',
            2026: '5 -FUNDEADOURO DE SALIN\u00d3POLIS 25 - 27.pdf',
        },
    },
    # DHN 5
    {
        'dhn': 5,
        'name': 'Ilha dos Guarás, Pará, Brazil',
        'lat': -0.59766, 'lon': -47.91556,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '05_-_ilha_dos_guaras_2024_ok.pdf',
            2025: '4 - ILHA DOS GUAR\u00c1S - PA 20-22 2025.pdf',
            2026: '4 - ILHA DOS GUAR\u00c1S (ESTADO DO PAR\u00c1) - 2026 22 - 24.pdf',
        },
    },
    # DHN 6
    {
        'dhn': 6,
        'name': 'Ilha do Mosqueiro, Pará, Brazil',
        'lat': -1.165, 'lon': -48.4733,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '06_-_ilha_do_mosqueiro_2024_ok.pdf',
            2025: '6 - ILHA DO MOSQUEIRO 26 - 28 2025.pdf',
            2026: '6 - ILHA DO MOSQUEIRO 28 - 30.pdf',
        },
    },
    # DHN 7
    {
        'dhn': 7,
        'name': 'Belem, Pará, Brazil',
        'lat': -1.4362, 'lon': -48.4941,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '07_-_porto_de_belem_2024_ok.pdf',
            2025: '7 - PORTO DE BEL\u00c9M - PA 29-31 2025.pdf',
            2026: '7 - PORTO DE BEL\u00c9M (ESTADO DO PAR\u00c1) - 2026 - 31 - 33.pdf',
        },
    },
    # DHN 8
    {
        'dhn': 8,
        'name': 'Vila do Conde, Pará, Brazil',
        'lat': -1.5383, 'lon': -48.7533,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '08_-_porto_de_vila_do_conde_2024_ok.pdf',
            2025: '8 - PORTO DE VILA DO CONDE - PA 32-34 2025.pdf',
            2026: '8 - PORTO DE VILA DO CONDE 34 - 36.pdf',
        },
    },
    # DHN 9
    {
        'dhn': 9,
        'name': 'Breves, Pará, Brazil',
        'lat': -1.6917, 'lon': -50.4833,
        'state': 'Para', 'utc_offset': 3,
        'pdfs': {
            2024: '09_-_atracadouro_de_breves_2024_ok.pdf',
            2025: '9 - ATRACADOURO DE BREVES - PA 35-37 2025.pdf',
            2026: '9 - ATRACADOURO DE BREVES 37 - 39.pdf',
        },
    },
    # DHN 10
    {
        'dhn': 10,
        'name': 'Sao Luis, Maranhão, Brazil',
        'lat': -2.5288, 'lon': -44.3081,
        'state': 'Maranhao', 'utc_offset': 3,
        'pdfs': {
            2024: '10_-_sao_luis_2024_ok.pdf',
            2025: '11_-_sao_luis_-ma_41-43.pdf',
            2026: '10 - S\u00c3O LU\u00cdS 40 - 42.pdf',
        },
    },
    # DHN 11
    {
        'dhn': 11,
        'name': 'Terminal da Ponta da Madeira, Maranhão, Brazil',
        'lat': -2.565, 'lon': -44.3783,
        'state': 'Maranhao', 'utc_offset': 3,
        'pdfs': {
            2024: '11_-_term_ponta_da_madeira_2024_ok.pdf',
            2025: '13_-_terminal_da_ponta_da_madeira_-_ma_47-49.pdf',
            2026: '11 - TERMINAL DA PONTA DA MADEIRA 43 - 45.pdf',
        },
    },
    # DHN 12
    {
        'dhn': 12,
        'name': 'Porto de Itaqui, Maranhão, Brazil',
        'lat': -2.5767, 'lon': -44.37,
        'state': 'Maranhao', 'utc_offset': 3,
        'pdfs': {
            2024: '12_-_porto_de_itaqui_2024_ok.pdf',
            2025: '14_-_porto_de_itaqui_-_ma_50-52.pdf',
            2026: '12 - PORTO DE ITAQUI - 46 - 48.pdf',
        },
    },
    # DHN 13
    {
        'dhn': 13,
        'name': 'Terminal da Alumar, Maranhão, Brazil',
        'lat': -2.6783, 'lon': -44.3633,
        'state': 'Maranhao', 'utc_offset': 3,
        'pdfs': {
            2024: '13_-_term_da_alumar_2024_ok.pdf',
            2025: '12_-_terminal_da_alumar_-_ma_44-46.pdf',
            2026: '13 - TERMINAL DA ALUMAR - 49 - 51.pdf',
        },
    },
    # DHN 14
    {
        'dhn': 14,
        'name': 'Tutóia, Maranhão, Brazil',
        'lat': -2.765, 'lon': -42.275,
        'state': 'Maranhao', 'utc_offset': 3,
        'pdfs': {
            2024: '14_-_porto_de_tutoia_2024_ok.pdf',
            2025: 'PORTO DE TUT\u00d3IA - 2025.pdf',
            2026: '14 - PORTO DE TUT\u00d3IA - 52 - 54.pdf',
        },
    },
    # DHN 15
    {
        'dhn': 15,
        'name': 'Luís Correia, Piauí, Brazil',
        'lat': -2.8533, 'lon': -41.6433,
        'state': 'Piaui', 'utc_offset': 3,
        'pdfs': {
            2024: '15_-_porto_de_luis_correia_2024_ok.pdf',
            2025: '15 - PORTO DE LU\u00cdS CORREIA -PI 53-55.pdf',
            2026: '15 - PORTO DE LU\u00cdS CORREIA 55 - 57.pdf',
        },
    },
    # DHN 16
    {
        'dhn': 16,
        'name': 'Terminal Portuário do Pecém, Ceará, Brazil',
        'lat': -3.535, 'lon': -38.7983,
        'state': 'Ceara', 'utc_offset': 3,
        'pdfs': {
            2024: 'pecem_2024.pdf',
            2025: '16_-_terminal_portuario_do_pecem_-_ce_56-58.pdf',
            2026: '16 - TERMINAL PORTU\u00c1RIO DO PEC\u00c9M 58 - 60.pdf',
        },
    },
    # DHN 17
    {
        'dhn': 17,
        'name': 'Mucuripe (Porto), Ceará, Brazil',
        'lat': -3.7152, 'lon': -38.4774,
        'state': 'Ceara', 'utc_offset': 3,
        'pdfs': {
            2024: 'mucuripe_2024.pdf',
            2025: '3 PORTO DE MUCURIPE - FORTALEZA (ESTADO DO CEAR\u00c1) - 2025 - P\u00e1ginas 59 a 61.pdf',
            2026: '17 - PORTO DE MUCURIPE - FORTALEZA 61 - 63.pdf',
        },
    },
    # DHN 18
    {
        'dhn': 18,
        'name': 'Areia Branca (Terminal Salineiro), Rio Grande do Norte, Brazil',
        'lat': -4.8224, 'lon': -37.0436,
        'state': 'Rio Grande do Norte', 'utc_offset': 3,
        'pdfs': {
            2024: '18_-_areia_branca_2024_ok.pdf',
            2025: '19_-_porto_de_areia_branca_-_termisa_-_rn_65-67.pdf',
            2026: '19 - PORTO DE AREIA BRANCA - TERMISA - 67 - 69.pdf',
        },
    },
    # DHN 20
    {
        'dhn': 20,
        'name': 'Macau, Rio Grande do Norte, Brazil',
        'lat': -5.1005, 'lon': -36.6734,
        'state': 'Rio Grande do Norte', 'utc_offset': 3,
        'pdfs': {
            2024: '20_-_porto_de_macau_2024_ok.pdf',
            2025: '20 - PORTO DE MACAU - RN - 68-70.pdf',
            2026: '20 - PORTO DE MACAU - 70 - 72.pdf',
        },
    },
    # DHN 21
    {
        'dhn': 21,
        'name': 'Guamaré, Rio Grande do Norte, Brazil',
        'lat': -5.1061, 'lon': -36.3171,
        'state': 'Rio Grande do Norte', 'utc_offset': 3,
        'pdfs': {
            2024: '19_-_guamare_2024_ok.pdf',
            2025: '21 - PORTO DE GUAMAR\u00c9 - RN - 71-73.pdf',
            2026: '21 - PORTO DE GUAMAR\u00c9- 73 - 75.pdf',
        },
    },
    # DHN 22
    {
        'dhn': 22,
        'name': 'Natal, Rio Grande do Norte, Brazil',
        'lat': -5.7755, 'lon': -35.2066,
        'state': 'Rio Grande do Norte', 'utc_offset': 3,
        'pdfs': {
            2024: '22_-_porto_de_natal_2024_ok.pdf',
            2025: '22_-_porto_de_natal_-_capitania_dos_portos_do_rn_-_74-76.pdf',
            2026: '22 - PORTO DE NATAL - COM3DN - 76 -78.pdf',
        },
    },
    # DHN 23
    {
        'dhn': 23,
        'name': 'Cabedelo (Porto), Paraíba, Brazil',
        'lat': -6.9702, 'lon': -34.8407,
        'state': 'Paraiba', 'utc_offset': 3,
        'pdfs': {
            2024: '23_-_porto_de_cabedelo_2024_ok.pdf',
            2025: '23_-_porto_de_cabedelo_-_pb_-_77-79.pdf',
            2026: '23 - PORTO DE CABEDELO - 79 - 81.pdf',
        },
    },
    # DHN 24
    {
        'dhn': 24,
        'name': 'Fernando de Noronha, Pernambuco, Brazil',
        'lat': -3.828, 'lon': -32.403,
        'state': 'Pernambuco', 'utc_offset': 2,
        'pdfs': {
            2024: '21_-_fernando_de_noronha_2024_ok.pdf',
            2025: '18_-_arquipelago_de_fernando_de_noronha_-bs_62-64.pdf',
            2026: '18 - ARQUIP\u00c9LAGO DE FERNANDO DE NORONHA 64 - 66.pdf',
        },
    },
    # DHN 19 (Porto do Recife \u2014 geographisch zwischen Cabedelo und Suape)
    {
        'dhn': 19,
        'name': 'Recife (Porto), Pernambuco, Brazil',
        'lat': -8.0567, 'lon': -34.8667,
        'state': 'Pernambuco', 'utc_offset': 3,
        'pdfs': {
            2024: '24_-_porto_do_recife_2024_ok.pdf',
            2025: '24 - PORTO DO RECIFE -PE - 80-82.pdf',
            2026: '24 - PORTO DO RECIFE - 82 - 84.pdf',
        },
    },
    # DHN 25
    {
        'dhn': 25,
        'name': 'Porto de Suape, Pernambuco, Brazil',
        'lat': -8.3989, 'lon': -34.9596,
        'state': 'Pernambuco', 'utc_offset': 3,
        'pdfs': {
            2024: '25_-_porto_de_suape_2024_ok.pdf',
            2025: '25 - PORTO DE SUAPE -PE - 83-85.pdf',
            2026: '25 - PORTO DE SUAPE - 85 -87.pdf',
        },
    },
    # DHN 26
    {
        'dhn': 26,
        'name': 'Maceió (Porto), Alagoas, Brazil',
        'lat': -9.6833, 'lon': -35.725,
        'state': 'Alagoas', 'utc_offset': 3,
        'pdfs': {
            2024: '26_-_porto_de_maceio_2024_ok.pdf',
            2025: '26_-_porto_de_maceio_-_al_-_86-88.pdf',
            2026: '26 - PORTO DE MACEI\u00d3 - 88 -90.pdf',
        },
    },
    # DHN 27 — 2024 PDF is image-based, needs OCR
    {
        'dhn': 27,
        'name': 'Terminal Maritimo Inacio Barbosa, Sergipe, Brazil',
        'lat': -10.8433, 'lon': -36.9183,
        'state': 'Sergipe', 'utc_offset': 3,
        'pdfs': {
            2024: 'terminal_maritimo_inacio_barbosa_-_2024_ok.pdf',
            2025: '27 - TERMINAL MAR\u00cdTIMO IN\u00c1CIO BARBOSA - SE - 89-91.pdf',
            2026: '27 - TERMINAL MAR\u00cdTIMO IN\u00c1CIO BARBOSA - 91 - 93.pdf',
        },
    },
    # DHN 28 — 2024 PDF is image-based, needs OCR
    {
        'dhn': 28,
        'name': 'Aracaju (Capitania dos Portos), Sergipe, Brazil',
        'lat': -10.9204, 'lon': -37.0457,
        'state': 'Sergipe', 'utc_offset': 3,
        'pdfs': {
            2024: 'capitania_dos_portos_de_sergipe_-_2024_ok.pdf',
            2025: '28 - CAPITANIA DOS PORTOS DE SERGIPE - SE - 92-94.pdf',
            2026: '28 - CAPITANIA DOS PORTOS DE SERGIPE - 94 - 96.pdf',
        },
    },
    # DHN 29
    {
        'dhn': 29,
        'name': 'Madre de Deus, Bahia, Brazil',
        'lat': -12.75, 'lon': -38.6237,
        'state': 'Bahia', 'utc_offset': 3,
        'pdfs': {
            2024: '29_-_madre_de_deus_2024_ok.pdf',
            2025: '29_-_porto_de_madre_de_deus_-_ba_-_95-97.pdf',
            2026: '29 - PORTO DE MADRE DE DEUS - 97 - 99.pdf',
        },
    },
    # DHN 30
    {
        'dhn': 30,
        'name': 'Aratu (Base Naval), Bahia, Brazil',
        'lat': -12.7944, 'lon': -38.4943,
        'state': 'Bahia', 'utc_offset': 3,
        'pdfs': {
            2024: '30_-_porto_de_aratu_2024_ok.pdf',
            2025: '30_-_porto_de_aratu_-_base_naval_-_ba_-_98-100.pdf',
            2026: '30 - PORTO DE ARATU - BASE NAVAL 100 - 102.pdf',
        },
    },
    # DHN 31
    {
        'dhn': 31,
        'name': 'Salvador (Porto), Bahia, Brazil',
        'lat': -12.974, 'lon': -38.5173,
        'state': 'Bahia', 'utc_offset': 3,
        'pdfs': {
            2024: '31_-_porto_de_salvador_2024_ok.pdf',
            2025: '31 - PORTO DE SALVADOR - BA - 101-103.pdf',
            2026: '31 - PORTO DE SALVADOR - 103 - 105.pdf',
        },
    },
    # DHN 32
    {
        'dhn': 32,
        'name': 'Ilhéus (Porto), Bahia, Brazil',
        'lat': -14.78, 'lon': -39.0267,
        'state': 'Bahia', 'utc_offset': 3,
        'pdfs': {
            2024: '32_-_porto_de_ilheus_2024_ok.pdf',
            2025: '32 - PORTO DE ILH\u00c9US - MALHADO - BA - 104-106.pdf',
            2026: '32 - PORTO DE ILH\u00c9US - MALHADO - 106 - 108.pdf',
        },
    },
    # DHN 33
    {
        'dhn': 33,
        'name': 'Barra do Riacho, Espírito Santo, Brazil',
        'lat': -19.8382, 'lon': -40.0597,
        'state': 'Espirito Santo', 'utc_offset': 3,
        'pdfs': {
            2024: '33_-_barra_do_riacho_2024_ok.pdf',
            2025: '33 - TERMINAL DE BARRA DO RIACHO - ES - 107-109.pdf',
            2026: '33 - TERMINAL DE BARRA DO RIACHO - 109 - 111.pdf',
        },
    },
    # DHN 34
    {
        'dhn': 34,
        'name': 'Tubarão (Porto), Espírito Santo, Brazil',
        'lat': -20.289, 'lon': -40.2438,
        'state': 'Espirito Santo', 'utc_offset': 3,
        'pdfs': {
            2024: '35_-_porto_de_tubarao_2024_ok.pdf',
            2025: '34 - PORTO DE TUBAR\u00c3O - ES - 110-112.pdf',
            2026: '34 - PORTO DE TUBAR\u00c3O - 112 - 114.pdf',
        },
    },
    # DHN 35
    {
        'dhn': 35,
        'name': 'Vitória (Porto), Espírito Santo, Brazil',
        'lat': -20.3224, 'lon': -40.3367,
        'state': 'Espirito Santo', 'utc_offset': 3,
        'pdfs': {
            2024: '34_-_porto_de_vitoria_2024_ok.pdf',
            2025: '35 - PORTO DE VIT\u00d3RIA 113 - 115.pdf',
            2026: '35 - PORTO DE VIT\u00d3RIA - 115 - 117.pdf',
        },
    },
    # DHN 36 — UTC-2 (Trindade)
    {
        'dhn': 36,
        'name': 'Ilha da Trindade, Espírito Santo, Brazil',
        'lat': -20.5083, 'lon': -29.31,
        'state': 'Espirito Santo', 'utc_offset': 2,
        'pdfs': {
            2024: '37_-_ilha_da_trindade_2024_ok.pdf',
            2025: '36 - ILHA DA TRINDADE - 116-118.pdf',
            2026: '36 - ILHA DA TRINDADE - 118 - 120.pdf',
        },
    },
    # DHN 37
    {
        'dhn': 37,
        'name': 'Ponta do Ubú, Espírito Santo, Brazil',
        'lat': -20.7883, 'lon': -40.57,
        'state': 'Espirito Santo', 'utc_offset': 3,
        'pdfs': {
            2024: '36_-_ponta_do_ubu_2024_ok.pdf',
            2025: '37 - TERMINAL DA PONTA DO UBU - ES - 119-121.pdf',
            2026: '37 - TERMINAL DA PONTA DO UBU - 121 - 123.pdf',
        },
    },
    # DHN 38
    {
        'dhn': 38,
        'name': 'Porto do Açu, Rio de Janeiro, Brazil',
        'lat': -21.8133, 'lon': -40.9983,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '38_-_porto_do_acu_2024_ok.pdf',
            2025: '38 - PORTO DO A\u00c7U - RJ - 122-124.pdf',
            2026: '38 - PORTO DO A\u00c7U - 124 - 126.pdf',
        },
    },
    # DHN 39
    {
        'dhn': 39,
        'name': 'Macaé, Rio de Janeiro, Brazil',
        'lat': -22.3853, 'lon': -41.7695,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '39_-_imbetiba_2024_ok.pdf',
            2025: '39 - TERMINAL MAR\u00cdTIMO DE IMBETIBA - RJ - 125-127.pdf',
            2026: '39 - TERMINAL MAR\u00cdTIMO DE IMBETIBA - 127 - 129.pdf',
        },
    },
    # DHN 40
    {
        'dhn': 40,
        'name': 'Arraial do Cabo (Porto do Forno), Rio de Janeiro, Brazil',
        'lat': -22.9725, 'lon': -42.0136,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '40_-_porto_do_forno_2024_ok.pdf',
            2025: '42 - PORTO DO FORNO - RJ - 134-136 2025.pdf',
            2026: '42 - PORTO DO FORNO - 136 - 138.pdf',
        },
    },
    # DHN 41
    {
        'dhn': 41,
        'name': 'Angra dos Reis, Rio de Janeiro, Brazil',
        'lat': -23.0133, 'lon': -44.315,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '44_-_porto_de_angra_2024_ok.pdf',
            2025: '44 - PORTO DE ANGRA DOS REIS - RJ - 140-142.pdf',
            2026: '44 - PORTO DE ANGRA DOS REIS - 142 -144.pdf',
        },
    },
    # DHN 42
    {
        'dhn': 42,
        'name': 'Ilha Fiscal, Rio de Janeiro, Brazil',
        'lat': -22.8967, 'lon': -43.1667,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '41_-_porto_do_rio_de_janeiro_2024_ok.pdf',
            2025: '4 - PORTO DO RIO DE JANEIRO - ILHA FISCAL (ESTADO DO RIO DE JANEIRO) - 2025 - P\u00e1ginas 129 a 131.pdf',
            2026: '40 - PORTO DO RIO DE JANEIRO - I FISCAL - 130 - 132.pdf',
        },
    },
    # DHN 43
    {
        'dhn': 43,
        'name': 'Itaguaí, Rio de Janeiro, Brazil',
        'lat': -22.9317, 'lon': -43.8417,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '42_-_porto_de_itaguai_2024_ok.pdf',
            2025: '41 - PORTO DE ITAGU\u00c1I - RJ - 131-133.pdf',
            2026: '41 - PORTO DE ITAGU\u00c1I - 133 - 135.pdf',
        },
    },
    # DHN 44
    {
        'dhn': 44,
        'name': 'Ilha Guaiba, Rio de Janeiro, Brazil',
        'lat': -23.0, 'lon': -44.0317,
        'state': 'Rio de Janeiro', 'utc_offset': 3,
        'pdfs': {
            2024: '43_-_term_da_ilha_guaiba_2024_ok.pdf',
            2025: '5 - TERMINAL DA ILHA GUA\u00cdBA (ESTADO DO RIO DE JANEIRO) - 2025 - P\u00e1ginas 137 a 139.pdf',
            2026: '43 - TERMINAL DA ILHA GUA\u00cdBA - 139 - 141.pdf',
        },
    },
    # DHN 45
    {
        'dhn': 45,
        'name': 'São Sebastião, São Paulo, Brazil',
        'lat': -23.81, 'lon': -45.3983,
        'state': 'Sao Paulo', 'utc_offset': 3,
        'pdfs': {
            2024: '45_-_porto_de_sao_sebastiao_2024_ok.pdf',
            2025: '45 - PORTO DE S\u00c3O SEBASTI\u00c3O - 143-145.pdf',
            2026: '45 - PORTO DE S\u00c3O SEBASTI\u00c3O - 145 - 147.pdf',
        },
    },
    # DHN 46
    {
        'dhn': 46,
        'name': 'Santos, São Paulo, Brazil',
        'lat': -23.9567, 'lon': -46.3083,
        'state': 'Sao Paulo', 'utc_offset': 3,
        'pdfs': {
            2024: '46_-_porto_de_santos_2024_ok.pdf',
            2025: '46 - PORTO DE SANTOS - 146-148.pdf',
            2026: '46 - PORTO DE SANTOS - 148 - 150.pdf',
        },
    },
    # DHN 47
    {
        'dhn': 47,
        'name': 'Ponta do Félix, Paraná, Brazil',
        'lat': -25.0967, 'lon': -48.4067,
        'state': 'Parana', 'utc_offset': 3,
        'pdfs': {
            2024: '50_-_ponta_do_felix_2024_ok.pdf',
            2025: '47 - TERMINAL DA PONTA DO FELIX - 149-151.pdf',
            2026: '47 - TERMINAL PORTU\u00c1RIO DA PONTA DO F\u00c9LIX 151 - 153.pdf',
        },
    },
    # DHN 48
    {
        'dhn': 48,
        'name': 'Paranaguá - Canal da Galheta, Paraná, Brazil',
        'lat': -25.5667, 'lon': -48.3167,
        'state': 'Parana', 'utc_offset': 3,
        'pdfs': {
            2024: '48_-_barra_paranagua_galheta_2024_ok.pdf',
            2025: '50 - BARRA DE PARANAGU\u00c1 - CANAL GALHETA - 158-160.pdf',
            2026: '50 - BARRA DE PARANAGU\u00c1 - CANAL DA GALHETA 160 -162.pdf',
        },
    },
    # DHN 49
    {
        'dhn': 49,
        'name': 'Paranaguá - Canal Sueste, Paraná, Brazil',
        'lat': -25.46, 'lon': -48.1567,
        'state': 'Parana', 'utc_offset': 3,
        'pdfs': {
            2024: '47_-_barra_paranagua_cais_sueste_2024_ok.pdf',
            2025: '49 - BARRA DE PARANAGU\u00c1 - CANAL SUESTE - 155-157.pdf',
            2026: '49 - BARRA DE PARANAGU\u00c1 - CANAL SUESTE 157 - 159.pdf',
        },
    },
    # DHN 50
    {
        'dhn': 50,
        'name': 'Paranaguá - Cais Oeste, Paraná, Brazil',
        'lat': -25.3067, 'lon': -48.3217,
        'state': 'Parana', 'utc_offset': 3,
        'pdfs': {
            2024: '49_-_porto_de_paranagua_cais_oeste_2024_ok.pdf',
            2025: '48 - PORTO DE PARANAGU\u00c1 - 152-154.pdf',
            2026: '48 - PORTO DE PARANAGU\u00c1 - CAIS OESTE - 154 - 156.pdf',
        },
    },
    # DHN 51
    {
        'dhn': 51,
        'name': 'São Francisco do Sul, Santa Catarina, Brazil',
        'lat': -26.245, 'lon': -48.6417,
        'state': 'Santa Catarina', 'utc_offset': 3,
        'pdfs': {
            2024: '51_-_sao_fco_do_sul_2024_ok.pdf',
            2025: '51 - PORTO DE S\u00c3O FRANCISCO DO SUL - 161-163.pdf',
            2026: '51 - PORTO DE S\u00c3O FRANCISCO DO SUL - 163 -165.pdf',
        },
    },
    # DHN 52
    {
        'dhn': 52,
        'name': 'Itajaí, Santa Catarina, Brazil',
        'lat': -26.9067, 'lon': -48.6483,
        'state': 'Santa Catarina', 'utc_offset': 3,
        'pdfs': {
            2024: '52_-_porto_de_itajai_2024_ok.pdf',
            2025: '52 - PORTO DE ITAJA\u00cd - 164-166.pdf',
            2026: '52 - PORTO DE ITAJA\u00cd - 166 - 168.pdf',
        },
    },
    # DHN 53
    {
        'dhn': 53,
        'name': 'Florianópolis, Santa Catarina, Brazil',
        'lat': -27.5883, 'lon': -48.5567,
        'state': 'Santa Catarina', 'utc_offset': 3,
        'pdfs': {
            2024: '53_-_porto_de_florianopolis_2024_ok.pdf',
            2025: '53 - PORTO DE FLORIAN\u00d3POLIS - 167-169.pdf',
            2026: '53 - PORTO DE FLORIAN\u00d3POLIS - 169 - 171.pdf',
        },
    },
    # DHN 54
    {
        'dhn': 54,
        'name': 'Imbituba, Santa Catarina, Brazil',
        'lat': -28.2309, 'lon': -48.6507,
        'state': 'Santa Catarina', 'utc_offset': 3,
        'pdfs': {
            2024: '54_-_porto_de_imbituba_2024_ok.pdf',
            2025: '54 - PORTO DE IMBITUBA - 170-172.pdf',
            2026: '54 - PORTO DE IMBITUBA - 172 - 174.pdf',
        },
    },
    # DHN 55
    {
        'dhn': 55,
        'name': 'Rio Grande, Rio Grande do Sul, Brazil',
        'lat': -32.1383, 'lon': -52.1033,
        'state': 'Rio Grande do Sul', 'utc_offset': 3,
        'pdfs': {
            2024: '55_-_porto_de_rio_grande_2024_ok.pdf',
            2025: '6 - PORTO DO RIO GRANDE (ESTADO DO RIO GRANDE DO SUL) - 2025 - P\u00e1ginas 173 a 175.pdf',
            2026: '55 - PORTO DO RIO GRANDE - 175 -177.pdf',
        },
    },
    # DHN 56
    {
        'dhn': 56,
        'name': 'Estação Antártica Comandante Ferraz, Antártica, Brazil',
        'lat': -62.085, 'lon': -58.3917,
        'state': 'Antartica', 'utc_offset': 3,
        'pdfs': {
            2024: '56_-_fundeadouro_eacf_2024_ok.pdf',
            2025: '56 - FUND. ESTA\u00c7\u00c3O COMANDANTE FERRAZ - 176 - 178.pdf',
            2026: '56 - FUNDEADOURO DA EST ANT COM FERRAZ - 178 - 180.pdf',
        },
    },
]

# Build DHN number lookup
DHN_LOOKUP = {s['dhn']: i for i, s in enumerate(STATIONS)}


# ============================================================
# PDF parsing using PyMuPDF word positions
# ============================================================
def parse_pdf_fitz(filename, year):
    """Parse a DHN tide table PDF using word positions.
    Works for both 2024 (1 decimal) and 2025/2026 (2 decimal) formats.
    Layout: 3 pages, each with 4 months in 8 sub-columns (day 1-16, day 17-31).
    """
    doc = fitz.open(filename)
    page_months = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
    ]

    entries = []

    for page_idx, page in enumerate(doc):
        if page_idx >= 3:
            break
        months = page_months[page_idx]
        words = page.get_text('words')

        # Find the 8 sub-column x-positions from day numbers
        day_words = [(w[0], w[1], w[4]) for w in words
                     if w[1] > 95 and w[1] < 170 and re.match(r'^\d{1,2}$', w[4])
                     and 1 <= int(w[4]) <= 31]
        day_xs = sorted(set(round(w[0], 0) for w in day_words))

        if len(day_xs) < 8:
            # Try wider y range
            day_words = [(w[0], w[1], w[4]) for w in words
                         if w[1] > 85 and re.match(r'^\d{1,2}$', w[4])
                         and 1 <= int(w[4]) <= 31]
            day_xs = sorted(set(round(w[0], 0) for w in day_words))

        # Keep only the 8 most common x clusters
        if len(day_xs) > 8:
            # Cluster nearby x values (within 5 units)
            clusters = []
            for x in day_xs:
                merged = False
                for c in clusters:
                    if abs(x - c[-1]) < 5:
                        c.append(x)
                        merged = True
                        break
                if not merged:
                    clusters.append([x])
            day_xs = [min(c) for c in sorted(clusters, key=lambda c: c[0])[:8]]

        if len(day_xs) != 8:
            print(f"  Warning page {page_idx} of {os.path.basename(filename)}: "
                  f"{len(day_xs)} day columns (expected 8)")
            if len(day_xs) < 4:
                continue

        sub_col_centers = day_xs

        def closest_subcol(x):
            min_dist = 999
            best = 0
            for ci, cx in enumerate(sub_col_centers):
                dist = abs(x - cx)
                if dist < min_dist:
                    min_dist = dist
                    best = ci
            return best

        # Collect all data words below header
        data_words = [(w[0], w[1], w[4]) for w in words if w[1] > 95]
        # Filter out symbols and non-data
        skip_words = {'v', 'c', '&', '*', 'z', 'HORA', 'ALT', 'ALT(m)', '(m)',
                      'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'SÁB', 'DOM',
                      'Janeiro', 'Fevereiro', 'Março', 'Marco', 'Abril',
                      'Maio', 'Junho', 'Julho', 'Agosto',
                      'Setembro', 'Outubro', 'Novembro', 'Dezembro'}

        data_words = [(x, y, t) for x, y, t in data_words if t not in skip_words]

        # Day assignments per subcol
        day_assignments = defaultdict(list)
        for x, y, text in data_words:
            if re.match(r'^\d{1,2}$', text):
                val = int(text)
                if 1 <= val <= 31:
                    ci = closest_subcol(x)
                    day_assignments[ci].append((y, val))

        for ci in day_assignments:
            day_assignments[ci].sort()

        def get_day_for_subcol(ci, y):
            best_day = None
            for dy, dval in day_assignments[ci]:
                if dy <= y + 3:
                    best_day = dval
                else:
                    break
            return best_day

        # Group words by y-row
        rows = defaultdict(list)
        for x, y, t in data_words:
            y_key = round(y / 2) * 2
            rows[y_key].append((x, y, t))

        for y_key in sorted(rows.keys()):
            row = sorted(rows[y_key], key=lambda w: w[0])

            i = 0
            while i < len(row):
                x, y, text = row[i]
                if re.match(r'^\d{4}$', text):
                    hour = int(text[:2])
                    minute = int(text[2:])
                    if hour >= 24:
                        i += 1
                        continue
                    # Look for height value next
                    if i + 1 < len(row):
                        x2, y2, text2 = row[i + 1]
                        # Accept both dot and comma as decimal separator
                        if re.match(r'^-?\d+[.,]\d+$', text2) and abs(x2 - x) < 35:
                            height = float(text2.replace(',', '.'))
                            ci = closest_subcol(x)
                            month_idx = ci // 2
                            if month_idx < len(months):
                                month = months[month_idx]
                                day = get_day_for_subcol(ci, y)

                                if day:
                                    try:
                                        dt = datetime(year, month, day, hour, minute)
                                        entries.append((dt, height))
                                    except ValueError:
                                        pass
                            i += 2
                            continue
                i += 1

    doc.close()
    return entries


# ============================================================
# OCR fallback for image-based PDFs
# ============================================================
def parse_pdf_ocr(filename, year):
    """Parse an image-based DHN tide table PDF using OCR.
    Renders each page at 300 DPI, runs pytesseract, then parses
    HHMM + height patterns from the OCR text.
    Returns list of (datetime, height) tuples.
    """
    if not HAS_OCR:
        print("  ERROR: pytesseract/PIL not available for OCR")
        return []

    doc = fitz.open(filename)
    page_months = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
    ]

    entries = []

    for page_idx, page in enumerate(doc):
        if page_idx >= 3:
            break
        months = page_months[page_idx]

        # Render page at 300 DPI
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Run OCR
        # Use English OCR (Portuguese not always installed)
        text = pytesseract.image_to_string(img)

        # Parse OCR text line by line
        # DHN tables have lines like: "1  0342 3.8  1008 0.5  1552 3.6  2221 0.6"
        # or with 2 decimals: "1  0342 3.82  1008 0.54"
        # We look for day numbers followed by time+height pairs

        lines = text.split('\n')
        current_day = {}  # month_idx -> day

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to find time (HHMM) + height pairs
            # Pattern: 4 digits (time) followed by a height value
            tokens = line.split()
            if not tokens:
                continue

            # Check if line starts with a day number (1-31)
            token_idx = 0
            day_value = None
            if tokens[0].isdigit() and 1 <= int(tokens[0]) <= 31:
                day_value = int(tokens[0])
                token_idx = 1

            # Now look for HHMM + height pairs in remaining tokens
            while token_idx < len(tokens) - 1:
                tok = tokens[token_idx]
                # Check if this looks like a time (4 digits, valid HHMM)
                if re.match(r'^\d{4}$', tok):
                    hour = int(tok[:2])
                    minute = int(tok[2:])
                    if hour < 24 and minute < 60:
                        # Next token should be height
                        next_tok = tokens[token_idx + 1]
                        # Accept heights like 3.8, 0.54, 3,82 etc
                        if re.match(r'^-?\d+[.,]\d+$', next_tok):
                            height = float(next_tok.replace(',', '.'))

                            # Determine which month block this belongs to
                            # OCR doesn't give us column positions, so we need to
                            # count pairs within the line to determine month offset
                            # Each line can have entries from multiple month columns
                            # For now, we try to use the day number if available
                            if day_value is not None:
                                # Count how many time-height pairs we've found so far
                                # to determine month offset within this page
                                # This is approximate - OCR may jumble columns
                                pair_count = 0
                                for j in range(1, token_idx):
                                    if re.match(r'^\d{4}$', tokens[j]):
                                        jh = int(tokens[j][:2])
                                        jm = int(tokens[j][2:])
                                        if jh < 24 and jm < 60 and j + 1 < len(tokens):
                                            if re.match(r'^-?\d+[.,]\d+$', tokens[j + 1]):
                                                pair_count += 1

                                # Each month has ~4 entries per day (2 HW + 2 LW)
                                # Use pair_count to guess month offset
                                month_offset = pair_count // 4
                                if month_offset >= len(months):
                                    month_offset = len(months) - 1
                                month = months[month_offset]

                                try:
                                    dt = datetime(year, month, day_value, hour, minute)
                                    entries.append((dt, height))
                                except ValueError:
                                    pass

                            token_idx += 2
                            continue
                token_idx += 1

    doc.close()
    print(f"    OCR extracted {len(entries)} raw entries")
    return entries


def is_image_pdf(filename):
    """Check if a PDF is image-based (no extractable text)."""
    doc = fitz.open(filename)
    total_text = ""
    for page_idx, page in enumerate(doc):
        if page_idx >= 3:
            break
        total_text += page.get_text()
    doc.close()
    return len(total_text.strip()) < 50


# ============================================================
# Interpolation and UTide analysis
# ============================================================
def check_monotonic_and_fix(entries):
    """Sort by datetime and remove duplicates."""
    entries.sort(key=lambda e: e[0])
    fixed = []
    for dt, h in entries:
        if fixed and dt == fixed[-1][0]:
            continue
        fixed.append((dt, h))
    return fixed


def interpolate_to_hourly(entries):
    """Interpolate HW/LW points to hourly using half-cosine segments."""
    first_year = entries[0][0].year
    base = datetime(first_year, 1, 1, 0, 0)
    times = np.array([(e[0] - base).total_seconds() / 3600.0 for e in entries])
    heights = np.array([e[1] for e in entries])

    t_start = int(np.ceil(times[0]))
    t_end = int(np.floor(times[-1]))
    t_hourly = np.arange(t_start, t_end + 1, 1.0)
    h_hourly = np.zeros_like(t_hourly)

    seg_idx = 0
    for i, t in enumerate(t_hourly):
        while seg_idx < len(times) - 2 and t > times[seg_idx + 1]:
            seg_idx += 1

        t1 = times[seg_idx]
        t2 = times[seg_idx + 1]
        h1 = heights[seg_idx]
        h2 = heights[seg_idx + 1]

        phase = np.pi * (t - t1) / (t2 - t1)
        h_hourly[i] = (h1 + h2) / 2.0 + (h1 - h2) / 2.0 * np.cos(phase)

    dt_hourly = [base + timedelta(hours=int(t)) for t in t_hourly]
    return dt_hourly, h_hourly


def run_utide_analysis(times, heights, lat):
    """Run UTide harmonic analysis. Passes datetime objects directly."""
    t_arr = np.array(times)

    coef = utide.solve(
        t_arr, heights, lat=lat,
        nodal=True, trend=False, method='ols',
        conf_int='linear', verbose=False, constit='auto',
    )
    return coef


def format_xtide_harmonics(coef, station_name, lat, lon, state,
                           utc_offset_hours=3, years_str='2024-2026'):
    """Format UTide results as XTide harmonics file entry (175 constituents)."""
    from utide._ut_constants import ut_constants
    const_table = ut_constants['const']
    utide_names = [n.strip() for n in const_table.name]

    utide_results = {}
    for i, uname in enumerate(coef['name']):
        uname = uname.strip()
        amp = coef['A'][i]
        phase_local = coef['g'][i]

        if uname in utide_names:
            idx = utide_names.index(uname)
            utide_speed = const_table.freq[idx] * 360.0
        else:
            continue

        # Convert local phase to Greenwich phase
        phase_greenwich = (phase_local + utide_speed * utc_offset_hours) % 360

        xt_name_result = find_xtide_match(uname, utide_speed)
        if xt_name_result is None:
            continue
        xt_name, xt_speed = xt_name_result

        utide_results[xt_name] = {
            'amplitude': amp,
            'phase': phase_greenwich,
        }

    lines = []
    lines.append(f"# {station_name}")
    lines.append(f"# Derived from Marinha do Brasil (DHN) official tide tables {years_str}")
    lines.append(f"# Harmonic analysis via UTide from interpolated HW/LW predictions")
    lines.append(f"#")
    lines.append(f"# {station_name}")
    lines.append(f"# BEGIN HOT COMMENTS")
    lines.append(f"# country: Brazil")
    lines.append(f"# state: {state}")
    lines.append(f"# source: Derived from Marinha do Brasil (DHN) tide tables with UTide")
    lines.append(f"# date_imported: 20260406")
    lines.append(f"# datum: Chart Datum (Marinha)")
    lines.append(f"# confidence: 8")
    lines.append(f"# !units: meters")
    lines.append(f"# !longitude: {lon:.6f}")
    lines.append(f"# !latitude: {lat:.6f}")
    lines.append(station_name)
    lines.append(f"+00:00 :UTC")

    z0 = coef['mean']
    lines.append(f"{z0:.4f} meters")

    for name, speed in CONSTITUENTS_175:
        if name in utide_results:
            r = utide_results[name]
            if r['amplitude'] >= 0.00005:
                lines.append(f"{name:15s} {r['amplitude']:.4f}  {r['phase']:.2f}")
            else:
                lines.append(f"x 0 0")
        else:
            lines.append(f"x 0 0")

    return '\n'.join(lines)


# ============================================================
# Main
# ============================================================
def process_station(station, use_2024=True):
    """Process a single station: parse PDFs, interpolate, run UTide, output harmonics."""
    print(f"\n{'='*70}")
    print(f"Station: {station['name']} (DHN {station['dhn']})")
    print(f"{'='*70}")

    utc_offset = station.get('utc_offset', 3)
    all_entries = []
    years_used = []

    for year in sorted(station['pdfs'].keys()):
        pdf_name = station['pdfs'][year]
        pdf_path = os.path.join(BASE, pdf_name)
        if not os.path.exists(pdf_path):
            print(f"  WARNING: {pdf_path} not found, skipping year {year}")
            continue

        if year == 2024 and not use_2024:
            print(f"  Skipping {year} (1 decimal precision)")
            continue

        print(f"  Parsing {year}: {os.path.basename(pdf_path)}")

        # Try normal fitz extraction first; fall back to OCR if image PDF
        if is_image_pdf(pdf_path):
            print(f"    Image-based PDF detected, trying OCR...")
            entries = parse_pdf_ocr(pdf_path, year)
        else:
            entries = parse_pdf_fitz(pdf_path, year)

        print(f"    -> {len(entries)} entries")

        if entries:
            # Quick sanity check
            months_found = set(e[0].month for e in entries)
            print(f"    Months: {sorted(months_found)}")
            all_entries.extend(entries)
            years_used.append(year)

    if not all_entries:
        print("  ERROR: No entries found!")
        return None

    # Fix monotonicity
    entries = check_monotonic_and_fix(all_entries)
    print(f"\n  Total after dedup: {len(entries)} HW/LW entries")
    print(f"  Range: {entries[0][0]} to {entries[-1][0]}")

    # Check for gaps > 12h
    gap_count = 0
    for i in range(1, len(entries)):
        dt_diff = (entries[i][0] - entries[i-1][0]).total_seconds() / 3600
        if dt_diff > 12:
            gap_count += 1
            if gap_count <= 5:
                print(f"  Gap: {entries[i-1][0]} -> {entries[i][0]} ({dt_diff:.1f}h)")
    if gap_count > 5:
        print(f"  ... and {gap_count - 5} more gaps")

    # Check for alternating HW/LW (monotonicity of direction)
    direction_errors = 0
    for i in range(2, len(entries)):
        h_prev = entries[i-2][1]
        h_curr = entries[i-1][1]
        h_next = entries[i][1]
        # Three consecutive rising or falling values suggest a missed extremum
        if (h_curr > h_prev and h_next > h_curr) or (h_curr < h_prev and h_next < h_curr):
            direction_errors += 1
    if direction_errors > 0:
        print(f"  WARNING: {direction_errors} potential non-alternating HW/LW sequences")

    # Interpolate to hourly
    print(f"\n  Interpolating to hourly...")
    dt_hourly, h_hourly = interpolate_to_hourly(entries)
    print(f"  -> {len(dt_hourly)} hourly values ({dt_hourly[0]} to {dt_hourly[-1]})")

    # Run UTide
    print(f"  Running UTide analysis...")
    coef = run_utide_analysis(dt_hourly, h_hourly, station['lat'])

    print(f"  Mean level (Z0): {coef['mean']:.4f} m")
    print(f"  Constituents solved: {len(coef['name'])}")

    # Show top constituents
    idx = np.argsort(coef['A'])[::-1]
    print(f"\n  Top 10 constituents:")
    for i in idx[:10]:
        print(f"    {coef['name'][i].strip():8s}  A={coef['A'][i]:.4f}m  g={coef['g'][i]:8.2f}\u00b0")

    # Format output
    years_str = f"{min(years_used)}-{max(years_used)}"
    output = format_xtide_harmonics(
        coef, station['name'], station['lat'], station['lon'],
        station['state'], utc_offset_hours=utc_offset, years_str=years_str
    )

    return output


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Parse Brazilian DHN tide tables')
    parser.add_argument('--station', type=int, help='Process only station N (0-based index)')
    parser.add_argument('--dhn', type=int, help='Process only DHN station number (e.g. 4)')
    parser.add_argument('--no-2024', action='store_true', help='Skip 2024 data (1 decimal)')
    parser.add_argument('--output', default='/home/oliver/harmonics/utide/harmonics_utide_brazil_dhn.txt',
                        help='Output file path')
    args = parser.parse_args()

    use_2024 = not args.no_2024
    all_outputs = []

    if args.dhn is not None:
        if args.dhn not in DHN_LOOKUP:
            print(f"ERROR: DHN {args.dhn} not found. Available: {sorted(DHN_LOOKUP.keys())}")
            sys.exit(1)
        stations_to_process = [STATIONS[DHN_LOOKUP[args.dhn]]]
    elif args.station is not None:
        stations_to_process = [STATIONS[args.station]]
    else:
        stations_to_process = STATIONS

    for station in stations_to_process:
        output = process_station(station, use_2024=use_2024)
        if output:
            all_outputs.append(output)

    if all_outputs:
        # Read congen header template
        template_file = '/home/oliver/harmonics/template/harmonics_template.txt'
        with open(template_file, 'r', encoding='iso-8859-1') as f:
            header_text = f.read().rstrip() + '\n'

        with open(args.output, 'w', encoding='iso-8859-1') as f:
            f.write(header_text)
            for i, output in enumerate(all_outputs):
                f.write(output + '\n')

        print(f"\n{'='*70}")
        print(f"Written {len(all_outputs)} stations to {args.output}")
        print(f"{'='*70}")
