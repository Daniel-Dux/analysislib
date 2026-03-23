# Quick Start: Fluoreszenz-Analyse mit persistentem Hintergrundbild

## Konzept

Das System verwendet **ein persistentes Hintergrundbild**, das auf der Festplatte gespeichert wird:
- ✅ Nur **1 Bild pro Shot** → schnellere Experimente
- ✅ **Hintergrundbild wird wiederverwendet** → keine wiederholte Aufnahme nötig
- ✅ **Einfache Aktualisierung** über einen Parameter

## Schnellstart in 4 Schritten

### Schritt 1: Hintergrundbild aufnehmen (einmalig)

**Im Experiment-Script:**
```python
record_background = True  # Wichtig!
camera_name = 'MOT_Counting'

# Nehmen Sie ein Bild OHNE Atome auf
MOT_Counting.expose(t=5.0, name='signal', trigger_duration=100e-3)
```

**Führen Sie den Shot aus** → Das Bild wird als Hintergrundbild gespeichert

### Schritt 2: Parameter zurücksetzen

**Im Experiment-Script:**
```python
record_background = False  # Oder auskommentieren
```

### Schritt 3: Normale Messungen

**Im Experiment-Script:**
```python
# Nehmen Sie ein Bild MIT Atomen auf
MOT_Counting.expose(t=5.0, name='signal', trigger_duration=100e-3)
```

**Führen Sie Shots aus** → Das gespeicherte Hintergrundbild wird automatisch verwendet

### Schritt 4: Ergebnisse verwenden

**In lyse/Analysis Plot Panel:**
```python
signal = data['MOT_Counting_signal_sum']
uncertainty = data['MOT_Counting_signal_uncertainty']
weight_factor = data['MOT_Counting_bg_weight_factor']
```

## Wo wird das Hintergrundbild gespeichert?

```
analysislib/HQA/analysis_plot_panel/src/analysis_scipts/background_images/
└── MOT_Counting_background.npy
└── MOT_Counting_background.json  (Metadaten)
```

## ROI Konfiguration

### Option 1: Im Script (Standard)
```python
# In fluo_background_analysis.py
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

### Option 2: In run_globals (empfohlen)
```python
# Im Experiment-Script oder Connection Table
fluo_signal_roi_center = [300, 300]
fluo_signal_roi_size = [100, 100]
fluo_bg_roi_center = [100, 100]
fluo_bg_roi_size = [50, 50]
```

## Wann neues Hintergrundbild aufnehmen?

Nehmen Sie ein neues Hintergrundbild auf, wenn:
- ⚠️ Beleuchtungsintensität geändert
- ⚠️ Kameraeinstellungen geändert (Exposure, Gain)
- ⚠️ Optische Ausrichtung verändert
- ⚠️ Hintergrund über Zeit gedriftet

**Prozess:**
1. Setzen Sie `record_background=True`
2. Nehmen Sie einen Shot **ohne Atome** auf
3. Setzen Sie `record_background=False`
4. Weiter mit normalen Messungen

## Debugging

### Debug-Modus aktivieren
```python
# In fluo_background_analysis.py
debug = True
```

Dies zeigt:
- Raw Signal-Bild mit ROIs
- Verwendetes Hintergrundbild
- Gewichtetes Hintergrundbild
- Korrigiertes Bild
- 1D-Profile

### Typische Probleme

**"Background file not found"**
- → Nehmen Sie zuerst ein Hintergrundbild auf mit `record_background=True`

**"Background shape does not match"**
- → Kamera-Auflösung hat sich geändert
- → Nehmen Sie neues Hintergrundbild auf

**Gewichtungsfaktor weit von 1.0**
- Normal: 0.8 - 1.2
- Sehr abweichend (< 0.5 oder > 2.0):
  - → Hintergrundbild veraltet
  - → Nehmen Sie neues Hintergrundbild auf

## Vergleich: Alt vs. Neu

### Alt (mehrere Bilder pro Shot):
```python
# Pro Shot:
- 1× Signal-Bild (mit Atomen)
- 2-3× Hintergrund-Bilder (ohne Atome)
→ 3-4 Bilder pro Shot
→ Längere Experimente
```

### Neu (persistentes Hintergrundbild):
```python
# Pro Shot:
- 1× Signal-Bild (mit Atomen)
→ 1 Bild pro Shot
→ Schnellere Experimente

# Einmalig (bei Bedarf):
- 1× Hintergrundbild aufnehmen
→ Wird gespeichert und wiederverwendet
```

## Vorteile des neuen Systems

✅ **Schneller**: Nur 1 Bild pro Shot statt 3-4  
✅ **Einfacher**: Kein komplexes Timing für mehrere Bilder  
✅ **Konstant**: Gleiches Hintergrundbild über viele Shots  
✅ **Flexibel**: Einfache Aktualisierung bei Bedarf  
✅ **Dokumentiert**: Metadaten zeigen Herkunft des Hintergrunds  

## Workflow-Diagramm

```
Start
  │
  ├─► SETUP (einmalig)
  │   ├─ Setze record_background=True
  │   ├─ Shot ohne Atome
  │   ├─ Hintergrundbild wird gespeichert
  │   └─ Setze record_background=False
  │
  ├─► NORMALE NUTZUNG (täglich)
  │   ├─ Shots mit Atomen
  │   ├─ Hintergrundbild wird automatisch geladen
  │   └─ Analyse läuft
  │
  └─► UPDATE (bei Bedarf)
      ├─ Setze record_background=True
      ├─ Shot ohne Atome
      ├─ Neues Hintergrundbild wird gespeichert
      └─ Setze record_background=False
          └─ Zurück zu NORMALE NUTZUNG
```

## Support

Bei Problemen siehe ausführliche Dokumentation:
- `README_fluo_background_analysis.md` - Vollständige Dokumentation
- `example_fluo_experiment.py` - Beispiel Experiment-Script
- `fluo_background_analysis.py` - Das Analyse-Script mit Kommentaren
