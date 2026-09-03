# GMV OCR — fallback PaddleOCR per PDF scansionati

Motore OCR di riserva usato da `gmv_evidence_pipeline.py` solo quando un PDF non ha
un layer di testo nativo (`pypdf` non estrae nulla) **e** non esiste già un Markdown
AnyDoc pre-generato in `10_MD_PROCESSED_FILES/`. Sui ~335 PDF già processati nel
sistema, questo riguarda una minoranza (~15) — i documenti realmente scansionati,
non i PDF già testuali.

## Perché un ambiente virtuale separato

`paddlepaddle`/`paddleocr` non hanno wheel compatibili con Python 3.14 (l'interprete
di default di questa macchina e con cui è costruito il `.venv` condiviso del repo).
Vanno installati sotto Python 3.11 in un ambiente dedicato, invocato come processo
esterno da `gmv_evidence_pipeline.py` — stesso pattern già usato per LibreOffice
nell'estrazione dei `.doc` (`shutil.which` + `subprocess.run`), non un import diretto
nel processo principale.

Installazione, un tempo solo, **mai** da eseguire in test o CI (~1GB di download,
diversi minuti, CPU-only su Apple Silicon):

```bash
/Users/giacomomarcovalerio/.local/bin/python3.11 -m venv ~/.gmv_core/.venv-paddleocr
~/.gmv_core/.venv-paddleocr/bin/python -m pip install --requirement 10_API/requirements-paddleocr.txt
```

Verifica manuale dopo l'installazione:

```bash
~/.gmv_core/.venv-paddleocr/bin/python 10_API/ocr_paddleocr_pdf.py /percorso/a/uno/scan.pdf
```
Lo stdout deve contenere solo il testo estratto (nessun banner/log del framework —
se compare rumore, la redirezione in `ocr_paddleocr_pdf.py` va rivista prima di
usare lo script in pipeline).

## Costo e limiti noti

- ~14s a pagina (modelli già caricati, pipeline OCR semplice `PaddleOCR(lang=...)`).
- `PPStructureV3` (layout + tabelle + Markdown) è stato valutato e scartato: ~155s a
  pagina su questa macchina, troppo lento per l'uso in pipeline.
- Sulla scrittura a mano l'accuratezza resta bassa, come per qualunque motore OCR
  testato finora — non è un difetto specifico di questa integrazione.

## Estrattore risultante

I record prodotti da questo fallback hanno `extractor: "pdf_text_paddleocr"`.
