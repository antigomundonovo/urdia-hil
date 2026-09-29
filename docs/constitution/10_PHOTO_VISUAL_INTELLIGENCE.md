# DOCUMENTO 10 — PHOTO STORY + VISUAL INTELLIGENCE

## Pipeline
```text
import
→ file validation
→ SHA-256
→ perceptual hash
→ metadata/EXIF
→ OCR
→ vision
→ embedding
→ visual search
→ archive search
→ source matching
→ context
→ rights
→ story
```

## OCR
Extrair texto, confiança e região quando possível. OCR é evidência auxiliar.

## Vision
Pode detectar objetos, arquitetura, sinalização, uniformes, veículos e candidatos de época/local. Resultado é hipótese.

## Identity rule
Similaridade visual não prova identidade. Confirmar com provenance + contexto + metadata + evidence.

## Photo questions
```text
O que vemos?
Quando?
Onde?
Quem?
Por quê?
Quem registrou?
Contexto?
O que aconteceu antes/depois?
Que documentos existem?
O que não sabemos?
```

## Asset classes
```text
ORIGINAL_AS_RETRIEVED
CROPPED
RESTORED
UPSCALED
COLORIZED
RECONSTRUCTED
AI_GENERATED
ILLUSTRATION
UNKNOWN
```

## Transformations
Criar nova versão com parent asset, operation, parameters, tool, version, actor e timestamp.

## Restoration allowed
Denoise, contraste, upscale e restauração técnica. Não adicionar/remover elementos históricos relevantes ou fabricar detalhes sem identificação.

## Colorization
Preservar original e marcar versão colorizada.

## AI priority
```text
real historical asset
→ licensed archival material
→ illustration
→ AI
```

## Duplicate detection
Combinar file hash, perceptual hash, metadata e semantic similarity.

## Visual QC
Resolution, aspect ratio, crop, compression, text overlap, safe areas e legibilidade.

## Rights handoff
Asset sem rights válido não deve entrar em pacote publicável.

## Done
Foto → análise → candidatos de origem → provenance → rights → context → story com rastreabilidade.
