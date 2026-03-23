# Fluorescence Analysis with Weighted Background Subtraction

## Overview

Das Script `fluo_background_analysis.py` führt eine Fluoreszenzanalyse mit gewichteter Hintergrundsubtraktion durch. Es ist kompatibel mit dem Analysis Plot Panel und lyse.

## Features

1. **Einzelbild pro Shot**: Lädt ein Signal-Bild pro Shot für schnelle Analyse

2. **Persistentes Hintergrundbild**: 
   - Verwendet ein gespeichertes Hintergrundbild von der Festplatte
   - Kein Bedarf für mehrere Hintergrundbilder pro Shot
   - Schnellere Experimente

3. **Hintergrundbild-Aufnahme**: 
   - Einfache Aufnahme neuer Hintergrundbilder über Parameter `record_background=True`
   - Automatisches Speichern auf Festplatte
   - Mit Metadaten (Zeitstempel, Statistiken)

4. **Gewichtete Hintergrundsubtraktion**: 
   - Berechnet die Summe in einer Hintergrund-ROI
   - Gewichtet das Hintergrundbild so, dass die Summe in der Hintergrund-ROI dem echten Bild entspricht
   - Subtrahiert das gewichtete Hintergrundbild

5. **ROI-basierte Signalextraktion**: Summiert das Signal in einer konfigurierbaren Signal-ROI

6. **Unsicherheitsabschätzung**: Berechnet Unsicherheiten basierend auf Hintergrundvariation

## Konfiguration

### ROI-Definition

Die ROIs können auf zwei Arten definiert werden:

#### 1. Direkt im Script (Standard)
```python
signal_roi = {
    'x_center': 300,
    'y_center': 300,
    'width': 100,
    'height': 100
}

background_roi = {
    'x_center': 100,
    'y_center': 100,
    'width': 50,
    'height': 50
}
```

#### 2. Über run_globals (empfohlen)
Im Connection Table oder Experiment-Script:
```python
# Signal ROI
fluo_signal_roi_center = [300, 300]  # [x, y] in Pixel
fluo_signal_roi_size = [100, 100]    # [width, height] in Pixel

# Background ROI
fluo_bg_roi_center = [100, 100]      # [x, y] in Pixel
fluo_bg_roi_size = [50, 50]          # [width, height] in Pixel
```

### Kamera-Name

Passen Sie den Kamera-Namen an:
```python
camera_name = 'Cam_fluorescence'  # Oder 'PCOedge', etc.
```

### Bild-Labels

Das Script versucht Bilder mit folgenden Labels zu laden:

**Signal-Bild:**
- Primär: `'fluorescence'`, `'signal'`
- Alternativ: `'fluorescence'`, `'atoms'`

**Hintergrund-Bilder:**
- Versucht mehrere: `'background'`, `'background2'`, `'background3'`
- Alternativ: `'no_atoms'`

Diese müssen mit Ihrem `camera.expose()` Aufruf in Ihrem Experiment-Script übereinstimmen.

## Verwendung im Experiment-Script

### Schritt 1: Hintergrundbild aufnehmen (einmalig)

Zuerst müssen Sie ein Hintergrundbild aufnehmen:

```python
from labscript import *

# ... Ihr Setup ...

# Wichtig: Setzen Sie record_background auf True
record_background = True

# Nehmen Sie ein Bild OHNE Atome auf (Hintergrundbedingungen)
# Stellen Sie sicher, dass die Beleuchtung identisch zu Ihren Signal-Aufnahmen ist
camera.expose(t='MOT_Counting', name='signal', trigger_duration=100e-3)
```

Nach dem Shot wird das Bild als Hintergrundbild gespeichert in:
`analysislib/HQA/analysis_plot_panel/src/analysis_scipts/background_images/`

### Schritt 2: Normale Messungen (Standard)

Für alle weiteren Messungen verwenden Sie:

```python
from labscript import *

# ... Ihr Setup ...

# Setzen Sie record_background auf False (oder lassen Sie es weg)
record_background = False

# Nehmen Sie ein Signal-Bild MIT Atomen auf
camera.expose(t='MOT_Counting', name='signal', trigger_duration=100e-3)
```

Das gespeicherte Hintergrundbild wird automatisch geladen und verwendet.

### Wann ein neues Hintergrundbild aufnehmen?

Nehmen Sie ein neues Hintergrundbild auf, wenn:
- Die Beleuchtungsintensität sich geändert hat
- Die Kameraeinstellungen (Exposure, Gain) verändert wurden
- Die optische Ausrichtung angepasst wurde
- Der Hintergrund über Zeit gedriftet ist
- Sie einen anderen Bereich der Kamera verwenden

## Gewichtete Hintergrundsubtraktion - Algorithmus

1. **Berechne Summe in Background-ROI:**
   - `S_signal = sum(signal_image[bg_roi])`
   - `S_background = sum(background_image[bg_roi])`

2. **Berechne Gewichtungsfaktor:**
   - `weight = S_signal / S_background`

3. **Subtrahiere gewichteten Hintergrund:**
   - `corrected_image = signal_image - weight × background_image`

4. **Extrahiere Signal:**
   - `signal = sum(corrected_image[signal_roi])`

**Vorteil:** Diese Methode kompensiert automatisch für Intensitätsschwankungen des Hintergrunds zwischen Aufnahmen.

## Gespeicherte Ergebnisse

Das Script speichert folgende Ergebnisse im HDF5-File:

### In normalem Analyse-Modus:

**Skalare Werte:**
- `{camera_name}_signal_sum`: Gesamtsignal in der Signal-ROI
- `{camera_name}_signal_uncertainty`: Geschätzte Unsicherheit
- `{camera_name}_signal_sum_smooth`: Signal im geglätteten Bild
- `{camera_name}_bg_weight_factor`: Verwendeter Gewichtungsfaktor
- `{camera_name}_signal_roi_x/y`: Position der Signal-ROI
- `{camera_name}_bg_roi_x/y`: Position der Hintergrund-ROI

**Arrays:**
- `{camera_name}_corrected_image`: Hintergrund-subtrahiertes Bild
- `{camera_name}_background_avg`: Verwendetes Hintergrundbild
- `{camera_name}_corrected_smooth`: Geglättetes korrigiertes Bild (falls aktiviert)

### Im Hintergrund-Aufnahme-Modus:

**Skalare Werte:**
- `{camera_name}_background_recorded`: True (Flag für erfolgreiche Aufnahme)
- `{camera_name}_background_mean`: Mittlerer Wert des Hintergrundbilds

## Debug-Modus

Aktivieren Sie den Debug-Modus für visuelle Kontrolle:

```python
debug = True
```

Dies zeigt:
1. Rohes Signal-Bild mit ROIs
2. Gemitteltes Hintergrundbild mit ROIs
3. Gewichtetes Hintergrundbild
4. Korrigiertes Bild
5. Geglättetes korrigiertes Bild
6. Zoom auf Signal-ROI
7. 1D-Profile durch die Signal-ROI

## Glättung

Optional können Sie Gaußsche Glättung anwenden:

```python
smooth_sigma = 2.0  # Sigma für Gaußfilter (0 = keine Glättung)
```

## Tipps

1. **Hintergrund-ROI wählen**: Wählen Sie eine Region, die repräsentativ für den Hintergrund ist, aber kein Signal enthält

2. **Hintergrundbild regelmäßig aktualisieren**: 
   - Nehmen Sie ein neues Hintergrundbild auf, wenn sich die experimentellen Bedingungen ändern
   - Ein gutes Hintergrundbild ist entscheidend für genaue Ergebnisse

3. **ROI-Größe**: Die Signal-ROI sollte groß genug sein, um das gesamte Signal zu erfassen, aber nicht unnötig groß

4. **Test mit Debug-Modus**: Verwenden Sie zunächst `debug=True`, um zu überprüfen, dass die ROIs korrekt positioniert sind

5. **Bedingungen konstant halten**: Stellen Sie sicher, dass die Beleuchtungsbedingungen zwischen Hintergrundbild und Signal-Aufnahme identisch sind

## Beispiel-Workflow

### Erstmaliges Setup:

1. Konfigurieren Sie ROIs im Script oder in run_globals
2. Nehmen Sie ein Hintergrundbild auf:
   - Setzen Sie `record_background=True` in Globals
   - Nehmen Sie ein Bild OHNE Atome auf
   - Führen Sie das Analyseskript aus (speichert Hintergrundbild)
3. Überprüfen Sie mit `debug=True`, dass alles korrekt ist

### Tägliche Nutzung:

1. Setzen Sie `record_background=False` (oder lassen Sie es weg)
2. Nehmen Sie Signal-Bilder MIT Atomen auf
3. Das Script lädt automatisch das gespeicherte Hintergrundbild
4. Verwenden Sie die gespeicherten Ergebnisse im Analysis Plot Panel

### Neues Hintergrundbild aufnehmen:

1. Setzen Sie `record_background=True`
2. Nehmen Sie ein neues Hintergrundbild auf (ohne Atome)
3. Setzen Sie `record_background=False` zurück
4. Weiter mit normaler Analyse

## Kompatibilität mit Analysis Plot Panel

Das Script ist vollständig kompatibel mit dem Analysis Plot Panel. Alle gespeicherten Ergebnisse können direkt im Panel verwendet werden:

```python
# Im Analysis Plot Panel können Sie auf die Ergebnisse zugreifen:
signal = data['{camera_name}_signal_sum']
uncertainty = data['{camera_name}_signal_uncertainty']
```

## Fehlerbehebung

**Problem: "Background file not found"**
- Sie müssen zuerst ein Hintergrundbild aufnehmen
- Setzen Sie `record_background=True` und nehmen Sie ein Bild ohne Atome auf

**Problem: "Background shape does not match signal shape"**
- Die Kamera-Auflösung oder ROI hat sich geändert
- Nehmen Sie ein neues Hintergrundbild mit den aktuellen Einstellungen auf

**Problem: "Could not load signal image"**
- Überprüfen Sie, dass `camera_name` korrekt ist
- Stellen Sie sicher, dass die Bild-Labels mit Ihrem Experiment übereinstimmen
- Standard-Label ist 'signal', alternativ 'atoms'

**Problem: "Background sum is zero"**
- Die Hintergrund-ROI enthält nur Nullen oder sehr niedrige Werte
- Verschieben Sie die Hintergrund-ROI oder passen Sie deren Größe an
- Nehmen Sie ein neues Hintergrundbild auf

**Problem: Negative Signale**
- Der Gewichtungsfaktor könnte zu hoch sein
- Überprüfen Sie die Position der Hintergrund-ROI
- Möglicherweise gibt es lokale Intensitätsvariationen
- Das Hintergrundbild ist veraltet - nehmen Sie ein neues auf

**Problem: Gewichtungsfaktor weit von 1.0 entfernt**
- Normal: 0.8 - 1.2 sind typisch
- Sehr abweichend (< 0.5 oder > 2.0): 
  - Hintergrundbild wurde unter anderen Bedingungen aufgenommen
  - Nehmen Sie ein neues Hintergrundbild auf

## Autor

Analysis Plot Panel  
Datum: 2026-02-23
