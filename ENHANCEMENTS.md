# Caelestia laptop enhancements

This fork carries the laptop-specific integration used by the live Caelestia setup.
Generated indexes, model weights, recordings, logs and credentials are intentionally
not stored in Git.

## Spotlight search

- `Super` and `Super+Shift+Space` open the native Caelestia launcher.
- Results combine applications, folders, fuzzy filenames, indexed content and local
  semantic matches, capped at ten total results.
- Every useful path is indexed immediately by filename, including Markdown and
  source files. Top-level code projects are discovered with a one-level probe.
  Compact filename vectors are backfilled before slower content extraction/OCR.
- EmbeddingGemma INT4 generates document embeddings through OpenVINO. A reusable
  OpenCL kernel performs top-K vector scoring on Intel graphics; it exits 45 seconds
  after the last query.
- Text/OCR embedding and SigLIP2 visual labelling run only on AC in bounded jobs.
- In Ultra Power Saver, search remains available but automatically uses lexical
  filename/content search without loading either ML model.
- Nautilus exposes `Search with Caelestia Spotlight` in its context menu.

Local model locations:

- `~/ML/models/embeddinggemma-300m-int4-ov`
- `~/ML/models/siglip2-base-int8-onnx`

The index is stored under `~/.local/share/caelestia-search` and may be deleted and
rebuilt without affecting personal files.

## Ultra Power Saver

`Alt+U` toggles the mode. It records the previous profile and brightness, switches
to power-saver, caps Intel P-state performance at 45%, disables turbo and temporarily
disables Hyprland blur/animations. Semantic/visual indexing, cache maintenance and
nonessential listeners are stopped. PipeWire, WirePlumber, Bluetooth, Chrome and
video players are intentionally left alone. Exiting restores only services that
were active before entry, then reloads the normal Hyprland configuration.

The battery popout also exposes Ultra alongside the normal manual power profiles.

## Gemini voice typing

`F9` starts and stops dictation. Recording uses a short-lived ffmpeg process and a
60-second transient systemd timeout. The Gemini Python libraries load only after
recording stops; there is no permanent keyboard-listener process. Caelestia renders
listening, processing, success and error states from an event-watched JSON file.

Settings > Voice typing manages three Gemini key slots and the transcription prompt.
Keys are passed over stdin into the desktop Secret Service keyring, never placed in
JSON, process arguments or Git. A slot is selected randomly per transcription and
the remaining keys provide automatic failover. Legacy private key files remain a
compatibility fallback. The repository contains no API keys.

## Safety properties

- Index workers are AC-only, low CPU/IO weight, memory-capped and time-capped.
- Waydroid and Ultra mode prevent iGPU visual/index workloads from starting.
- Semantic confidence gating prefers an empty result over unrelated files.
- Exact and fuzzy filenames remain available before semantic backfill completes.
- Every temporary power change has an explicit restoration path.
