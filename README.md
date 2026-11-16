# estudo: registro de itens Cebraspe e motor de saldo

Sistema de linha de comando para a preparação do concurso da ANPD. Ele registra os
itens que você resolve fora dele (certo ou errado, confiança de 0 a 3, tipo de erro) e
calcula, com o seu dado, onde você perde saldo líquido e a partir de qual confiança
responder compensa. O contrato do projeto está em [SPEC.md](SPEC.md); as fases
seguintes estão em [ROADMAP.md](ROADMAP.md) e não foram implementadas.

Estado atual: Fase 1 completa. Fase 0 (perguntas e plano) aprovada em 16/11/2026 com
as recomendações propostas, resumidas em "Decisões" no fim deste arquivo.

## Estudar a LGPD: uso diário

Tudo já vem configurado: a árvore de assuntos da LGPD (`lgpd_2026`) está em `dados/` e o
banco se monta sozinho na primeira vez que você roda qualquer comando.

1. Leia a lei em [leitura/lgpd.md](leitura/lgpd.md). É o texto vigente copiado da fonte,
   com a norma que deu cada redação e a marca **[Lei 15.352]** nos dispositivos que ela
   alterou. No topo há um confronto com a Lei 15.352: onde a consolidação não acompanhou
   a alteração, aparece a redação certa logo abaixo do dispositivo.
2. Resolva itens Cebraspe fora do sistema (prova em PDF, caderno). Ao terminar cada bloco,
   registre:

   ```
   uv run estudo log --fonte cebraspe_2024_anatel
   [cebraspe_2024_anatel | (sem assunto)] > 12 C E bases
   tipo de erro: 1 nao_sabia  2 confusao  3 enunciado  4 pressa
   > 1
   [cebraspe_2024_anatel | LGPD.C2.S1] > 13 E E
   [cebraspe_2024_anatel | LGPD.C2.S1] > 14 C C 3 dir
   ```

   Número do item, gabarito, sua resposta. Confiança só quando não for 2. O assunto
   continua o mesmo até você digitar outro apelido.
3. Uma vez por semana: `uv run estudo relatorio` e `uv run estudo revisar`.
4. Faça commit de `dados/` de vez em quando. É lá que fica o seu histórico; o banco é
   descartável.

Apelidos dos assuntos (os artigos de cada um saem da estrutura da fonte):

| Apelido | Assunto | Arts. |
| --- | --- | --- |
| `prel` | Cap. I, disposições preliminares | 1º a 6º |
| `bases` | Cap. II, Seção I, requisitos para o tratamento | 7º a 10 |
| `sens` | Cap. II, Seção II, dados sensíveis | 11 a 13 |
| `crianca` | Cap. II, Seção III, crianças e adolescentes | 14 |
| `term` | Cap. II, Seção IV, término do tratamento | 15 e 16 |
| `dir` | Cap. III, direitos do titular | 17 a 22 |
| `pubreg` | Cap. IV, Seção I, poder público: regras | 23 a 30 |
| `pubresp` | Cap. IV, Seção II, poder público: responsabilidade | 31 e 32 |
| `transf` | Cap. V, transferência internacional | 33 a 36 |
| `ctrl` | Cap. VI, Seção I, controlador e operador | 37 a 40 |
| `enc` | Cap. VI, Seção II, encarregado | 41 |
| `resp` | Cap. VI, Seção III, responsabilidade e ressarcimento | 42 a 45 |
| `sigilo` | Cap. VII, Seção I, segurança e sigilo | 46 a 49 |
| `gov` | Cap. VII, Seção II, boas práticas e governança | 50 e 51 |
| `sanc` | Cap. VIII, Seção I, sanções administrativas | 52 a 54 |
| `anpd` | Cap. IX, Seção I, a Agência (ANPD) | 55 a 57, com 55-A a 55-M |
| `cnpd` | Cap. IX, Seção II, Conselho Nacional | 58, 58-A, 58-B e 59 |
| `finais` | Cap. X, disposições finais e transitórias | 60 a 65 |

Os capítulos também têm apelido (`trat`, `pub`, `agentes`, `seg`, `fisc`, `anpdcap`) para
item que pega o capítulo inteiro. `uv run estudo arvore listar` mostra a lista completa.
O nome da Seção I do Capítulo IX na árvore vem da Lei 15.352, porque a consolidação ainda
traz o nome antigo.

## Começar de novo depois de meses

```
uv sync                 # instala as dependências (Python 3.11 ou superior)
uv run pytest           # tudo precisa passar
uv run estudo auditoria # banco, diário e fontes coerentes; código 1 se houver erro crítico
uv run estudo relatorio
```

Rode os comandos na raiz do repositório, porque `dados/` e `fontes/` são lidos da pasta
atual (ou de `ESTUDO_RAIZ`). O banco SQLite fica fora do git, em
`%LOCALAPPDATA%\estudo\estudo.db` no Windows e `~/.local/share/estudo/estudo.db` no
Linux, ou onde `ESTUDO_DB` apontar. Ele é descartável: `uv run estudo reconstruir
--forcar` apaga e refaz o banco a partir de `dados/`.

## O que fica onde

| Caminho | Conteúdo | No git |
| --- | --- | --- |
| `migrations/NNN_*.sql` | schema, constraints, triggers e views, aplicados em ordem | sim |
| `estudo/` | código | sim |
| `dados/tentativas.csv` | diário de toda tentativa registrada, só acréscimo | sim |
| `dados/classificacoes.csv` | itens classificados depois pelo `classificar` | sim |
| `dados/arvores/<nome>.csv`, `dados/arvores.csv` | árvores de assuntos e a ordem em que foram carregadas e ativadas | sim |
| `dados/mapas.csv` | mapeamentos entre árvores | sim |
| `fontes/` e `fontes/index.json` | textos oficiais e índice com URL, data e SHA-256 | sim |
| banco SQLite | cache reconstruível | não |

Não edite os CSVs de `dados/` à mão sem rodar `estudo auditoria` em seguida; a
auditoria compara o número de tentativas do banco com o do diário.

## Fluxo diário: `estudo log`

```
uv run estudo log --fonte cebraspe_2024_anatel_esp
[cebraspe_2024_anatel_esp | (sem assunto)] > 57 C E dir
tipo de erro: 1 nao_sabia  2 confusao  3 enunciado  4 pressa
> 1
ok cebraspe_2024_anatel_esp/57 (novo, esboço): errado nao_sabia | LGPD.DIR | sessão 1 itens, saldo -1
```

Uma linha por item: referência, gabarito e sua resposta. Item que não existe é criado
em esboço (fonte, referência, gabarito, assunto, sem enunciado). Depois da referência,
em qualquer ordem:

| Token | Efeito |
| --- | --- |
| `C E` | gabarito C, respondi E. Com o item já no banco, basta a resposta: `57 E` |
| `B` ou `-` | deixei em branco |
| `0` a `3` | confiança digitada. Sem número, vale 2 e fica marcada como assumida |
| `ch` | acertei chutando (`chute_certo`) |
| qualquer palavra | assunto por prefixo do código ou alias; fica valendo para as próximas linhas |
| `90s` | tempo medido em cronômetro externo |
| `#texto` | nota |
| `prova/57` | troca a fonte da sessão |

O tipo de erro só é perguntado quando você erra, sem opção pré-selecionada: Enter vazio
repete a pergunta. Em `confusao`, o sistema pede o assunto confundido. Linha vazia ou
`q` encerra; `?` mostra a sintaxe.

## Outros comandos

| Comando | O que faz |
| --- | --- |
| `estudo import arquivo.csv [--dry-run]` | importa tentativas no formato de `dados/tentativas.csv` (obrigatórias: fonte, referencia, resposta, confianca). Uma linha inválida e nada entra; o relatório diz qual linha e por quê |
| `estudo classificar` | percorre os itens sem assunto |
| `estudo relatorio` | saldo geral, por disciplina e assunto, curvas de confiança, timidez, tipos de erro, falsa confiança, pares perigosos, evolução semanal, dez prioritários |
| `estudo revisar` | itens cuja última tentativa foi erro ou chute certo, com o motivo |
| `estudo auditoria` | inconsistências; código de saída 1 em erro crítico |
| `estudo reconstruir --forcar` | refaz o banco a partir de `dados/` |
| `estudo arvore carregar CSV --nome x` | carrega árvore nova (colunas `codigo,nome,disciplina,parent_codigo,aliases`, aliases separados por `\|`) e a ativa |
| `estudo arvore mapear CSV` | mapeia assuntos de uma árvore para outra (`de_arvore,de_codigo,para_arvore,para_codigo`) |
| `estudo arvore sumario ARQ --prefixo LGPD ...` | gera CSV de árvore com os títulos, capítulos e seções do arquivo em `fontes/` |
| `estudo arvore listar` | assuntos da árvore ativa |
| `estudo leitura lgpd` | regera `leitura/lgpd.md` a partir de `fontes/` |
| `estudo fontes baixar` | baixa LGPD, Lei 15.352/2026 e Lei 14.133/2021 do normas.leg.br e registra o hash |
| `estudo fontes registrar ARQ ...` | registra arquivo que você colocou em `fontes/` |

## Como ler o relatório

Saldo líquido é acertos menos erros; branco vale zero. Chute certo conta como acerto no
saldo e na curva, porque a prova dá o ponto, e como erro no índice de prioridade e no
`revisar`.

A curva de confiança mostra, para cada nível, o saldo e a taxa de acerto com intervalo
de Wilson de 95%. No modelo Cebraspe o ganho esperado de responder é 2p - 1, então
responder compensa quando p > 50%. O veredito só sai quando o intervalo inteiro fica de
um lado de 50% e há pelo menos 10 itens respondidos no nível; fora disso a linha diz
"inconclusivo" ou "amostra insuficiente". A segunda curva usa só a confiança que você
digitou, sem o 2 assumido do modo turbo.

Prioridade de um assunto:

```
P = Wilson_inferior(erros, respondidos) x (1 + 0,1 x min(reincidentes, 5)) x (0,5 + 0,5 x 2^(-dias/30))
```

multiplicado por 1,25 quando há falsa confiança com amostra (10 ou mais respondidos com
confiança 2 ou 3 e saldo negativo). Assunto com menos de 5 respondidos fica fora do
ranking e aparece numa lista própria. Reincidente é item errado em duas ou mais
tentativas; dias é o tempo desde o último erro. As constantes estão em
`estudo/metricas.py` e são impressas no topo do relatório. São escolha inicial, não
vieram de dado. Tempo não entra no índice.

## Regras que o código garante

- Acerto não é coluna: sai da view `v_tentativas`, derivado do gabarito, nulo em branco.
- Nenhuma coluna guarda métrica derivada; há teste que inspeciona o schema.
- Resposta em C, E ou B; gabarito em C ou E; confiança inteira de 0 a 3; tipo de erro na
  taxonomia fechada; assunto confundido só em `confusao`. CHECK e triggers recusam o resto,
  inclusive no `import`.
- Errou: tipo obrigatório. Acertou: só `chute_certo` ou nada. Branco: nunca tem tipo.
- Árvore nova não reescreve tentativa antiga: os relatórios resolvem o assunto atual pelo
  `topic_map`. Assunto dividido em dois conta a tentativa nos dois.
- Fonte que mudou de hash é apontada pela auditoria e nada é apagado.

Corrigir o gabarito de um item em esboço não passa pelos triggers das tentativas; a
auditoria aponta as tentativas que ficaram incoerentes.

## Decisões da Fase 0

1. Cada `log` grava no banco e no diário `dados/tentativas.csv` na mesma transação; a
   reconstrução reimporta o diário.
2. Item identificado por `fonte` (prova) e `referencia` (número do item), únicos juntos.
3. `chute_certo` vale +1 no saldo e conta como erro para prioridade e revisão.
4. `confianca_explicita` separa confiança digitada da assumida.
5. Árvore provisória a partir do sumário dos arquivos em `fontes/` (`estudo arvore sumario`),
   mais as disciplinas que você acrescentar no CSV.
6. A checagem de cartão sem dispositivo fica para a Fase 2, quando existirem cartões.

## Fontes

As três leis do núcleo já estão em `fontes/`, baixadas em 16/11/2026 por
`estudo fontes baixar`. A origem é a API pública do normas.leg.br, o portal de
legislação do Congresso Nacional, e cada arquivo é a resposta JSON gravada sem
alteração. O JSON traz um registro por dispositivo (artigo, parágrafo, inciso, alínea)
com todas as versões datadas e a norma que fez cada alteração, o que serve à ingestão
da Fase 2.

O Planalto não serviu: de fora do Brasil, todo endereço de `planalto.gov.br/ccivil_03`
redireciona para a página inicial do gov.br, e o comando recusa gravar quando há
redirecionamento.

`fontes/index.json` guarda arquivo, norma, origem, URL da API, URN, página para leitura
humana, data da versão, SHA-256, licença (CC BY 4.0) e os tipos de texto que a fonte
declara. Pontos que valem saber antes de usar esses textos:

- A própria fonte marca todos os textos como `UnofficialLegalValue`. O texto com valor
  oficial é o do Diário Oficial; compilação, aqui ou no Planalto, não é oficial.
- A consolidação da LGPD tem pelo menos uma lacuna conferida: o nome da Seção I do
  Capítulo IX continua "Da Autoridade Nacional de Proteção de Dados (ANPD)", embora a
  Lei 15.352/2026 o altere para "Da Agência Nacional de Proteção de Dados". Por isso a
  Lei 15.352 fica também em arquivo próprio, e a Fase 2 precisa conferir cada
  dispositivo alterado contra a lei alteradora.
- O HTML "Compilação Monovigente" que o portal oferece para a LGPD está desatualizado
  (última alteração citada de 2022) e não foi usado.

Para outra fonte, coloque o arquivo em `fontes/` com nome minúsculo do tipo
`lei_13709_2018.html` e rode `estudo fontes registrar`.

`dados/propostas/arvore_14133.csv` tem os títulos e capítulos da 14.133, ainda sem
apelidos e não carregada. Quando for estudar essa lei ou as disciplinas de TI, junte os
assuntos novos aos da LGPD num CSV só e carregue como árvore nova (`estudo arvore
carregar ... --nome x`); a árvore antiga fica preservada e as tentativas continuam valendo.
