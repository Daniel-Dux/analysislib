# Troubleshooting: Image Loading Issues

## Problem: "Could not load signal image"

Wenn Sie die Fehlermeldung erhalten, dass Bilder nicht gefunden werden können, führt das Script jetzt automatisch folgende Schritte durch:

### Automatische Label-Erkennung

Das Script verwendet jetzt `run.get_all_image_labels()`, um automatisch alle verfügbaren Bildorientierungen und Labels zu finden:

1. **Schritt 1**: Ruft `get_all_image_labels()` auf
   ```
   Available image labels for 'MOT_Counting':
     Orientation 'PoC6': ['signal', 'atoms', 'MOT_Counting']
   ```

2. **Schritt 2**: Probiert alle gefundenen Kombinationen aus
   ```
   Trying: orientation='PoC6', label='signal'
   ✓ Successfully loaded image!
   ```

3. **Schritt 3**: Falls nicht erfolgreich, probiert häufige Standard-Kombinationen

### Gespeicherte Informationen

Nach erfolgreicher Bildladung werden folgende Informationen gespeichert:

**In den Ergebnissen:**
- `MOT_Counting_orientation`: Die verwendete Orientation (z.B. 'PoC6')
- `MOT_Counting_label`: Das verwendete Label (z.B. 'signal')

**In den Metadaten des Hintergrundbilds:**
```json
{
  "camera_name": "MOT_Counting",
  "orientation": "PoC6",
  "label": "signal",
  "shape": [1024, 1280],
  "mean": 150.5,
  "std": 25.3
}
```

### Häufige Fälle

#### Fall 1: Orientation ist 'PoC6', Kameraname ist 'MOT_Counting'

```python
# Im Experiment-Script:
MOT_Counting.expose(
    t=5.0,
    name='signal',           # Dies ist das Label
    trigger_duration=100e-3
)

# Das Script findet automatisch:
# - Camera: 'MOT_Counting'
# - Orientation: 'PoC6' (wird automatisch erkannt)
# - Label: 'signal'
```

#### Fall 2: Label ist identisch mit Orientation

Manchmal ist das Label identisch mit der Orientation:

```python
# Im Experiment-Script:
MOT_Counting.expose(
    t=5.0,
    name='MOT_Counting',     # Label = 'MOT_Counting'
    trigger_duration=100e-3
)

# Das Script probiert automatisch:
# - orientation='PoC6', label='MOT_Counting'
# - orientation='MOT_Counting', label='MOT_Counting'
# - Weitere Kombinationen...
```

### Manuelles Debugging

Falls das automatische Finden nicht funktioniert, können Sie manuell prüfen:

#### Option 1: In Python (lyse)
```python
import lyse
run = lyse.Run(h5_path)

# Alle verfügbaren Labels anzeigen
labels = run.get_all_image_labels('MOT_Counting')
print(labels)
# Ausgabe: {'PoC6': ['signal', 'atoms'], 'MOT_Counting': ['image1']}

# Bestimmtes Bild laden
image = run.get_images('MOT_Counting', 'PoC6', 'signal')[0]
```

#### Option 2: HDF5-Datei direkt öffnen
```python
import h5py

with h5py.File('shot_file.h5', 'r') as f:
    # Zeige Struktur
    print(f['images']['MOT_Counting'].keys())
    # Ausgabe: ['PoC6', 'orientation2', ...]
    
    # Zeige Labels für eine Orientation
    print(f['images']['MOT_Counting']['PoC6'].keys())
    # Ausgabe: ['signal', 'atoms', ...]
```

### Fehlerausgabe

Wenn das Script keine Bilder findet, zeigt es jetzt:

```
ERROR: Could not load signal image
============================================================
Camera name: 'MOT_Counting'

Available orientations and labels:
  'PoC6': ['signal', 'atoms', 'background']
  'MOT_Counting': ['image1']

Please check:
1. Camera name is correct in the script
2. Images were actually taken during the experiment
3. The orientation name in camera.expose() matches
============================================================
```

### Lösungen für häufige Probleme

#### Problem: "No images found"
- **Ursache**: Keine Bilder im HDF5-File
- **Lösung**: Überprüfen Sie, dass `camera.expose()` im Experiment aufgerufen wurde

#### Problem: "Wrong orientation"
- **Ursache**: Die Orientation stimmt nicht überein
- **Lösung**: Das Script findet jetzt automatisch die richtige Orientation

#### Problem: "Wrong label"
- **Ursache**: Das Label in `name=` stimmt nicht überein
- **Lösung**: Das Script probiert automatisch häufige Labels aus

#### Problem: Kameraname falsch
- **Ursache**: `camera_name` im Script stimmt nicht mit dem tatsächlichen Kameranamen überein
- **Lösung**: 
  ```python
  # Im fluo_background_analysis.py ändern:
  camera_name = 'MOT_Counting'  # Muss exakt mit Kameraname übereinstimmen
  ```

### Best Practices

1. **Konsistente Namensgebung**: Verwenden Sie immer dieselben Namen für:
   - Kameraname im Connection Table
   - Label in `camera.expose(name=...)`

2. **Standard-Labels**: Bleiben Sie bei Standard-Labels wie:
   - `'signal'` für Bilder mit Signal
   - `'background'` für Hintergrundbilder
   - `'atoms'` für Atombilder

3. **Testen**: Nach Änderungen am Setup:
   ```python
   # Im Script:
   debug = True  # Aktiviert detaillierte Ausgaben
   ```

4. **Metadaten prüfen**: Nach dem Aufnehmen eines Hintergrundbilds:
   ```bash
   cat analysislib/.../background_images/MOT_Counting_background.json
   ```
   Zeigt die verwendete Orientation und das Label.

### Beispiel: Vollständiger Workflow

```python
# 1. Experiment-Script (hqa_sequence.py oder ähnlich)
from labscript import *

# Camera ist definiert als:
IMAQdxCamera("MOT_Counting", parent_device=..., connection=...)

# Während des Experiments:
MOT_Counting.expose(
    t=5.0,
    name='signal',           # Dieses Label wird verwendet
    trigger_duration=100e-3
)

# 2. Analyse-Script (fluo_background_analysis.py)
camera_name = 'MOT_Counting'  # MUSS exakt übereinstimmen

# 3. Das Script findet automatisch:
#    - Camera: 'MOT_Counting'
#    - Orientation: 'PoC6' (wird automatisch erkannt)
#    - Label: 'signal' (wird automatisch erkannt)

# 4. Überprüfung in lyse:
print(data['MOT_Counting_orientation'])  # Ausgabe: 'PoC6'
print(data['MOT_Counting_label'])        # Ausgabe: 'signal'
```

### Zusammenfassung

Das aktualisierte Script ist **viel robuster** und findet automatisch:
✅ Die richtige Orientation  
✅ Das richtige Label  
✅ Probiert alle verfügbaren Kombinationen aus  
✅ Zeigt detaillierte Fehlermeldungen mit verfügbaren Optionen  
✅ Speichert die verwendeten Werte für zukünftige Referenz  

Falls Sie weiterhin Probleme haben, aktivieren Sie `debug=True` und prüfen Sie die Konsolenausgabe für detaillierte Informationen.
