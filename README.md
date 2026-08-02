# PREVENTIVATORE.ENERGIA
PREVENTIVATORE DI RISPARMIO CALCOLATO TRAMITE CONFRONTO DI BOLLETTE CON LE OFFERTE LUCE IN VIGORE DI FASTWEB ENERGIA

## Uso

1. Installa le dipendenze:

```bash
python3 -m pip install -r requirements.txt
```

2. Esegui il preventivatore sul PDF di esempio o su un altro PDF di bolletta:

```bash
python3 preventivatore.py --input Fastweb_Vodafone_Business_Fix_Flex.pdf --output preventivo.pdf
```

3. Trova il documento generato in `preventivo.pdf`.

## File inclusi

- `preventivatore.py`: script Python per estrarre i dati dal PDF e generare il PDF di preventivo.
- `requirements.txt`: dipendenze necessarie (`pypdf`, `reportlab`).
- `Fastweb_Vodafone_Business_Fix_Flex.pdf`: esempio di bolletta da analizzare.
- `index.html`: interfaccia web statica per simulazioni rapide e caricamento PDF via browser.
