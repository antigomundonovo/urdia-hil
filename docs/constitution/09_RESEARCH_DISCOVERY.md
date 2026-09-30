# DOCUMENTO 09 — RESEARCH + DISCOVERY ENGINE

## Objetivo
Descobrir poucas oportunidades relevantes em vez de um feed infinito.

## Source adapters
```text
RSS
Atom
Sitemap
Search
GDELT
Wikidata
Wikipedia
OpenAlex
Crossref
Wayback
Internet Archive
Wikimedia
```

Implementados na V1: RSS/Atom, sitemap (URL set e índice com limites de
documentos/itens), GDELT, pesquisa da API MediaWiki, pesquisa Wikidata e
metadados acadêmicos Crossref/OpenAlex, Wayback CDX, Internet Archive e
metadados de arquivos do Wikimedia Commons. A pesquisa geral permanece
explicitamente indisponível até ter adaptador e testes próprios. Resultados
desses catálogos e índices são leads de descoberta, nunca evidência por si só;
metadados de licença do Commons também não substituem a verificação de direitos.
XML externo é rejeitado e todas as requisições usam o SafeFetcher, com validação
de redirect, tamanho, timeout, robots e limite por host.
Retrievals bem-sucedidos persistem ETag e Last-Modified; varreduras seguintes
enviam validadores condicionais e registram HTTP 304 sem reprocessar resultados.
Tipos de fonte ainda sem adaptador podem ser cadastrados, mas a API rejeita a
solicitação de varredura até que a implementação esteja disponível.

## Pipeline
```text
source config
→ fetch
→ normalize
→ deduplicate
→ entities/topics
→ candidate claims
→ cluster
→ dependency analysis
→ relevance filter
→ opportunity candidate
```

## Search is not evidence
Resultados de busca são leads. O claim precisa ser sustentado por source/evidence posteriormente.

## Fetch safety
Timeout, size limit, rate limit, cache, ETag, Last-Modified, redirect validation, robots handling.

## Extraction
Preferir structured extraction/Trafilatura. Browser only quando JS/dynamic content realmente exigir.

## Deduplication
Canonical URL + URL normalization + content hash + semantic similarity + source relations.
Deduplication and clusters are scoped to the source profile; items from another
profile in the same workspace must not suppress or merge private discoveries.

## Source dependency
A cita B, B cita C, C reproduz D devem formar uma cadeia/cluster de dependência e não múltiplas confirmações independentes.

## Independent evidence
`URLs → source clusters → independent groups`.

## Discovery dimensions
```text
editorial fit
freshness
novelty
visual potential
source availability
historical value
audience relevance
saturation
risk
```

## Brasil 65/35
Aplicar prioridade aproximada de 65% Brasil / 35% mundo na descoberta, sem transformar em quota rígida.

## Brasil source program
Configurar fontes como Arquivo Nacional, Biblioteca Nacional/Hemeroteca, IPHAN, IBGE, museus, universidades e arquivos.

## World source program
Bibliotecas, museus, arquivos e repositórios acadêmicos internacionais.

## Academic layer
OpenAlex/Crossref/DOAJ para artigos, autores, instituições e contexto. Não presumir que metadado seja prova de cada claim.

## Archive layer
Wayback/Internet Archive para recuperação e contexto, sem presumir licença de republicação.

## Quarantine
```text
QUARANTINED → AWAITING_CONFIRMATION → REASSESSMENT_DUE → CLEARED / REJECTED
```

## Fast/Deep paths
Fast para casos simples; Deep para raros/controversos/importantes; Adversarial para claims fortes; Archival para fotos/documentos; Emergency para atualidades.

## Competitor discovery
Usar para detectar assuntos, formatos e lacunas. Nunca como base de copy.

## Observability
Registrar query/source, duração, resultados, filtrados, clusters, promoted candidates e erros.

## Done
Fontes entram, sinais são normalizados, duplicatas removidas, clusters gerados, independência analisada e candidatos elegíveis promovidos.
