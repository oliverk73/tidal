#!/usr/bin/env python3
"""Fix encoding errors in subordinate_stations_mapped.csv"""

import re

# Mapping of broken strings to correct strings
corrections = {
    # Brazilian Portuguese names
    "Cabo Cassipor�": "Cabo Cassiporé",
    "Rio Par�": "Rio Pará",
    "Canan�ia": "Cananéia",
    "Florian�polis": "Florianópolis",
    "Ilhas de S�o Jo�o": "Ilhas de São João",
    "Ilh�us": "Ilhéus",
    "Itaja�": "Itajaí",
    "Macap�": "Macapá",
    "Maca�": "Macaé",
    "Macei�": "Maceió",
    "Morro de S�o Paulo": "Morro de São Paulo",
    "Paranagu�": "Paranaguá",
    "P�rto Belo": "Pôrto Belo",
    "Rio S�o Francisco": "Rio São Francisco",
    "Salin�polis": "Salinópolis",
    "Santa Cruz Cabr�lia": "Santa Cruz Cabrália",
    "S�o Jo�o da Barra": "São João da Barra",
    "S�o Lu�s": "São Luís",
    "S�o Sebasti�o": "São Sebastião",
    "Tut�ia": "Tutóia",
    "Vit�ria": "Vitória",

    # Greenland names (Danish)
    "Frederiksh�b": "Frederikshåb",
    "Godth�b": "Godthåb",
    "Julianeh�b": "Julianehåb",

    # Canadian names (French)
    "Gasp�": "Gaspé",
    "Caw�e": "Cawée",

    # Caribbean names
    "Rivi�re du": "Rivière du",
    "Pointe-�-Pitre": "Pointe-à-Pitre",
    "Cura�ao": "Curaçao",

    # Mexican names
    "Yucat�n": "Yucatán",
    "Pil�n": "Pilón",
    "Mais�": "Maisí",

    # Suriname
    "Nickerie Rivi�r": "Nickerie Rivier",

    # Canadian French
    "�le Haute": "Île Haute",
    "�les du Salut": "Îles du Salut",

    # Portuguese (Azores)
    "S�o Miguel, A�ores": "São Miguel, Açores",

    # Iceland
    "�sland": "Ísland",

    # Belgian
    "Belgi�": "België",

    # German
    "Scharh�rn": "Scharhörn",
    "Steubenh�ft": "Steubenhöft",
    "Gl�ckstadt": "Glückstadt",
    "L�hort": "Lühort",
    "S�derpiep": "Süderpiep",
    "T�nning": "Tönning",
    "S�dfall": "Südfall",
    "S�der Aue": "Süder Aue",
    "F�hr": "Föhr",
    "Dageb�ll": "Dagebüll",
    "H�rnum": "Hörnum",

    # Danish
    "R�m�": "Rømø",
    "S�nderho": "Sønderho",
    "Fan�": "Fanø",
    "Bl�vandshuk": "Blåvandshuk",
    "Thybor�nn": "Thyborønn",

    # Norwegian
    "Flor�": "Florø",

    # Venezuelan
    "Malec�n": "Malecón",

    # Mozambique
    "Mo�ambique": "Moçambique",
}

def fix_file(input_path, output_path=None):
    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # Apply all corrections
    fixed_count = 0
    for broken, correct in corrections.items():
        if broken in content:
            count = content.count(broken)
            content = content.replace(broken, correct)
            print(f"Fixed: '{broken}' -> '{correct}' ({count} occurrences)")
            fixed_count += count

    # Write the fixed content
    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

    print(f"\nTotal fixes applied: {fixed_count}")
    print(f"Output written to: {output_path}")

if __name__ == "__main__":
    fix_file("/home/oliver/subordinate_corrections/subordinate_stations_mapped.csv")
