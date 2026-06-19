#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Stationsnamen: lokale Schreibweise (ISO-8859-1-Diakritika) + Bundesland
(Brazil/India/Mexico). Anwenden via Meridian-Anker (Namenszeile = Zeile VOR der
Zeitzonen-/Meridianzeile). Nur eindeutige Fälle; Unsicheres bleibt unverändert.

Aufruf:  python3 py/fix_att_localnames.py <batch> [--apply]
  batch = brazil | india | mexico | diacritics
Mappings sind exakte alte->neue Namensstrings (nur was geändert wird).
"""
import re, sys, glob

MER = re.compile(r'^[+-]\d{2}:\d{2}\s*:')
ATT = glob.glob("harmonics/att/*.txt")

BRAZIL = {
 "Barra Norte (Rio de Brigue), Brazil": "Barra Norte (Rio de Brigue), Amapá, Brazil",
 "Macapa, Brazil": "Macapá, Amapá, Brazil",
 "Porto de Santana, Brazil": "Porto de Santana, Amapá, Brazil",
 "Salinopolis, Brazil": "Salinópolis, Pará, Brazil",
 "Ilha de Colares, Brazil": "Ilha de Colares, Pará, Brazil",
 "Porto de Mosqueiro, Brazil": "Porto de Mosqueiro, Pará, Brazil",
 "Ilhas de Sao Joao, Brazil": "Ilhas de São João, Maranhão, Brazil",
 "Belem, Brazil": "Belém, Pará, Brazil",
 "Ilha de Santana, Brazil": "Ilha de Santana, Maranhão, Brazil",
 "Acarau, Brazil": "Acaraú, Ceará, Brazil",
 "Camocim, Brazil": "Camocim, Ceará, Brazil",
 "Areia Branca (Salineiro Terminal), Brazil": "Areia Branca (Salineiro Terminal), Rio Grande do Norte, Brazil",
 "Porto de Natal, Brazil": "Porto de Natal, Rio Grande do Norte, Brazil",
 "Cabedelo, Brazil": "Cabedelo, Paraíba, Brazil",
 "Tambau, Brazil": "Tambaú, Paraíba, Brazil",
 "Tamandare, Brazil": "Tamandaré, Pernambuco, Brazil",
 "Porto de Pedras, Brazil": "Porto de Pedras, Alagoas, Brazil",
 "Maceio, Brazil": "Maceió, Alagoas, Brazil",
 "Rio Sao Francisco Bar, Brazil": "Rio São Francisco Bar, Brazil",   # AL/SE-Grenze: kein Bundesland
 "Aracaju, Brazil": "Aracaju, Sergipe, Brazil",
 "Ponta do Alambique, Brazil": "Ponta do Alambique, Bahia, Brazil",
 "Salvador, Brazil": "Salvador, Bahia, Brazil",
 "Morro de Sao Paulo, Brazil": "Morro de São Paulo, Bahia, Brazil",
 "Porto Seguro, Brazil": "Porto Seguro, Bahia, Brazil",
 "Cumuruxatiba, Brazil": "Cumuruxatiba, Bahia, Brazil",
 "Nova Vicosa, Brazil": "Nova Viçosa, Bahia, Brazil",
 "Ilhas dos Abrolhos, Brazil": "Ilhas dos Abrolhos, Bahia, Brazil",
 "Regencia, Brazil": "Regência, Espírito Santo, Brazil",
 "Barra do Riacho, Brazil": "Barra do Riacho, Espírito Santo, Brazil",
 "Vitoria, Brazil": "Vitória, Espírito Santo, Brazil",
 "Guarapari, Brazil": "Guarapari, Espírito Santo, Brazil",
 "Itapemirim, Brazil": "Itapemirim, Espírito Santo, Brazil",
 "Atafona, Brazil": "Atafona, Rio de Janeiro, Brazil",
 "Cabo de Sao Tome, Brazil": "Cabo de São Tomé, Rio de Janeiro, Brazil",
 "Ilha de Brocoio, Brazil": "Ilha de Brocoió, Rio de Janeiro, Brazil",
 "Porto Buzios, Brazil": "Porto Búzios, Rio de Janeiro, Brazil",
 "Ilha do Boqueirao, Brazil": "Ilha do Boqueirão, Rio de Janeiro, Brazil",
 "Cabo Frio, Brazil": "Cabo Frio, Rio de Janeiro, Brazil",
 "Ilha Guaiba, Brazil": "Ilha Guaíba, Rio de Janeiro, Brazil",
 "Angra dos Reis, Brazil": "Angra dos Reis, Rio de Janeiro, Brazil",
 "Parati, Brazil": "Parati, Rio de Janeiro, Brazil",
 "Santos, Brazil": "Santos, São Paulo, Brazil",
 "Ponta Paranapua, Brazil": "Ponta Paranapua, São Paulo, Brazil",   # Schreibweise unsicher -> nur Bundesland
 "Icapara, Brazil": "Icapara, São Paulo, Brazil",
 "Itajai, Brazil": "Itajaí, Santa Catarina, Brazil",
 "Porto Belo, Brazil": "Porto Belo, Santa Catarina, Brazil",
 "Florianopolis, Brazil": "Florianópolis, Santa Catarina, Brazil",
 "Laguna, Brazil": "Laguna, Santa Catarina, Brazil",
 "Tramandai, Brazil": "Tramandaí, Rio Grande do Sul, Brazil",
 "Rio Grande, Brazil": "Rio Grande, Rio Grande do Sul, Brazil",
 # UNVERÄNDERT (unsicher): "Ilha Irmaos, Brazil", "Barra do Timonha, Brazil"
}

MAPS = {"brazil": BRAZIL}


def apply_map(mapping, do):
    hits = {k: 0 for k in mapping}
    for f in ATT:
        L = open(f, encoding="iso-8859-1", errors="replace").read().split("\n")
        chg = 0
        for i in range(1, len(L)):
            if MER.match(L[i]) and not L[i-1].startswith("#"):
                nm = L[i-1]
                if nm in mapping:
                    hits[nm] += 1
                    if do:
                        L[i-1] = mapping[nm]
                    chg += 1
        if do and chg:
            open(f, "w", encoding="iso-8859-1").write("\n".join(L))
    return hits


def main():
    batch = sys.argv[1] if len(sys.argv) > 1 else "brazil"
    do = "--apply" in sys.argv
    mapping = MAPS[batch]
    hits = apply_map(mapping, do)
    matched = sum(1 for v in hits.values() if v == 1)
    multi = [k for k, v in hits.items() if v > 1]
    miss = [k for k, v in hits.items() if v == 0]
    print(f"[{batch}] Mapping={len(mapping)}  getroffen(1x)={matched}  "
          f"mehrfach={len(multi)}  nicht gefunden={len(miss)}")
    for k in miss:
        print(f"   MISS: {k!r}")
    for k in multi:
        print(f"   MULTI: {k!r} ({hits[k]}x)")
    print("ANGEWENDET" if do else "DRY-RUN")


if __name__ == "__main__":
    main()
