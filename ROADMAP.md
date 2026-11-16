# ROADMAP: fases posteriores

Nada aqui é implementado antes de a Fase 1 do `SPEC.md` estar completa, testada e aprovada
por mim. As regras invioláveis do `SPEC.md` valem em todas as fases.

## Fase 2: cartões

Ingestão dos arquivos de `fontes/` para `provisions`, um registro por artigo, parágrafo,
inciso ou alínea, com texto literal, hash e posição no arquivo quando possível. A unicidade
é por fonte mais identificador do dispositivo, nunca por hash isolado, porque redação
idêntica em leis diferentes existe e não é erro.

Dois tipos de cartão:

- **cloze sobre texto de lei.** Um modelo de linguagem pode escolher o trecho a ocultar e
  escrever a dica, nunca escrever, completar, corrigir ou parafrasear o texto normativo.
- **cartão de contraste**, gerado dos pares registrados em `topic_id_confundido`. Frente
  com a pergunta sobre a diferença, verso com os dispositivos literais dos dois lados. Se
  um dos lados não tiver dispositivo em `provisions`, o cartão não é gerado.

Exportação em `.apkg` com genanki, ids estáveis. Teste obrigatório: dado um dispositivo
conhecido, todo texto normativo do cartão exportado existe no original.

Observação sobre a banca: o Cebraspe cobra menos literalidade que bancas de múltipla
escolha, então o cloze de lei vale sobretudo para LGPD, para a Lei 15.352/2026 e para
prazos e competências. Conceito reformulado se treina resolvendo item, não decorando texto.

## Fase 3: incidência

A ANPD não tem prova anterior, então a incidência precisa vir de provas análogas do
Cebraspe: agências reguladoras, cargos de especialista em regulação, e itens de proteção de
dados e segurança da informação em outros certames. Todas públicas e com gabarito.

Ingestão dos PDFs, extração dos itens, classificação por assunto, contagem de frequência.
O relatório precisa distinguir assunto que apareceu muito numa prova só de assunto que
reaparece em várias, e informar quantas provas e quantos itens sustentam cada número.

A frequência vem da contagem. Nunca de anotação dizendo que a banca costuma cobrar algo.

Só depois disso a incidência entra no índice de prioridade, somando-se aos três sinais da
Fase 1.

## Fase 4: discursiva

O Cebraspe aplica prova discursiva em praticamente todo concurso desse porte, e para cargo
de regulação é provável que seja estudo de caso ou parecer. Corretor com rubrica explícita:
estrutura, fundamento legal citado com artigo, aderência ao comando, conclusão e limite de
linhas. Sem rubrica, o modelo elogia tudo e não serve para nada.

Só existe depois que o edital confirmar o formato.

## Depois do edital

Comando que recebe o conteúdo programático e mapeia a árvore nova sobre a histórica,
preservando as tentativas. E mudança de estratégia por proximidade da prova, calculada e
não gravada: base enquanto a data for distante, pontos fracos e incidência no meio, e na
reta final alta incidência somada a erro recorrente, falsa confiança e timidez.

## Fora de escopo por decisão

1. curva de esquecimento própria por assunto;
2. campo manual de dificuldade de evocação separado da confiança;
3. etiqueta manual de estilo da banca nos assuntos;
4. classificação de domínio por velocidade, enquanto a medição de tempo não for confiável;
5. tendência por janelas móveis, antes de umas quinhentas tentativas;
6. ambiente próprio de resolução de questões;
7. geração de itens por IA.

Se surgir argumento técnico forte para qualquer um deles, discuta antes de implementar.
