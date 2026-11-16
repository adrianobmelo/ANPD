# SPEC: sistema de preparação para o concurso ANPD (banca Cebraspe)

Você é um engenheiro de software sênior em Python trabalhando comigo neste repositório.
Leia este arquivo inteiro antes de escrever qualquer linha de código. As Fases 2 e 3 estão
em `ROADMAP.md` e não devem ser implementadas agora.

## 1. Contexto

Alvo: concurso da Autoridade Nacional de Proteção de Dados, cargo de Especialista em
Regulação de Proteção de Dados, 50 vagas, banca Cebraspe. Edital previsto para dezembro de
2026, com no mínimo dois meses entre edital e prova.

Sou bacharel em Direito com inscrição na OAB e tenho cerca de quinze anos de TI, com
certificação AWS e mestrado em cloud em andamento. As vagas devem ser estratificadas por
especialidade, e meu alvo provável é a de tecnologia ou segurança da informação.

O modelo Cebraspe muda a natureza do problema em relação a provas de múltipla escolha:

- cada item é julgado como certo ou errado;
- item errado anula item certo, então o que importa é saldo líquido, não taxa de acerto;
- deixar em branco é uma jogada legítima e precisa ser medida como tal;
- a banca cobra menos literalidade pura e mais extrapolação e reformulação de conceito.

Daí sai o objetivo do sistema: descobrir, com dado meu, em que nível de confiança meus
chutes passam a ser lucrativos, e onde estou perdendo saldo. Isso nenhuma plataforma de
questões calcula.

> Regra operacional crítica: se registrar um item levar mais de vinte segundos de digitação
> em condições normais, eu paro de usar e o projeto fracassa.

## 2. Regras invioláveis

1. Nenhum conteúdo jurídico pode ser produzido a partir da memória de um modelo de
   linguagem. Todo dispositivo só entra no banco se vier de arquivo de fonte que eu
   forneci. Fonte não encontrada, programa falha com erro explícito.
2. Todo cartão guarda o dispositivo de origem e o texto literal utilizado. Cartão sem
   origem rastreável é bug.
3. Não implementar motor próprio de repetição espaçada. O Anki resolve isso.
4. O sistema nunca sugere, prevê ou preenche o tipo de erro. Esse campo é meu, sem âncora
   na tela. Pode sugerir assunto, nunca tipo de erro.
5. Não persistir campo calculado. Saldo, reincidência, prioridade e ponto de corte de
   confiança são consulta ou view, não coluna.
6. Não fazer scraping de plataformas pagas de questões. Uso provas públicas do Cebraspe,
   fontes oficiais de legislação e os itens que eu mesmo resolvi.
7. Banco em SQLite, arquivo único, fora do git.
8. Toda recomendação precisa saber responder por que está sendo feita, com os números que
   a sustentam.
9. Amostra insuficiente é dita em voz alta, nunca convertida em conclusão.

## 3. Stack

Python 3.11 ou superior com uv. SQLite com SQL escrito à mão, sem ORM, migrações em
arquivos numerados em `migrations/`. Typer para a CLI, genanki para exportação, pytest para
os testes. Biblioteca padrão sempre que resolver sem dependência nova.

## 4. Fase 0: antes de codar

Não escreva código. Primeiro:

1. No máximo seis perguntas, só as que mudam decisão de arquitetura.
2. Lista das fontes que preciso baixar para `fontes/`, com nome de arquivo, órgão e origem
   oficial. O núcleo inicial é a LGPD (Lei 13.709/2018), a Lei 15.352/2026, que criou a
   carreira e transformou a ANPD em agência reguladora, e a Lei 14.133/2021.
3. Plano da Fase 1 em até vinte linhas.
4. Modelo relacional com as constraints.
5. Proposta do índice de prioridade, explicando como amostra pequena é impedida de dominar
   o ranking.

Espere minha aprovação.

## 5. Modelo de dados

**topics**: id, disciplina, código, nome, parent_id, aliases. A árvore inteira precisa
poder ser substituída quando o edital sair, com as tentativas antigas preservadas por
mapeamento, nunca por reescrita.

**items**: id, fonte, referência de origem, banca, ano, órgão, cargo, gabarito (C ou E),
topic_id, enunciado opcional.

> Modo esboço, obrigatório: quando eu registrar um item que ainda não existe, o sistema
> cria o registro com origem, gabarito e assunto, sem exigir enunciado. Exigir enunciado no
> fluxo diário inviabiliza o sistema, porque eu resolvo os itens fora dele.

**attempts**: id, item_id, data, minha resposta em C, E ou branco, acerto, confiança de 0 a
3, tempo em segundos opcional, origem da medição do tempo, tipo de erro,
topic_id_confundido, nota.

Constraints:

- item_id com chave estrangeira obrigatória;
- resposta restrita a C, E ou branco;
- acerto calculado a partir do gabarito, nunca digitado por mim, e nulo quando a resposta
  for branco;
- confiança inteira de 0 a 3;
- tipo de erro restrito à taxonomia fechada;
- topic_id_confundido só preenchido quando o tipo for confusao;
- topic_id do item pode ser nulo, com fila de classificação cobrada pela auditoria.

O tempo é opcional e carrega a origem da medição, porque cronômetro de CLI mede o intervalo
entre prompts e não o tempo real de resolução. Tempo não entra no índice de prioridade
enquanto a medição não for confiável.

## 6. Taxonomia de erro

Fechada, sem campo livre, sem acréscimo automático:

- `nao_sabia`: desconhecia o dispositivo ou o conceito
- `confusao`: troquei por instituto, prazo ou regra parecida
- `enunciado`: sabia e li mal o item
- `pressa`: sabia e marquei errado por desatenção
- `chute_certo`: acertei sem saber, contado como erro para revisão

Em `confusao`, o sistema pede o assunto confundido e grava o par. O par é simétrico: A com
B e B com A são o mesmo par perigoso.

Itens em branco não têm tipo de erro. A análise deles sai do cruzamento com a confiança.

## 7. O motor de saldo

É a parte que justifica o sistema existir. Em consulta, nunca em coluna:

- **saldo líquido** por assunto e no geral: acertos menos erros, ignorando brancos.
- **taxa de resposta**: quantos itens eu respondo e quantos deixo em branco.
- **curva de confiança**: para cada nível de 0 a 3, o saldo líquido dos itens que respondi
  naquele nível. É isso que diz a partir de qual confiança responder compensa e abaixo de
  qual eu deveria deixar em branco.
- **timidez**: itens deixados em branco com confiança 2 ou 3, ou seja, pontos que eu tinha
  e não levei.
- **falsa confiança**: confiança alta com saldo negativo.
- **reincidência** e **recência** por assunto.
- **pares perigosos**, com tentativas envolvendo o par, erros de confusão e último erro.

O ranking de prioridade da Fase 1 usa três sinais apenas: taxa de erro, reincidência e
recência. Ordene pelo limite inferior do intervalo de Wilson da taxa de erro, para que
assunto com três tentativas não suba no ranking por acaso. Falsa confiança entra quando
houver amostra. Incidência histórica só na Fase 3.

## 8. Comandos

- `estudo log`: coração do sistema. Modo turbo por padrão: confiança 2 assumida, último
  assunto mantido entre registros, assunto localizado por prefixo e por alias, item criado
  em esboço quando não existe, mínimo de confirmações. A resposta aceita C, E e branco. O
  tipo de erro só é perguntado quando houve erro ou chute certo, e sempre aparece vazio.
- `estudo import`: importa de CSV, em transação, com dry-run, relatório de linhas
  rejeitadas e sem inserção parcial. Não contorna constraint nenhuma.
- `estudo classificar`: percorre a fila de itens sem assunto.
- `estudo relatorio`: saldo por disciplina e por assunto, curva de confiança, timidez,
  distribuição dos tipos de erro, pares perigosos, evolução no tempo, dez assuntos
  prioritários. Cada linha mostra a amostra e marca explicitamente quando ela é
  insuficiente. Saída em texto, com barras em caracteres, sem emoji e sem interface
  gráfica.
- `estudo revisar`: o que volta hoje, com o motivo impresso ao lado.
- `estudo auditoria`: cartão sem dispositivo de origem, item sem assunto, tentativa sem
  tipo de erro quando exigido, confusao sem par, par preenchido fora de confusao, resposta
  ou gabarito inválido, fonte com hash divergente do índice, arquivo em `fontes/` fora do
  index e registro no index sem arquivo. Código de saída diferente de zero quando houver
  erro crítico.

## 9. Fontes

Nome de arquivo minúsculo com identificador e ano, do tipo `lei_13709_2018.pdf`,
`lei_15352_2026.pdf`. O `fontes/index.json` guarda nome, órgão, data da versão, URL oficial
e hash do arquivo. Mudou o hash, a auditoria avisa e aponta os cartões que podem ter ficado
desatualizados, sem apagar nada.

## 10. Critérios de aceite da Fase 1

- `uv run pytest` passa;
- `estudo log` registra um item em menos de vinte segundos, inclusive quando o item ainda
  não existe no banco;
- nenhuma sugestão de tipo de erro aparece em lugar nenhum;
- acerto é derivado do gabarito e nulo em branco;
- a curva de confiança é calculada e explicável;
- amostra insuficiente é identificada;
- nenhuma métrica derivada está persistida;
- a auditoria detecta inconsistências plantadas nos testes;
- README que me permita retomar o projeto meses depois;
- o banco pode ser apagado e reconstruído a partir das fontes e dos CSVs.

## 11. O que não fazer

Sem interface web, dashboard, autenticação, Docker, ORM, microserviço, abstração para
trocar de banco, sistema de plugins, pasta `core/`, serviço externo, nuvem, chatbot
jurídico, geração de conteúdo jurídico sem fonte, previsão do que a banca vai cobrar sem
base empírica, gamificação, ou motor próprio de repetição espaçada.

Entregue a Fase 1 completa e testada antes de abrir o `ROADMAP.md`. Se eu pedir para pular
etapa, me lembre desta linha.
