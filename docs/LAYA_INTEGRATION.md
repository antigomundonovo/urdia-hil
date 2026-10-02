# Laya no URDIA

O URDIA integra [Laya](https://github.com/NandhaKishorM/laya) como provider
opcional de classificação estruturada (`choice`, `score`, `noul`), não como
gerador de conteúdo nem como fonte factual. A decisão permanece sujeita à
verificação de evidências, direitos, QC e aprovação humana do URDIA.

## Instalação e ativação

Instale a dependência opcional com `pip install -e ".[laya]"` ou
`pip install "urdia-hil[laya]"`. Isso instala Laya 0.3.22 e sua pilha de
inferência. A instalação base do URDIA não instala PyTorch nem baixa pesos.
O primeiro uso precisa de acesso ao Hugging Face para baixar o modelo; a
inferência ocorre localmente no processo e não envia o estado a uma API de
inferência remota.

## Avaliação shadow local

Antes de conectar Laya ao fluxo editorial, prepare um JSONL local com casos
rotulados e revisados por humanos. Cada linha deve conter:

```json
{"id":"case-001","state":{"text":"texto histórico"},"questions":{"topic":{"type":"choice","instructions":"Qual tema descreve `text`?","criteria":{"history":"história","other":"outro"}}},"expected":{"topic":"history"},"lang":"pt"}
```

`expected` deve usar o rótulo de `choice`, boolean para `noul` ou índice inteiro
da escala ordenada de `score`. Execute:

```powershell
urdia-laya-shadow .\meus-casos-laya.jsonl --report .\artifacts\laya-shadow.json
```

O comando requer o extra `[laya]` e acesso ao Hugging Face na primeira
execução. Ele não altera registros editoriais, não persiste os textos dos
casos, não estima calibração nem estabelece um critério automático de
promoção. O relatório contém hash SHA-256 do JSONL, versão do pacote, revisões
dos checkpoints, contagens, acurácia por pergunta, erro absoluto médio de
`score` e contagem de rotas. Guarde dataset e relatório somente em local
aprovado para o nível de sensibilidade dos dados; o hash não anonimiza nem
substitui controle de acesso ao dataset.

Inclua casos representativos do perfil ANM, uma referência humana por decisão,
casos ambíguos e exemplos de falsos positivos/negativos. Para escolhas
`choice`, teste paráfrases e mudanças na ordem das opções; para português,
registre idioma explicitamente (`lang: "pt"`). O benchmark publicado pelo
projeto Laya não substitui essa avaliação própria.

O adapter é inerte até ser injetado no `CapabilityCaller` **e** os registros
de provider e capability serem ativados. A capability deve ser
`laya.classify`; configure `allowed_profiles` explicitamente para os perfis
aprovados. Não configure fallback que converta resultado ausente/inválido em
aprovação.

Exemplo de composição explícita no backend (não executado automaticamente no
startup):

```python
from packages.domain.enums import HealthState
from packages.governance.capability_call import CapabilityCaller
from packages.governance.registries import CapabilityRegistry, ProviderRegistry
from packages.providers.laya import LayaDecisionProvider

adapter = LayaDecisionProvider()
provider = ProviderRegistry(session).register(
    "laya",
    name="Laya typed decisions",
    version="0.3.22",
    privacy={"inference": "local"},
    license="Apache-2.0",
    health=HealthState.HEALTHY.value,
)
CapabilityRegistry(session).register(
    "laya.classify",
    provider_id=provider.id,
    version="1",
    allowed_profiles=["antigo_mundo_novo"],
)
caller = CapabilityCaller(session, {"laya": adapter})
```

O status HEALTHY acima é uma decisão explícita do operador; a primeira chamada
carrega o checkpoint e pode falhar por dependência ausente, falta de memória ou
rede indisponível. O caller existente audita a chamada e aplica o fallback
configurado. Em produção, registre o provider/capability em uma migração
operacional revisada, defina quota e monitore erros antes de habilitá-lo.

O contrato de entrada é:

```json
{
  "state": {"text": "texto a classificar"},
  "questions": {
    "topic": {
      "type": "choice",
      "instructions": "Qual categoria melhor descreve `text`?",
      "criteria": {"history": "tema histórico", "other": "outro tema"}
    }
  },
  "lang": "pt"
}
```

`lang` é opcional. Cada pergunta exige `instructions`; `choice` admite de 2 a
20 opções, `score` de 2 a 32 níveis ordenados e `noul` retorna probabilidade de
verdade. Estado limitado a 50.000 caracteres; máximo de 64 perguntas.

Resposta é marcada `mode=ADVISORY` e
`confidence_policy=UNVALIDATED_DO_NOT_GATE`. O campo não deve entrar em gates
determinísticos ou automatizar a seleção/publicação. As probabilidades dos
checkpoints disponíveis são conhecidas por apresentar calibração inadequada
ou não validada para o domínio ANM; não estabeleça limiar operacional sem
dataset holdout próprio, validação por perfil/idioma/tipo de pergunta e
avaliação humana. A integração fixa os SHAs de modelo `reviewed` da versão
Laya instalada; a versão do pacote está travada em 0.3.22.

## Licença e atribuição

O pacote Laya 0.3.22 e os model cards publicados dos checkpoints oficiais
consultados (`laya`, `laya-multilingual`, `laya-typed-decisions`) indicam
Apache License 2.0. URDIA depende do pacote sem copiar seu código-fonte ou
incorporar pesos ao repositório. Ao redistribuir uma instalação que inclua
Laya ou seus pesos, distribua também a licença Apache 2.0 aplicável e preserve
os avisos de copyright/atribuição e quaisquer arquivos `NOTICE` fornecidos
com os artefatos; identifique modificações caso código Laya seja incorporado
ou modificado. A licença não concede direito sobre marcas registradas.

Referências consultadas:

- Código e licença: [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya),
  commit `6d942c92081fbc139e736bbd9ac0023223c29b7f`.
- Pesos/model cards: [laya](https://huggingface.co/convaiinnovations/laya),
  [laya-multilingual](https://huggingface.co/convaiinnovations/laya-multilingual)
  e
  [laya-typed-decisions](https://huggingface.co/convaiinnovations/laya-typed-decisions).
- Política operacional e limites: [Laya benchmarks](https://github.com/NandhaKishorM/laya/blob/main/docs/benchmarks.md),
  [confidence](https://github.com/NandhaKishorM/laya/blob/main/docs/questions-and-answers.md)
  e [staged adoption](https://github.com/NandhaKishorM/laya/blob/main/docs/staged-adoption.md).
