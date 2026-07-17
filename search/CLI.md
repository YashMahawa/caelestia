# Caelestia indexed search CLI

`caelestia-search` exposes the same local hybrid index used by the launcher.
It searches filenames, folders, extracted document text, PDF/image OCR and
available semantic vectors without crawling the filesystem at query time.

```sh
# Fast hybrid search, human-readable score/kind/path output
caelestia-search find "income certificate" -n 10

# `find` is optional
caelestia-search "anime subtitles"

# Structured output for AI agents and scripts
caelestia-search find "project architecture" --json -n 20

# Filename and indexed-text search without loading an ML model
caelestia-search find "README markdown" --lexical --json

# Safe path piping
caelestia-search find "vacation photo" -0 | xargs -0 -r ls -ld --

# Index health and lightweight metadata refresh
caelestia-search status
caelestia-search scan
```

Queries never recursively scan the SSD. New files under watched locations are
added by the event-driven watcher; `scan` refreshes metadata when needed.
