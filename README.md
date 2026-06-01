# Sistema SN Serviços Automotivos

Sistema web para oficina mecânica, com:

- Dashboard com resumo
- Cadastro de clientes e veículos
- Ordens de serviço com peças, mão de obra, desconto e impressão
- Estoque com baixa automática ao lançar peças na OS
- Relatórios por período
- Logo da SN Serviços Automotivos já configurada

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Abra:

```text
http://127.0.0.1:5000
```

## Deploy no Coolify

O projeto já está pronto para Docker/Coolify.

### Opção recomendada: Dockerfile

- Build Pack: Dockerfile
- Porta interna: 5000
- Variáveis:
  - PORT=5000
  - DATA_DIR=/app/data
  - SECRET_KEY=coloque-uma-chave-grande-aqui
- Persistent Storage:
  - /app/data

O banco SQLite fica em `/app/data/sn_servicos.db`, para não perder dados no redeploy.

### Opção Docker Compose

Use o `docker-compose.yml` deste projeto. Ele já cria um volume chamado `sn_servicos_data` apontando para `/app/data`.
