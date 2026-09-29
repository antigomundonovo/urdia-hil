# DOCUMENTO 13 — CONTENT + RENDERING ENGINE

## Architecture
```text
Canonical Content
→ Format Plan
→ Platform Input
→ Renderer
→ QC
→ Export
```

## Formats
```text
PHOTO POST
CAROUSEL
MICROLOOP
```

## ANM visual defaults
Image-first, pouco texto na arte, imagem forte e legenda complementar. Exceções para conteúdo documental, quiz e documentos que exigem leitura.

## Carousel structure
```text
HOOK
ORIENTATION
EVIDENCE
CONTEXT
DISCOVERY
MEANING
SOURCE / QUESTION
```

## Microloop
Imagem + texto + movimento mínimo opcional + áudio opcional.

Duração: 5–12s conforme reading time, visual comprehension e transition time.

## Render tech
```text
Pillow
SVG
HTML/CSS
Playwright
FFmpeg
```

## Determinism
Registrar template version, renderer version, font version, asset versions e content version.

## Font handling
Usar somente fontes cuja licença/redistribuição é conhecida no projeto.

## Image transforms
Registrar crop, resize, restoration, colorization, tool e version.

## Security
FFmpeg e ferramentas externas recebem argumentos estruturados; não shell concatenado com input externo.

## QC
```text
resolution
dimensions
aspect ratio
font rendering
overflow
contrast
missing assets
audio duration
file integrity
```

## Export
```text
post-YYYY-MM-DD-ID/
├── image/
├── carousel/
├── microloop/
├── captions/
├── platform_variants/
├── hashtags/
├── seo/
├── sources/
├── rights/
└── manifest.json
```

## No long-video pipeline
Não incluir voice-over, scene generation, complex timelines ou vídeo narrado na V1.
