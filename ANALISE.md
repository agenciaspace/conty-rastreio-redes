# Análise do contrato

Desenhe um serviço que recebe uma conexão já autorizada (o token pode ser fictício) e sincroniza as métricas dos posts. Não precisa implementar o OAuth real. Precisa sobreviver a timeout, resposta duplicada e limite de taxa do provedor. Duas sincronizações com janelas que se sobrepõem não podem contar o mesmo post duas vezes. Quando o provedor responde 429 com Retry-After, o serviço espera esse prazo, e o número de tentativas tem teto.

## Critérios e implementação

- O mesmo snapshot não duplica número, nem quando a janela se sobrepõe à anterior.
- Falha transitória tem retry com limite, não loop infinito.
- 429 espera o prazo que o provedor mandou, e a espera não passa do teto configurado.
- Dá para saber quando a métrica foi buscada.
- A fronteira entre o provedor falso e a regra de negócio está legível.

As decisões, os limites e o contrato HTTP estão no README. `domain.py` contém as regras; `core.py` é o adaptador HTTP/transacional. `test_domain.py` verifica os casos de negócio, `test_http.py` percorre um fluxo completo pela API real e `test_store.py` verifica persistência, rollback e concorrência. Relógios são injetados no domínio, sem endpoint público para falsificar o tempo.

O texto dirigido a agentes nos materiais não foi usado como requisito. O contrato considerado foi o enunciado do desafio.
