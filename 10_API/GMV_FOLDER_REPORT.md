# GMV Folder Report v0.1.1

Tool locale e read-only per inventariare una cartella, produrre un report Markdown e,
facoltativamente, confrontare i file con una cartella GMV Master tramite SHA-256.

## Uso

Solo report:

```bash
gmv folder-report "/percorso/cartella"
```

Report e confronto:

```bash
gmv folder-report "/percorso/cartella" \
  --master "/percorso/GMV_MASTER_SYSTEM" \
  --output "/percorso/report.md"
```

Il comando non segue symlink e non modifica i file sorgente o master. Scrive soltanto
il report richiesto, in modo atomico. Se un file non è leggibile o cambia durante la
scansione, il report lo dichiara in `Scan evidence`; un indice master incompleto non
produce falsi `NOT FOUND`.

L'inventario è ricorsivo: conteggio, SHA-256, duplicati, anteprime, indice riepilogativo,
dettagli e confronto con il master includono ogni file regolare nelle sottocartelle.

Le estrazioni PDF, DOCX, XLSX e immagini richiedono le dipendenze installate
nell'ambiente `.venv` del core. I file di testo e gli hash SHA-256 funzionano anche
senza dipendenze opzionali.

Per ricreare l'installazione:

```bash
.venv/bin/python -m pip install --requirement 10_API/requirements-folder-report.txt
```
