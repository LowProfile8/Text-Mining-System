#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Athena Advisory Group Sagl — Engine AI v5.0
Migliorie v5:
  - Prompt contabile completamente riscritto con rigore Swiss GAAP FER
  - Logica M/I basata sulla rivendibilità del bene (non solo conto dare)
  - Riga cambio: descrizione in col3, conto perdita cambio in dare, stesso ctAvere in avere, importo vuoto
  - Fornitore sconosciuto: conto 4000 + flag indice_giallo_dare per evidenziare cella
  - IVA split multi-aliquota con righe separate per ogni aliquota
  - Valuta default CHF, tasso 0.00 se non reperibile (da verificare manualmente)
  - Fatture multi-pagina: totale sempre dall'ultima pagina
  - Note di credito / importi negativi: inversione Dare/Avere automatica
  - Logging strutturato completo
"""

import io
import json
import base64
import zipfile
import re
import asyncio
import logging
import unicodedata
from datetime import datetime

import pandas as pd
from openai import AsyncOpenAI
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps, ImageFilter

# ==============================================================================
# LOGGER
# ==============================================================================

logger = logging.getLogger("athena.engine_ai")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)

# ==============================================================================
# PIANO DEI CONTI SWISS GAAP FER — COMPLETO
# ==============================================================================

PIANO_CONTI_COMPLETO = """
═══ ATTIVI ═══
1000 Cassa | 1020 Conto corrente bancario | 1025 CC bancario valuta estera
1045 Carte di credito/debito | 1100 Crediti Svizzera | 1101 Crediti estero
1102 Crediti estero in valuta estera | 1170 Imposta precedente su costi materiale/prestazioni
1171 Imposta precedente su investimenti e altri costi esercizio
1172 Compensazione deduzione imposta precedente (metodo rendiconto)
1175 IVA rendiconto | 1192 Anticipi a fornitori | 1200 Scorte prodotti commerciali
1210 Scorte materie prime | 1300 Risconti attivi (costi pagati anticipatamente)
1301 Ratei attivi (ricavi non ancora ricevuti)
1500 Macchine e attrezzature | 1509 Ammortamenti macchine e attrezzature
1510 Mobilio e installazioni | 1511 Installazioni officina | 1512 Installazioni negozio
1513 Mobili ufficio | 1519 Ammortamenti mobilio e installazioni
1520 Macchine ufficio | 1521 Informatica | 1522 Tecnologia comunicazione
1529 Ammortamenti macchine ufficio/informatica/comunicazione
1530 Veicoli | 1537 Veicoli in leasing | 1539 Ammortamenti veicoli
1540 Utensili e apparecchiature | 1549 Ammortamenti utensili
1570 Impianti fissi | 1571 Installazioni fisse | 1579 Ammortamenti impianti fissi
1600 Immobili aziendali | 1609 Ammortamenti immobili aziendali
1700 Brevetti | 1710 Marchi | 1720 Licenze | 1721 Concessioni | 1722 Diritti d'uso
1740 Software sviluppato in proprio | 1741 Software e licenze acquistati
1749 Ammortamenti software | 1770 Goodwill | 1779 Ammortamenti goodwill

═══ PASSIVI ═══
2000 Debiti per costi materiale/merce | 2001 Debiti per prestazioni di terzi
2002 Debiti per costi personale | 2004 Debiti per altri costi d'esercizio
2030 Anticipi da terzi | 2100 Conto corrente bancario (debito)
2120 Impegni da leasing finanziari | 2200 IVA dovuta | 2201 Rendiconto IVA
2300 Costi da pagare | 2301 Ricavi incassati anticipatamente
2340 Accantonamenti per imposte dirette
2800 Capitale azionario/sociale | 2970 Utile riportato | 2979 Utile/perdita annua

═══ RICAVI (AVERE) ═══
3000 Ricavi lordi prodotti fabbricati | 3001 Ricavi lordi vendite al dettaglio
3002 Ricavi lordi vendite all'ingrosso | 3090 Sconti | 3091 Ribassi e riduzioni
3200 Ricavi lordi merci di rivendita | 3290 Sconti su merci rivendita
3400 Ricavi lordi prestazioni di servizi | 3490 Sconti su prestazioni
3600 Ricavi da materie prime | 3680 Altri ricavi | 3809 IVA aliquota saldo
3900 Variazioni scorte prodotti finiti | 3940 Variazioni valore prestazioni non fatturate

═══ COSTI DIRETTI — MATERIALE E MERCI (DARE) ═══
4000 Acquisti materiale/prodotti (materie prime, componenti, accessori, materiale ausil.)
4001 Acquisti componenti | 4002 Acquisti accessori | 4003 Acquisti altri materiali
4004 Acquisti materiale ausiliario e di consumo | 4005 Acquisti materiale imballaggio
4006 Prestazione di terzi (diretta) | 4007 Spese d'acquisto dirette
4060 Prestazioni di terzi settore specifico | 4070 Noli in entrata
4071 Dazi all'importazione | 4072 Spedizioni in entrata
4200 Acquisti articoli di rivendita | 4205 Acquisti materiale imballaggio rivendita
4270 Noli in entrata rivendita | 4271 Dazi importazione rivendita
4400 Lavori di terzi/prestazioni subappaltanti | 4407 Spese acquisto dirette terzisti
4500 Corrente calorica produzione | 4501 Corrente industriale
4510 Gas naturale produzione | 4530 Benzina produzione | 4531 Diesel produzione
4900 Variazioni scorte merci rivendita | 4901 Variazioni scorte materie prime

═══ COSTI PERSONALE (DARE) ═══
5000 Salari (produzione) | 5070 AVS,AI,IPG,AD | 5072 Previdenza professionale
5073 Assicurazione infortuni | 5074 Assicurazione indennita giornaliera malattia
5080 Ricerca personale | 5081 Formazione e aggiornamento | 5082 Rimborsi spese effettive
5200 Salari (commercio) | 5400 Salari (servizi) | 5600 Salari (amministrazione)
5603 Salari a partecipanti e direzione | 5604 Onorari CdA
5700 AVS,AI,IPG,AD (titolare) | 5720 Previdenza professionale
5800 Inserzioni personale | 5810 Formazione aziendale | 5820 Spese di viaggio
5821 Spese vitto | 5822 Spese alloggio | 5830 Spese forfettarie quadri
5840 Mensa personale viveri | 5900 Prestazioni di terzi (personale)

═══ COSTI LOCALI (DARE) ═══
6000 Canone locazione fabbrica | 6001 Canone locazione officina/atelier
6002 Canone locazione magazzino | 6003 Canone locazione locali esposizione/vendita
6004 Canone locazione locali ufficio/amministrazione | 6005 Canone locazione locali personale
6006 Canone locazione garage/parcheggio
6030 Costi accessori (riscaldamento, energia, gas, acqua)
6040 Pulizia locali | 6050 Manutenzione locali | 6051 Riparazioni locali
6059 Prestazioni assicurative locali | 6060 Leasing immobili aziendali

═══ COSTI MRS / LEASING IMMOBILIZZAZIONI (DARE) ═══
6100 MRS macchine e attrezzature | 6101 MRS mobilio e installazioni
6102 MRS utensili e apparecchiature | 6105 Leasing impianti produzione
6110 MRS installazioni negozi | 6115 Leasing installazioni vendita
6120 MRS magazzino | 6125 Leasing installazioni magazzino
6130 MRS mobili ufficio | 6131 MRS macchine ufficio | 6132 MRS informatica
6133 MRS tecnologia comunicazione | 6135 Leasing installazioni personale

═══ COSTI AUTO E TRASPORTO (DARE) ═══
6200 Riparazioni veicoli | 6201 Servizi veicoli | 6202 Pulizia veicoli
6210 Benzina (veicoli aziendali) | 6211 Diesel (veicoli aziendali) | 6212 Olio veicoli
6213 Corrente (veicoli elettrici) | 6220 Assicurazione RC veicoli
6221 Assicurazione casco | 6222 Assicurazione protezione giuridica veicoli
6230 Tasse di circolazione | 6260 Leasing veicoli | 6264 Noleggio veicoli
6280 Noli trasporto | 6281 Spedizionieri | 6282 Cargo domicilio

═══ ASSICURAZIONI, CONTRIBUTI, TASSE (DARE) ═══
6300 Assicurazione danni calamita | 6301 Assicurazione rottura vetri | 6302 Assicurazione furto
6310 Assicurazione RC azienda | 6311 Assicurazione garanzie
6312 Assicurazione protezione giuridica | 6320 Assicurazione interruzione esercizio
6360 Contributi | 6361 Tasse | 6370 Permessi | 6371 Patenti d'esercizio

═══ COSTI ENERGIA E SMALTIMENTO (DARE) ═══
6400 Corrente elettrica | 6401 Corrente calorica | 6402 Corrente per luce
6410 Metano | 6411 Gas liquido in bombole | 6420 Olio riscaldamento
6430 Acqua | 6460 Spazzatura | 6461 Rifiuti speciali | 6462 Depurazione acque

═══ COSTI AMMINISTRATIVI E INFORMATICI (DARE) ═══
6500 Materiale ufficio | 6501 Stampanti | 6502 Fotocopie
6503 Pubblicazioni specialistiche, giornali, periodici
6510 Telefono | 6512 Internet | 6513 Porti (postali)
6520 Contributi associativi | 6521 Donazioni | 6522 Mance
6530 Tenuta contabilita | 6531 Consulenza aziendale | 6532 Consulenza giuridica
6540 Costi CdA | 6541 Costi assemblea generale | 6542 Costi ufficio revisione
6550 Costi di costituzione/aumento capitale | 6551 Costi incasso/esecuzione
6555 Spese di gestione | 6559 Altri costi di amministrazione
6570 Leasing Hardware | 6571 Leasing Software | 6572 Noleggio Hardware | 6573 Noleggio Software
6580 Costi licenze e aggiornamenti software | 6581 Assistenza/hotline hardware
6582 Assistenza/hotline software | 6583 Materiale di consumo IT
6585 Costi linea telefonica dedicata | 6590 Consulenza informatica base
6591 Sviluppo individuale/adattamenti | 6592 Costi d'introduzione sistemi

═══ COSTI PUBBLICITARI (DARE) ═══
6600 Inserzioni pubblicitarie | 6601 Pubblicita radiofonica | 6602 Pubblicita TV
6604 Internet e social media | 6610 Stampati pubblicitari, materiale pubblicitario
6611 Articoli pubblicitari, campioni, cartelloni e insegne elettroniche
6620 Vetrine, decorazioni | 6621 Fiere, esposizioni | 6640 Spese rappresentanza
6641 Assistenza clienti | 6642 Regali ai clienti | 6660 Contributi pubblicitari
6661 Sponsoring | 6670 Manifestazioni per clienti | 6680 Consulenze pubblicitarie
6681 Analisi di mercato

═══ ALTRI COSTI D'ESERCIZIO (DARE) ═══
6700 Informazioni commerciali | 6701 Esecuzioni | 6710 Sicurezza aziendale
6720 Ricerca e sviluppo | 6740 Correzione imposta precedente | 6790 Altri costi d'esercizio

═══ AMMORTAMENTI E RETTIFICHE (DARE) ═══
6820 Amm. macchine e attrezzature | 6821 Amm. mobilio e installazioni
6822 Amm. macchine ufficio/informatica/comunicazione | 6823 Amm. veicoli
6824 Amm. utensili e apparecchiature | 6825 Amm. installazioni magazzino
6827 Amm. impianti fissi | 6830 Amm. immobili aziendali
6840 Amm. brevetti/know-how | 6841 Amm. marchi/campioni/modelli
6842 Amm. licenze/concessioni/diritti | 6845 Amm. sviluppo | 6847 Amm. goodwill

═══ COSTI E RICAVI FINANZIARI ═══
6900 Costi interessi bancari | 6901 Costi interessi su prestiti
6902 Costi interessi mutui ipotecari | 6903 Costi interessi di mora
6905 Costi interessi su leasing finanziari | 6940 Spese bancarie generali
6941 Diritti di custodia | 6942 Perdite di corso su titoli a breve termine
6944 Perdite di corso su debiti onerosi | 6945 Conti clienti concessi (sconti passivi)
6947 Commissione di factoring | 6949 Perdite su cambio — USARE SEMPRE PER DIFF.CAMBIO
6950 Ricavi da averi bancari | 6960 Ricavi da titoli | 6962 Ricavi da partecipazioni
6995 Sconti ricevuti da fornitori | 6999 Utili su cambio

═══ STRAORDINARI ═══
8500 Accantonamenti straordinari | 8501 Amm. straordinari
8503 Perdite straordinarie su cambio | 8504 Perdite da alienazione attivo fisso
8510 Scioglimento riserve | 8511 Scioglimento accantonamenti
8513 Utili straordinari su cambio | 8514 Utili da alienazione attivo fisso
8900 Imposte sull'utile | 8901 Imposte sul capitale
"""

# ==============================================================================
# LOGICA PER SETTORE
# ==============================================================================

LOGICA_SETTORE = {
    "Ristorante / Bar / Take-away": {
        "desc": (
            "Settore F&B/ristorazione. "
            "COSTI DIRETTI classe 4 (M — merci/consumo immediato): alimenti, bevande, ingredienti, "
            "materie prime cucina, tovagliato monouso, imballaggi monouso, materiale consumo cucina. "
            "COSTI INDIRETTI classe 6: "
            "affitto locali -> 6003; elettricita -> 6400; gas/metano -> 6410; acqua -> 6430; "
            "pulizie -> 6040; manutenzione attrezzature -> 6100; riparazioni locali -> 6050; "
            "telefono/internet -> 6510/6512; materiale ufficio -> 6500; poste -> 6513; "
            "assicurazione RC -> 6310; assicurazioni -> 6300; tasse/contributi -> 6361/6360; "
            "carburante veicoli aziendali -> 6210/6211; "
            "pubblicita cartacea/volantini -> 6610; social media/web -> 6604; "
            "totem/insegne/cartelloni FISICI -> 6611 (NON 4000); "
            "software gestionale/cassa abbonamento -> 6580; "
            "consulenza contabile -> 6530; consulenza legale -> 6532; "
            "spese bancarie -> 6940; interessi bancari -> 6900. "
            "INVESTIMENTI classe 15xx-17xx (I — beni pluriennali > CHF 1000): "
            "forno professionale, frigorifero industriale, lavastoviglie, macchina caffe, "
            "arredamento, mobili, impianti fissi, veicoli aziendali, software perpetuo."
        ),
        "conto_fornitore_default": "2000",
    },
    "Noleggio auto": {
        "desc": (
            "Settore noleggio veicoli. "
            "COSTI DIRETTI classe 4 (M): carburante fleet -> 4530/4531; "
            "lubrificanti -> 4003; materiale consumo veicoli -> 4004. "
            "COSTI INDIRETTI classe 6: "
            "manutenzione/riparazioni veicoli -> 6200/6201; lavaggio veicoli -> 6202; "
            "assicurazione RC flotta -> 6220; assicurazione casco -> 6221; "
            "tasse circolazione -> 6230; leasing veicoli fleet -> 6260; "
            "noleggio veicoli sostitutivi -> 6264; affitto locali -> 6000; "
            "materiale ufficio -> 6500; telefono -> 6510; spese bancarie -> 6940. "
            "INVESTIMENTI (I): acquisto veicoli da rinoleggiare -> 1530; "
            "attrezzature officina -> 1500; software gestione fleet -> 1741."
        ),
        "conto_fornitore_default": "2000",
    },
    "Noleggio barche": {
        "desc": (
            "Settore noleggio nautico. "
            "COSTI DIRETTI classe 4 (M): carburante imbarcazioni -> 4530/4531; "
            "lubrificanti/oli -> 4003; materiale consumo bordo -> 4004. "
            "COSTI INDIRETTI classe 6: "
            "manutenzione/revisioni imbarcazioni -> 6200; assicurazioni nautiche -> 6300; "
            "tasse porto/ormeggio -> 6361; affitto ormeggi -> 6000; "
            "materiale ufficio -> 6500; spese bancarie -> 6940. "
            "INVESTIMENTI (I): acquisto/leasing imbarcazioni -> 1500/1537; "
            "motori e attrezzature nautiche pluriennali -> 1500."
        ),
        "conto_fornitore_default": "2000",
    },
    "Trasporti / Logistica": {
        "desc": (
            "Settore trasporti. "
            "COSTI DIRETTI classe 4 (M): carburante -> 4530/4531; pedaggi autostrada -> 4007; "
            "pneumatici e ricambi -> 4000; subappalti trasporto -> 4400; noli -> 4070. "
            "COSTI INDIRETTI classe 6: "
            "manutenzione veicoli -> 6200; assicurazione RC -> 6220/6221; "
            "tasse circolazione -> 6230; leasing veicoli -> 6260; "
            "affitto magazzino -> 6002; telefono -> 6510; spese bancarie -> 6940. "
            "INVESTIMENTI (I): acquisto veicoli/camion -> 1530; "
            "attrezzature magazzino -> 1500; software logistico -> 1741."
        ),
        "conto_fornitore_default": "2000",
    },
    "Azienda di consulenza": {
        "desc": (
            "Settore consulenza/servizi professionali. "
            "Quasi TUTTI i costi sono INDIRETTI classe 6 (M — servizi): "
            "abbonamenti SaaS/software -> 6580; licenze software annuali -> 6580; "
            "telefonia/internet -> 6510/6512; affitto ufficio -> 6004; "
            "formazione/corsi -> 5081; spese viaggio -> 5820; vitto -> 5821; alloggio -> 5822; "
            "consulenze esterne -> 6531/6532; materiale ufficio -> 6500; "
            "poste/spedizioni -> 6513; marketing/pubblicita -> 6600/6604/6610; "
            "assicurazione RC -> 6310; spese bancarie -> 6940; interessi -> 6900; "
            "tenuta contabilita -> 6530; revisione -> 6542. "
            "COSTI DIRETTI classe 4 (M): prestazioni di terzi dirette al cliente -> 4006/4060. "
            "INVESTIMENTI (I): software pluriennale > CHF 1000 -> 1741; "
            "hardware/computer -> 1521; arredamento ufficio -> 1513."
        ),
        "conto_fornitore_default": "2001",
    },
    "Azienda di architettura": {
        "desc": (
            "Settore architettura/progettazione. "
            "COSTI INDIRETTI classe 6 (M): "
            "software CAD/BIM abbonamento annuale -> 6580; telefonia -> 6510; "
            "affitto ufficio -> 6004; spese viaggio sopralluoghi -> 5820; "
            "formazione -> 5081; marketing/portfolio -> 6610/6604; "
            "stampe/plotter -> 6502; materiale ufficio -> 6500; "
            "consulenza legale -> 6532; spese bancarie -> 6940. "
            "COSTI DIRETTI classe 4 (M): materiali di prova/campioni -> 4000; "
            "prestazioni di terzi tecniche -> 4006/4060. "
            "INVESTIMENTI (I): software CAD/BIM licenza perpetua > CHF 1000 -> 1741; "
            "hardware/workstation -> 1521; arredi ufficio -> 1513."
        ),
        "conto_fornitore_default": "2001",
    },
    "Holding": {
        "desc": (
            "Holding/societa finanziaria. "
            "COSTI INDIRETTI classe 6 (M): "
            "consulenze legali/fiscali -> 6532; revisione contabile -> 6542; "
            "spese CdA -> 6540; costi assemblea -> 6541; "
            "interessi passivi -> 6900/6901; materiale ufficio -> 6500; "
            "telefono -> 6510; affitto ufficio -> 6004; spese bancarie -> 6940; "
            "tenuta contabilita -> 6530. "
            "INVESTIMENTI (I): partecipazioni -> 1480 (conto fuori classe 15xx ma investimento); "
            "hardware -> 1521; software -> 1741."
        ),
        "conto_fornitore_default": "2001",
    },
    "Organizzazione eventi": {
        "desc": (
            "Settore eventi/entertainment. "
            "COSTI DIRETTI classe 4 (M — consumo diretto per l'evento): "
            "allestimenti/scenografie -> 4000; service audio/video -> 4400; "
            "logistica evento/trasporti -> 4400/4070; catering/alimenti -> 4000; "
            "artisti/performer/animatori -> 4400; materiale consumo evento -> 4004. "
            "COSTI INDIRETTI classe 6: "
            "marketing evento -> 6600/6610/6604; affitto spazi -> 6000/6003; "
            "noleggio attrezzature -> 6264; assicurazione eventi -> 6320; "
            "telefono -> 6510; materiale ufficio -> 6500; spese bancarie -> 6940. "
            "INVESTIMENTI (I): attrezzature audio/video proprie -> 1500; "
            "veicoli -> 1530; software gestione eventi -> 1741."
        ),
        "conto_fornitore_default": "2000",
    },
    "Estetista": {
        "desc": (
            "Settore estetica/beauty. "
            "COSTI DIRETTI classe 4 (M — usati nel servizio): "
            "prodotti estetici, cosmetici, cerette, smalti, creme -> 4000; "
            "materiale monouso (guanti, salviette, cotton fioc) -> 4004. "
            "COSTI INDIRETTI classe 6: "
            "affitto locali -> 6003/6004; elettricita -> 6400; telefono -> 6510; "
            "pubblicita -> 6600/6604; materiale ufficio -> 6500; "
            "assicurazione RC -> 6310; spese bancarie -> 6940; "
            "manutenzione attrezzature -> 6100. "
            "INVESTIMENTI (I): "
            "lampade UV, macchinari estetici, lettini professionali -> 1500; "
            "arredamento -> 1510; software gestione appuntamenti -> 1741."
        ),
        "conto_fornitore_default": "2000",
    },
    "Parrucchiere": {
        "desc": (
            "Settore acconciatura. "
            "COSTI DIRETTI classe 4 (M — usati nel servizio): "
            "prodotti capelli, tinture, shampoo professionale, balsami, "
            "lacche, decoloranti -> 4000; materiale monouso -> 4004. "
            "COSTI INDIRETTI classe 6: "
            "affitto locali -> 6003/6004; elettricita -> 6400; telefono -> 6510; "
            "pubblicita -> 6600/6604; materiale ufficio -> 6500; "
            "assicurazione RC -> 6310; spese bancarie -> 6940. "
            "INVESTIMENTI (I): "
            "phon industriali, poltrone, lavatesta, sterilizzatori -> 1500/1510; "
            "arredamento salone -> 1510; software cassa -> 1741."
        ),
        "conto_fornitore_default": "2000",
    },
    "Chiosco": {
        "desc": (
            "Settore chiosco/kiosk. "
            "COSTI DIRETTI classe 4 (M — merci da rivendere): "
            "giornali/riviste -> 4200; tabacchi/sigarette -> 4200; "
            "bevande/snack -> 4200; biglietti/gratta e vinci -> 4200; "
            "materiale imballaggio -> 4205. "
            "COSTI INDIRETTI classe 6: "
            "affitto area/box -> 6000; elettricita -> 6400; telefono -> 6510; "
            "assicurazione -> 6300; spese bancarie -> 6940. "
            "INVESTIMENTI (I): box/chiosco fisso -> 1570; cassa automatica -> 1500."
        ),
        "conto_fornitore_default": "2000",
    },
    "Servizi Generali": {
        "desc": (
            "Settore generico. "
            "REGOLA PRINCIPALE: analizza le RIGHE DI DETTAGLIO della fattura per capire "
            "esattamente cosa viene acquistato. "
            "COSTI DIRETTI classe 4 (M): beni destinati alla rivendita o al consumo immediato "
            "nel ciclo produttivo (materie prime, merci, materiale consumo). "
            "COSTI INDIRETTI classe 6 (M o I): tutti gli altri costi operativi. "
            "INVESTIMENTI classe 15xx-17xx (I): beni durevoli pluriennali > CHF 1000. "
            "Se non riesci a determinare la natura del costo: usa 4000 e segnala con "
            "fornitore_sconosciuto=true nel JSON."
        ),
        "conto_fornitore_default": "2000",
    },
}

# ==============================================================================
# CODICI IVA — REGOLE COMPLETE
# ==============================================================================

CODICI_IVA = """
═══ ACQUISTI — METODO EFFETTIVO ═══
MERCI (M) = beni/servizi destinati alla rivendita o consumo immediato nel ciclo produttivo:
  M81 = IVA 8.1% merci/servizi (fatture dal 01.01.2024)
  M77 = IVA 7.7% merci/servizi (fatture fino al 31.12.2023)
  M26 = IVA 2.6% ridotta merci/servizi (dal 01.01.2024) — alimenti, libri, giornali, farmaci
  M25 = IVA 2.5% ridotta merci/servizi (fino al 31.12.2023)

INVESTIMENTI (I) = beni durevoli pluriennali destinati all'uso interno > CHF 1000:
  I81 = IVA 8.1% investimenti (dal 01.01.2024)
  I77 = IVA 7.7% investimenti (fino al 31.12.2023)
  I26 = IVA 2.6% ridotta investimenti (dal 01.01.2024)
  I25 = IVA 2.5% ridotta investimenti (fino al 31.12.2023)

REGOLA ANNO ALIQUOTA:
  Fattura con data >= 01.01.2024 -> usa 8.1% o 2.6%
  Fattura con data <= 31.12.2023 -> usa 7.7% o 2.5%

REGOLA M vs I (CRITICA — basata sulla rivendibilita'):
  M = il bene PUO' essere rivenduto tal quale o e' consumato nel servizio/produzione:
      materie prime, alimenti, bevande, cosmetici usati, carburante, merci rivendita,
      servizi ricorrenti (affitto, telefonia, energia, consulenze, abbonamenti SaaS),
      materiale consumo, pubblicita, pulizie. CONTO DARE classe 4 -> SEMPRE M.
  I = il bene NON puo' essere rivenduto, uso interno durevole pluriennale:
      macchinari, veicoli aziendali, arredamento, computer, impianti, software perpetuo,
      attrezzature professionali, manutenzioni, prestazioni di servizi. CONTO DARE classe 15xx-17xx -> SEMPRE I.
  REGOLA PRATICA: "Questo bene potrei rivenderlo tal quale?" -> SI=M, NO=I
  ESEMPI CONCRETI:
    farina/ingredienti ristorante = M (consumo diretto)
    forno professionale = I (pluriennale, non rivendibile)
    cosmetici usati nel servizio = M (consumo nel servizio)
    poltrona estetista = I (pluriennale)
    abbonamento SaaS annuale = M (servizio ricorrente)
    licenza software perpetua = I (bene durevole)
    carburante = M (consumo immediato)
    veicolo aziendale acquistato = I (pluriennale)
    totem/insegna pubblicitaria FISICA = I (bene fisico durevole, usa 6611 in dare)
    volantini/stampati pubblicitari = M (consumo immediato)
    affitto locali = M (servizio ricorrente)
    macchinario produzione = I

═══ ACQUISTI — ALIQUOTA A SALDO ═══
  "" = SEMPRE VUOTO — i costi con metodo saldo non hanno codice IVA da registrare

═══ RICAVI — METODO EFFETTIVO ═══
  V81 = ricavi IVA 8.1% (dal 01.01.2024)
  V77 = ricavi IVA 7.7% (fino al 31.12.2023)
  V26 = ricavi IVA 2.6% ridotta (dal 01.01.2024)
  V25 = ricavi IVA 2.5% ridotta (fino al 31.12.2023)

═══ RICAVI — ALIQUOTA A SALDO ═══
  F1 = codice saldo F1 (aliquota configurata nella sidebar)
  F2 = codice saldo F2 (aliquota configurata nella sidebar)

═══ CASI IVA VUOTA (lascia codice_iva = "") ═══
  - IVA esente / fuori campo / 0%:
    IT: "Esente", "Esente IVA", "Fuori campo IVA", "Non soggetto IVA", "0%", "E", "Escluso"
    DE: "Steuerfrei", "Befreit", "0% MwSt", "ohne MwSt", "E", "nicht steuerbar"
    FR: "Exonere", "TVA 0%", "Hors TVA", "E", "non assujetti"
    EN: "VAT exempt", "Zero rated", "0% VAT", "Outside scope", "E", "exempt"
  - IVA straniera (IT 22%, DE 19%, FR 20%, UK 20% ecc.) -> lascia vuoto
  - Acquisti con metodo saldo -> lascia SEMPRE vuoto
  - Nessuna IVA visibile in fattura -> lascia vuoto
"""

# ==============================================================================
# HELPERS
# ==============================================================================

def _normalizza_stringa(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r'\b(sagl|sa|ag|gmbh|srl|spa|snc|sas|inc|ltd|llc|bv|nv|oy|ab)\b', '', s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalizza_partitario(stringa_raw: str) -> str:
    if not stringa_raw or stringa_raw in ("Nessun partitario.", ""):
        return "Nessun partitario disponibile."
    cleaned = re.sub(r"[ \t]+", " ", stringa_raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return cleaned.strip()


def _sanifica_nome_file(nome: str) -> str:
    nome = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", nome)
    nome = re.sub(r"\s+", "_", nome)
    nome = nome.strip("._")
    return nome if nome.endswith(".pdf") else nome + ".pdf"


def _aggiungi_riga_errore(lista, indici_errore, contatore, nome_file, messaggio):
    logger.error("RIGA ERRORE [%s]: %s", nome_file, messaggio)
    riga_err = {
        "Data":        "INSERIRE MANUALMENTE",
        "Fattura":     nome_file,
        "Descrizione": f"PDF non elaborabile: {messaggio}",
        "CtDare":      "",
        "CtAvere":     "",
        "Imp. moneta": None,
        "Moneta":      "",
        "Cambio":      None,
        "Importo CHF": None,
        "Cod. IVA":    "",
        "_flag_giallo_dare": False,
    }
    lista.append(riga_err)
    indici_errore.append(contatore)
    lista.append({col: None for col in riga_err.keys()})


# ==============================================================================
# CONVERSIONE PDF → IMMAGINI
# ==============================================================================

def _ottimizza_immagine(img: Image.Image, max_lato: int = 2000) -> Image.Image:
    w, h = img.size
    lato_max = max(w, h)
    if lato_max > max_lato:
        scala = max_lato / lato_max
        nuove_dim = (int(w * scala), int(h * scala))
        img = img.resize(nuove_dim, Image.LANCZOS)
        logger.debug("Immagine ridimensionata: %dx%d -> %dx%d", w, h, *nuove_dim)
        try:
            img = img.filter(ImageFilter.SHARPEN)
        except Exception:
            pass
    return img


def _converti_pdf_immagini(pdf_bytes: bytes, nome_file: str) -> list:
    try:
        tutte_le_pagine = convert_from_bytes(
            pdf_bytes,
            fmt="jpeg",
            dpi=250,
            grayscale=False,
        )
        n_totali = len(tutte_le_pagine)
        logger.debug("[%s] Pagine totali PDF: %d", nome_file, n_totali)

        indici_utili = list(range(min(5, n_totali)))
        if n_totali > 5 and (n_totali - 1) not in indici_utili:
            indici_utili.append(n_totali - 1)
            logger.info("[%s] PDF lungo (%d pag.) — inclusa ultima pagina %d",
                        nome_file, n_totali, n_totali)

        immagini_b64 = []
        for idx in indici_utili:
            img = tutte_le_pagine[idx]
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img = _ottimizza_immagine(img, max_lato=2000)
            try:
                img = ImageOps.autocontrast(img, cutoff=1)
            except Exception:
                pass
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88, optimize=True)
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            immagini_b64.append((idx + 1, img_b64))

        if not immagini_b64:
            raise ValueError("Nessuna immagine estratta dal PDF")

        logger.debug("[%s] Pagine inviate all'AI: %s (tot. %d KB base64)",
                     nome_file,
                     [p for p, _ in immagini_b64],
                     sum(len(b) for _, b in immagini_b64) // 1024)
        return immagini_b64

    except Exception as e:
        logger.error("[%s] Errore conversione PDF: %s", nome_file, e)
        raise


# ==============================================================================
# CHIAMATA API ASINCRONA (singola fattura)
# ==============================================================================

async def _elabora_singola_fattura(
    client_async: AsyncOpenAI,
    nome_originale: str,
    pdf_bytes: bytes,
    prompt_sistema: str,
    conto_fornitore_default: str,
) -> dict:
    logger.info(">> Inizio elaborazione: %s", nome_originale)
    t_start = datetime.now()

    try:
        immagini_b64 = _converti_pdf_immagini(pdf_bytes, nome_originale)
    except Exception as e:
        return {"nome": nome_originale, "registrazioni": None,
                "errore": f"Errore conversione PDF: {e}", "pdf_bytes": pdf_bytes}

    content_parts = [
        {
            "type": "text",
            "text": (
                f"Analizza questa fattura: {nome_originale}. "
                "Segui TUTTE le regole del prompt di sistema senza eccezioni. "
                "Rispondi SOLO con il JSON richiesto, completo e valido, nessun testo aggiuntivo."
            )
        }
    ]
    n_pagine = len(immagini_b64)
    for i, (n_pag, b64) in enumerate(immagini_b64):
        if n_pagine > 1:
            is_ultima = (i == n_pagine - 1)
            suffisso = (
                " ← ULTIMA PAGINA: qui trovi il TOTALE FATTURA definitivo "
                "e l'eventuale riepilogo IVA per aliquota. "
                "Usa SEMPRE questo totale come importo_nominale."
            ) if is_ultima else ""
            content_parts.append({
                "type": "text",
                "text": f"[Pagina {n_pag} di {n_pagine}{suffisso}]"
            })
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}
        })

    raw_json = None
    for tentativo in range(3):
        try:
            risposta = await client_async.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                max_tokens=4096,
                temperature=0,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": content_parts}
                ]
            )
            raw_json = risposta.choices[0].message.content
            json.loads(raw_json)
            logger.debug("[%s] Tentativo %d OK", nome_originale, tentativo + 1)
            break
        except json.JSONDecodeError:
            logger.warning("[%s] JSON incompleto al tentativo %d, retry...",
                           nome_originale, tentativo + 1)
            if tentativo < 2 and raw_json:
                try:
                    risposta2 = await client_async.chat.completions.create(
                        model="gpt-4o",
                        response_format={"type": "json_object"},
                        max_tokens=4096,
                        temperature=0,
                        messages=[
                            {"role": "system", "content": prompt_sistema},
                            {"role": "user", "content": content_parts},
                            {"role": "assistant", "content": raw_json},
                            {"role": "user", "content":
                             "Il JSON era incompleto. Completalo. Rispondi SOLO con JSON valido."}
                        ]
                    )
                    raw_json = risposta2.choices[0].message.content
                    json.loads(raw_json)
                    logger.info("[%s] Retry riuscito", nome_originale)
                    break
                except Exception:
                    continue
        except Exception as e:
            logger.error("[%s] Errore API tentativo %d: %s", nome_originale, tentativo + 1, e)
            if tentativo == 2:
                return {"nome": nome_originale, "registrazioni": None,
                        "errore": f"Errore API: {e}", "pdf_bytes": pdf_bytes}

    if raw_json is None:
        return {"nome": nome_originale, "registrazioni": None,
                "errore": "Nessuna risposta valida dopo 3 tentativi", "pdf_bytes": pdf_bytes}

    try:
        dati = json.loads(raw_json)
        registrazioni = dati.get("registrazioni", [])
        if not registrazioni:
            raise ValueError("Lista registrazioni vuota")
    except Exception as e:
        return {"nome": nome_originale, "registrazioni": None,
                "errore": f"JSON non valido: {e}", "pdf_bytes": pdf_bytes}

    elapsed = (datetime.now() - t_start).total_seconds()
    logger.info("<< Fine elaborazione: %s (%.1fs, %d registrazioni)",
                nome_originale, elapsed, len(registrazioni))

    return {"nome": nome_originale, "registrazioni": registrazioni,
            "errore": None, "pdf_bytes": pdf_bytes}


# ==============================================================================
# FUNZIONE PRINCIPALE
# ==============================================================================

def elabora_documenti_banana(
    file_caricati,
    api_key,
    forma_giuridica,
    tipo_flusso,
    settore,
    metodo_iva,
    mappa_aliquote_saldo,
    stringa_bilancio,
    stringa_partitario,
    nome_ricevente=""
):
    logger.info("=== AVVIO ELABORAZIONE — %d file ===", len(file_caricati))

    stringa_partitario_norm = _normalizza_partitario(stringa_partitario)
    logica = LOGICA_SETTORE.get(settore, LOGICA_SETTORE["Servizi Generali"])
    conto_fornitore_default = logica["conto_fornitore_default"]

    saldo_config = ""
    if metodo_iva == "Aliquota a Saldo" and mappa_aliquote_saldo:
        saldo_config = (
            f"F1 corrisponde all'aliquota {mappa_aliquote_saldo.get('F1', '?')}, "
            f"F2 corrisponde all'aliquota {mappa_aliquote_saldo.get('F2', '?')}."
        )

    # ── PROMPT SISTEMA ─────────────────────────────────────────────────────
    prompt_sistema = f"""Sei un revisore contabile senior certificato, specializzato in contabilita svizzera \
Swiss GAAP FER e nel software Banana Contabilita+. Hai una conoscenza eccellente della partita doppia \
e del piano dei conti svizzero. Analizzi fatture scritte in ITALIANO, TEDESCO, FRANCESE e INGLESE. \
L'OUTPUT e' SEMPRE in italiano, nel formato JSON specificato, indipendentemente dalla lingua della fattura.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTESTO MANDATO ATTIVO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Forma giuridica azienda cliente: {forma_giuridica}
Settore azienda cliente: {settore}
Flusso contabile: {tipo_flusso}
Regime IVA: {metodo_iva}{f" — {saldo_config}" if saldo_config else ""}
{f"NOME AZIENDA RICEVENTE (chi riceve le fatture, NON il fornitore): {nome_ricevente}" if nome_ricevente else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHIVI DI RICONCILIAZIONE — PRIORITA' MASSIMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PARTITARIO FORNITORI/CLIENTI:
{stringa_partitario_norm}

ISTRUZIONI PARTITARIO:
- Confronta il nome del fornitore trovato in fattura con tutti i nomi nel partitario.
- Usa logica fuzzy: ignora differenze di forma giuridica (SA/Sagl/AG/GmbH/Srl/SpA),
  maiuscole, accenti, punteggiatura, abbreviazioni.
- Se trovi corrispondenza (anche parziale sul nome principale): usa il codice conto del
  partitario come CtAvere per acquisti o CtDare per vendite.
- Se NON trovi corrispondenza: usa {conto_fornitore_default} per acquisti, 1100 per vendite.
- IMPORTANTE: cerca la corrispondenza ANCHE se il partitario non ha la forma giuridica
  (es. "Migros" nel partitario corrisponde a "Migros SA" in fattura).

BILANCIO/CONTO ECONOMICO ANNO PRECEDENTE:
{stringa_bilancio}
ISTRUZIONI BILANCIO: mantieni coerenza con i conti gia' usati per voci simili.
Il bilancio e' la fonte piu' affidabile per la scelta del conto dare.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PIANO DEI CONTI SWISS GAAP FER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{PIANO_CONTI_COMPLETO}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOGICA SETTORE: {settore.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{logica["desc"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CODICI IVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{CODICI_IVA}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGOLE ESTRAZIONE — SEGUI NELL'ORDINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▌REGOLA 1 — DATA FATTURA
Output OBBLIGATORIO formato: GG.MM.AAAA
Cerca in tutte le lingue:
  IT: "Data fattura", "Data", "del", "In data"
  DE: "Datum", "Rechnungsdatum", "vom", "Ausstellungsdatum"
  FR: "Date", "Date de facture", "du", "Etablie le"
  EN: "Date", "Invoice date", "Dated", "Issued on"
Converti QUALSIASI formato:
  "25 Marzo 2021" -> "25.03.2021"
  "2023-02-06" -> "06.02.2023"
  "06/02/23" -> "06.02.2023"
  "6. Februar 2023" -> "06.02.2023"
  "6 fevrier 2023" -> "06.02.2023"

▌REGOLA 2 — NUMERO FATTURA
Cerca in tutte le lingue:
  IT: "Fattura N.", "No. fattura", "Numero fattura", "Rif.", "Documento N.", "N.ro", "Nr."
  DE: "Rechnung Nr.", "Rechnungsnummer", "Belegnummer", "Ref.", "Rech. Nr."
  FR: "Facture N.", "N de facture", "Reference", "No facture"
  EN: "Invoice No.", "Invoice #", "Invoice Number", "Ref.", "Document No."
REGOLA CRITICA: preserva ESATTAMENTE il formato originale inclusi apostrofi, slash,
  trattini, spazi, zeri iniziali.
  Esempi: "52'960'589", "2022/4969", "185-2023-01", "000107", "INV-2024-0042"
Se non trovato: "N/D"

▌REGOLA 3 — NOME FORNITORE (CHI EMETTE LA FATTURA)
ATTENZIONE: il FORNITORE emette la fattura, il RICEVENTE la riceve.
{f"Il RICEVENTE e' {nome_ricevente} — questo nome NON e' mai il fornitore." if nome_ricevente else ""}
Procedura di ricerca (nell'ordine):
  a) Intestazione/header in CIMA alla PRIMA PAGINA: nome vicino al logo, indirizzo emittente.
  b) Testo scritto nel o sotto il LOGO (leggilo con attenzione anche se stilizzato).
  c) Sezione pagamento: "Beneficiario", "Pagabile a", "Bankverbindung", "Beneficiaire",
     "Pay to", "Intestatario conto" — l'IBAN e' intestato al fornitore.
FORMATO OUTPUT: includi SEMPRE la forma giuridica se visibile (Sagl/SA/AG/GmbH/Srl/SpA/Inc/Ltd).
Se il fornitore e' completamente illeggibile o non identificabile: usa "Fornitore Sconosciuto"
e metti fornitore_sconosciuto: true nel JSON.

▌REGOLA 4 — IMPORTO LORDO (IVA INCLUSA) — REGOLA CRITICA
Devi trovare l'importo TOTALE DA PAGARE, IVA compresa.
FATTURE MULTI-PAGINA — PROCEDURA OBBLIGATORIA:
  a) Le fatture con molti prodotti mostrano il totale SOLO nell'ULTIMA PAGINA.
     Le righe "Totale" nelle pagine intermedie sono VUOTE o parziali — IGNORALE.
  b) Vai SEMPRE all'ultima pagina (etichettata "← ULTIMA PAGINA") e cerca il totale definitivo.
  c) Se l'ultima pagina ha riepilogo compilato (es. "CHF 4'641.05" o "Totale a pagare 2'812.59")
     USA quel valore.
  d) Se anche nell'ultima pagina il totale e' vuoto: SOMMA tutte le righe prodotto
     di tutte le pagine, poi aggiungi l'IVA se separata.

Parole chiave totale (tutte le lingue):
  IT: "Totale fattura", "Totale documento", "Totale a pagare", "Da pagare",
      "Totale IVA compresa", "Importo totale", "Netto a pagare"
  DE: "Rechnungsbetrag", "Gesamtbetrag", "Zu zahlen", "Betrag inkl. MwSt",
      "Totalbetrag", "Zahlbetrag", "Total inkl. MwSt"
  FR: "Montant total TTC", "Total TTC", "Net a payer", "Montant a payer",
      "Total facture", "A payer"
  EN: "Total amount due", "Grand total", "Amount due", "Invoice total",
      "Total inc. VAT", "Balance due", "Total payable"

ACCONTI: se vedi "Acconto ricevuto"/"Anzahlung"/"Acompte"/"Deposit paid",
  usa il TOTALE LORDO ORIGINALE prima della deduzione dell'acconto.

FORMATI NUMERICI (tutti equivalenti):
  1'234.56 (CH) = 1.234,56 (IT/DE) = 1,234.56 (EN) = 1234.56 = 1234,56
  Converti SEMPRE in formato decimale con punto: 1234.56
  Arrotonda a 2 decimali. importo_nominale SEMPRE positivo (vedi Regola 7 per negativi).

▌REGOLA 5 — CONTO DARE E CONTO AVERE (PARTITA DOPPIA)

ACQUISTI (flusso costi):
  CtDare = conto del COSTO. Segui questa priorita' nell'ordine:

  PRIORITA' 1 — BILANCIO ANNO PRECEDENTE:
    Cerca il conto gia' usato per spese analoghe. E' la fonte piu' affidabile.

  PRIORITA' 2 — ANALISI CONTENUTO FATTURA IN 4 PASSI:
    PASSO 1: Leggi le RIGHE DI DETTAGLIO della fattura (descrizione prodotti/servizi).
             Non basarti solo sul nome del fornitore: lo stesso fornitore puo' vendere
             un impianto, una manutenzione, o un prodotto.
    PASSO 2: Determina la NATURA del bene/servizio:
             E' un bene rivendibile o consumato nel servizio/produzione? -> MERCE (classe 4 o 6)
             E' un bene durevole pluriennale > CHF 1000 per uso interno? -> INVESTIMENTO (classe 15xx-17xx)
    PASSO 3: Applica la LOGICA SETTORE dell'azienda RICEVENTE (descritta sopra).
    PASSO 4: Scegli il conto piu' SPECIFICO del piano dei conti.
             EVITA 6790 (altri costi generici) se esiste un conto piu' preciso.
             EVITA 4000 (acquisti generici) se il contenuto e' piu' specifico.

  SE NON RIESCI A DETERMINARE LA NATURA DEL COSTO:
    Usa 4000 come conto dare e imposta fornitore_sconosciuto: true
    (la cella CtDare verra' evidenziata in giallo nell'interfaccia)

  CtAvere = conto partitario fornitore (dal partitario) oppure {conto_fornitore_default}

RICAVI (flusso vendite):
  CtDare = 1100 oppure conto partitario cliente
  CtAvere = scegli in base al tipo di ricavo:
    3000 = ricavi lordi principali (prodotti fabbricati, vendite standard)
    3001 = vendite al dettaglio | 3002 = vendite all'ingrosso
    3200 = merci di rivendita | 3400 = prestazioni di servizi
    3680 = altri ricavi accessori

NOTE DI CREDITO / STORNI / IMPORTI NEGATIVI:
  Se il documento e' una nota di credito o il totale ha segno negativo:
  -> INVERTI CtDare e CtAvere
  -> importo_nominale rimane POSITIVO
  -> Banana non accetta importi negativi
  Parole chiave nota credito:
    IT: "Nota di credito", "Nota credito", "Accredito", "Storno", "Rimborso", "Rettifica"
    DE: "Gutschrift", "Storno", "Kreditnote", "Ruckerstattung"
    FR: "Avoir", "Note de credit", "Remboursement"
    EN: "Credit note", "Credit memo", "Refund", "Reversal"

▌REGOLA 6 — VALUTA E TASSO DI CAMBIO
  Valuta default se non specificata: CHF
  Formato: "CHF", "EUR", "USD", "GBP" (sempre maiuscolo, 3 lettere)
  Tasso CHF: sempre 1.000000
  Tasso altra valuta: inserisci il tasso ufficiale AFC del mese della fattura se lo conosci
    con certezza, altrimenti metti 0.000000 (l'operatore lo inserira' manualmente)

▌REGOLA 7 — RIGA DIFFERENZA CAMBIO (SOLO SE valuta != CHF)
  Quando la valuta e' diversa da CHF, aggiungi OBBLIGATORIAMENTE una riga aggiuntiva
  immediatamente dopo la riga principale (prima della riga vuota separatrice).
  Questa riga ha:
    data_fattura: "" (vuota)
    numero_fattura: "" (vuoto)
    fornitore_cliente: "Perdita su cambio - fattura n. [numero_fattura_riga_principale]"
    conto_dare: 6949 (perdite su cambio Swiss GAAP FER — oppure conto dal bilancio se disponibile)
    conto_avere: stesso conto_avere della riga principale
    importo_nominale: null (lascia vuoto — sara' compilato manualmente)
    valuta: "CHF"
    tasso_cambio: 1.000000
    nota_cambio: "DA COMPILARE"
    codice_iva: ""
    tipo_riga: "cambio"
    fornitore_sconosciuto: false

▌REGOLA 8 — IVA
  Segui ESATTAMENTE le regole nella sezione CODICI IVA sopra.

  DOPPIA ALIQUOTA IVA (riepilogo nell'ultima pagina):
  Se nell'ultima pagina vedi righe distinte per aliquota (es. 8.1% e 2.6%, oppure 7.7% e 2.5%,
  oppure una aliquota e "esente/E/0%"):
  -> Genera UNA RIGA PER OGNI ALIQUOTA con tipo_riga = "iva_split"
  -> Ogni riga ha: stessa data, stesso numero fattura, stesso fornitore
  -> CtDare e CtAvere POSSONO differire (beni diversi = conti diversi)
  -> importo_nominale = importo IVA INCLUSA relativo a QUELLA SPECIFICA ALIQUOTA
  -> La SOMMA degli importi_nominale deve essere uguale al totale fattura
  -> Se una delle aliquote e' "esente/E/0%": codice_iva = "" per quella riga
  
  CALCOLO IMPORTO LORDO PER ALIQUOTA — REGOLA CRITICA:
  Quando vedi una tabella riepilogo IVA con colonne "Imponibile" e "Totale IVA":
  -> importo_nominale per quella riga = Imponibile + Totale IVA di QUELLA aliquota
  -> NON usare il totale fattura come importo di una delle righe
  -> NON usare l'imponibile da solo (senza IVA)
  
  ESEMPIO CONCRETO (dalla fattura):
    Riga 1: Imponibile 4.603,91 + IVA 119,70 (aliquota 2.6%) -> importo_nominale = 4723.61, codice_iva = M26
    Riga 2: Imponibile 10,00 + IVA 0,81 (aliquota 8.1%)     -> importo_nominale = 10.81,   codice_iva = M81
    Somma = 4734.42 = Totale Fattura ✓
  
  VERIFICA OBBLIGATORIA: la somma di tutti gli importi_nominale delle righe iva_split
  deve essere UGUALE al totale fattura. Se non corrisponde, ricalcola.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT JSON — FORMATO OBBLIGATORIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rispondi SOLO con questo JSON, nessun testo prima o dopo:

{{
  "registrazioni": [
    {{
      "data_fattura": "GG.MM.AAAA",
      "numero_fattura": "codice originale esatto",
      "fornitore_cliente": "Nome Azienda Forma Giuridica",
      "conto_dare": "codice numerico",
      "conto_avere": "codice numerico",
      "importo_nominale": 0.00,
      "valuta": "CHF",
      "tasso_cambio": 1.000000,
      "nota_cambio": "OK",
      "codice_iva": "",
      "tipo_riga": "principale",
      "fornitore_sconosciuto": false,
      "descrizione_interna": "nota breve max 60 caratteri"
    }}
  ]
}}

Tipi riga validi: "principale", "cambio", "iva_split"
fornitore_sconosciuto: true SOLO quando non riesci a determinare cosa acquista l'azienda
  e usi 4000 come fallback — la cella CtDare verra' evidenziata in giallo.
importo_nominale per riga "cambio": usa il valore JSON null (non 0.00, non stringa vuota).
"""

    # ── Leggi tutti i file ────────────────────────────────────────────────
    files_data = [(f.name, f.read()) for f in file_caricati]

    # ── Elaborazione asincrona parallela ──────────────────────────────────
    async def _run_parallel():
        client_async = AsyncOpenAI(api_key=api_key)
        tasks = [
            _elabora_singola_fattura(client_async, nome, data, prompt_sistema, conto_fornitore_default)
            for nome, data in files_data
        ]
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            risultati = loop.run_until_complete(_run_parallel())
        else:
            risultati = loop.run_until_complete(_run_parallel())
    except RuntimeError:
        risultati = asyncio.run(_run_parallel())

    # ── Assembla DataFrame ────────────────────────────────────────────────
    lista_righe_finali = []
    indici_rosso        = []   # tasso cambio da verificare
    indici_verde        = []   # righe cambio
    indici_errore       = []   # errori elaborazione
    indici_giallo_dare  = []   # fornitore sconosciuto — cella CtDare gialla
    dizionario_pdf_rinominati = {}
    contatore_righe = 0

    for risultato in risultati:
        nome_originale = risultato["nome"]
        pdf_bytes_orig = risultato["pdf_bytes"]

        if risultato["errore"]:
            _aggiungi_riga_errore(lista_righe_finali, indici_errore, contatore_righe,
                                   nome_originale, risultato["errore"])
            contatore_righe += 2
            dizionario_pdf_rinominati[f"ERRORE_{nome_originale}"] = pdf_bytes_orig
            continue

        registrazioni = risultato["registrazioni"]
        fornitore_principale = ""
        num_fattura_principale = ""
        ct_avere_principale = conto_fornitore_default
        riga = None

        for i_reg, reg in enumerate(registrazioni):
            tipo_riga           = reg.get("tipo_riga", "principale")
            data_fat            = str(reg.get("data_fattura", "")).strip()
            num_fat             = str(reg.get("numero_fattura", "")).strip()
            fornitore           = str(reg.get("fornitore_cliente", "")).strip()
            ct_dare             = str(reg.get("conto_dare", "")).strip()
            ct_avere            = str(reg.get("conto_avere", conto_fornitore_default)).strip()
            cod_iva             = str(reg.get("codice_iva", "")).strip()
            valuta              = str(reg.get("valuta", "CHF")).upper().strip()
            nota_cambio         = str(reg.get("nota_cambio", "OK")).strip()
            descrizione         = str(reg.get("descrizione_interna", "")).strip()
            flag_sconosciuto    = bool(reg.get("fornitore_sconosciuto", False))

            # Importo: per riga cambio puo' essere null
            importo_raw = reg.get("importo_nominale", None)
            if tipo_riga == "cambio":
                importo_nom = None
                importo_chf = None
            else:
                try:
                    importo_nom = round(float(importo_raw), 2) if importo_raw is not None else 0.0
                except (ValueError, TypeError):
                    importo_nom = 0.0

                # Importo negativo: inverti dare/avere
                if importo_nom < 0:
                    importo_nom = abs(importo_nom)
                    ct_dare, ct_avere = ct_avere, ct_dare
                    logger.warning("[%s] Importo negativo — invertiti CtDare/CtAvere", nome_originale)

                try:
                    tasso = round(float(reg.get("tasso_cambio", 1.0)), 6)
                except (ValueError, TypeError):
                    tasso = 1.0

                importo_chf = round(importo_nom * tasso, 2) if tasso > 0 else None

                if importo_nom > 500000:
                    logger.warning("[%s] Importo molto elevato: %.2f — verificare", nome_originale, importo_nom)
                elif importo_nom < 0.01 and tipo_riga == "principale":
                    logger.warning("[%s] Importo quasi zero: %.4f — possibile errore", nome_originale, importo_nom)

            # Tasso per riga cambio
            try:
                tasso = round(float(reg.get("tasso_cambio", 1.0)), 6)
            except (ValueError, TypeError):
                tasso = 1.0

            # Traccia fornitore e numero fattura principale
            if tipo_riga in ("principale", "iva_split") and i_reg == 0:
                fornitore_principale = fornitore
                num_fattura_principale = num_fat
                ct_avere_principale = ct_avere
            elif tipo_riga == "principale":
                fornitore_principale = fornitore
                num_fattura_principale = num_fat
                ct_avere_principale = ct_avere

            # Descrizione riga cambio: costruita in Python per sicurezza
            if tipo_riga == "cambio":
                descrizione_finale = f"Perdita su cambio - fattura n. {num_fattura_principale}"
            elif descrizione:
                descrizione_finale = f"{fornitore} - {descrizione}"
            else:
                descrizione_finale = fornitore

            riga = {
                "Data":        data_fat,
                "Fattura":     num_fat,
                "Descrizione": descrizione_finale,
                "CtDare":      ct_dare,
                "CtAvere":     ct_avere,
                "Imp. moneta": importo_nom if tipo_riga != "cambio" else None,
                "Moneta":      valuta,
                "Cambio":      tasso,
                "Importo CHF": importo_chf if tipo_riga != "cambio" else None,
                "Cod. IVA":    cod_iva,
                "_flag_giallo_dare": flag_sconosciuto,
            }
            lista_righe_finali.append(riga)

            # Indici colorazione
            if nota_cambio in ("TASSO DA VERIFICARE", "DA COMPILARE") and tipo_riga != "cambio":
                indici_rosso.append(contatore_righe)
            if tipo_riga == "cambio":
                indici_verde.append(contatore_righe)
            if flag_sconosciuto:
                indici_giallo_dare.append(contatore_righe)
                logger.warning("[%s] Fornitore sconosciuto — CtDare=4000 evidenziato", nome_originale)

            contatore_righe += 1

        # Riga vuota separatrice
        if riga:
            lista_righe_finali.append({col: None for col in riga.keys()})
            contatore_righe += 1

        # Rinomina PDF
        nome_pdf = _sanifica_nome_file(f"{fornitore_principale}_{num_fattura_principale}.pdf")
        if nome_pdf in dizionario_pdf_rinominati:
            base = nome_pdf[:-4]
            cnt = 2
            while f"{base}_{cnt}.pdf" in dizionario_pdf_rinominati:
                cnt += 1
            nome_pdf = f"{base}_{cnt}.pdf"
        dizionario_pdf_rinominati[nome_pdf] = pdf_bytes_orig
        logger.info("PDF rinominato: %s -> %s", nome_originale, nome_pdf)

    logger.info("=== ELABORAZIONE COMPLETATA — %d righe, %d errori, %d gialli ===",
                len(lista_righe_finali), len(indici_errore), len(indici_giallo_dare))

    if not lista_righe_finali:
        df_vuoto = pd.DataFrame(columns=[
            "Data", "Fattura", "Descrizione", "CtDare", "CtAvere",
            "Imp. moneta", "Moneta", "Cambio", "Importo CHF", "Cod. IVA", "_flag_giallo_dare"
        ])
        return df_vuoto, indici_rosso, indici_verde, indici_errore, indici_giallo_dare, dizionario_pdf_rinominati

    return (
        pd.DataFrame(lista_righe_finali),
        indici_rosso,
        indici_verde,
        indici_errore,
        indici_giallo_dare,
        dizionario_pdf_rinominati,
    )


# ==============================================================================
# FORMATTAZIONE IMPORTI PER EXPORT
# ==============================================================================

_COLONNE_IMPORTO = ["Imp. moneta", "Importo CHF"]
_COLONNE_TASSO   = ["Cambio"]


def formatta_df_per_export(df: pd.DataFrame, destinazione: str) -> pd.DataFrame:
    if destinazione not in ("banana", "excel"):
        raise ValueError("destinazione deve essere 'banana' oppure 'excel'")

    sep = "." if destinazione == "banana" else ","
    # Rimuovi colonna interna prima dell'export
    df_out = df.drop(columns=["_flag_giallo_dare"], errors="ignore").copy()
    
    # Ordinamento cronologico per data (righe vuote e cambio vanno in fondo)
    try:
        df_out["_data_sort"] = pd.to_datetime(
            df_out["Data"], format="%d.%m.%Y", errors="coerce"
        )
        df_out = df_out.sort_values("_data_sort", na_position="last").drop(columns=["_data_sort"])
        df_out = df_out.reset_index(drop=True)
    except Exception:
        pass

    def _fmt(valore, decimali: int) -> object:
        if valore is None:
            return None
        try:
            f = float(valore)
        except (TypeError, ValueError):
            return valore
        if pd.isna(f):
            return None
        s = f"{f:.{decimali}f}"
        if sep == ",":
            s = s.replace(".", ",")
        return s

    for col in _COLONNE_IMPORTO:
        if col in df_out.columns:
            df_out[col] = df_out[col].apply(lambda v: _fmt(v, 2))

    for col in _COLONNE_TASSO:
        if col in df_out.columns:
            df_out[col] = df_out[col].apply(lambda v: _fmt(v, 6))

    return df_out


def esporta_per_banana(df: pd.DataFrame) -> bytes:
    df_fmt = formatta_df_per_export(df, "banana")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_fmt.to_excel(writer, index=False, sheet_name="Registrazioni")
        ws = writer.sheets["Registrazioni"]
        col_idx = {c: i + 1 for i, c in enumerate(df_fmt.columns)}
        for col in _COLONNE_IMPORTO + _COLONNE_TASSO:
            if col in col_idx:
                for row in ws.iter_rows(min_row=2, min_col=col_idx[col], max_col=col_idx[col]):
                    for cell in row:
                        if cell.value is not None:
                            cell.number_format = "@"
    buf.seek(0)
    return buf.getvalue()


def esporta_per_excel(df: pd.DataFrame) -> bytes:
    df_fmt = formatta_df_per_export(df, "excel")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_fmt.to_excel(writer, index=False, sheet_name="Registrazioni")
        ws = writer.sheets["Registrazioni"]
        col_idx = {c: i + 1 for i, c in enumerate(df_fmt.columns)}
        for col in _COLONNE_IMPORTO + _COLONNE_TASSO:
            if col in col_idx:
                for row in ws.iter_rows(min_row=2, min_col=col_idx[col], max_col=col_idx[col]):
                    for cell in row:
                        if cell.value is not None:
                            cell.number_format = "@"
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# ZIP
# ==============================================================================

def genera_archivio_zip(dizionario_pdf: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, contenuto in dizionario_pdf.items():
            zf.writestr(nome, contenuto)
    buf.seek(0)
    return buf.getvalue()