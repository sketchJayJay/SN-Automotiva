# SN Serviços Automotivos

Sistema web da SN Serviços Automotivos, pronto para rodar no Coolify e com visual melhorado para celular.

## Funções

- Cadastro de clientes e veículos
- Ordem de serviço com busca de cliente, busca de veículo e busca de itens
- Estoque com cadastro, edição, exclusão e baixa automática na OS
- Relatórios financeiros por período
- Impressão / salvar PDF da OS
- Layout responsivo estilo aplicativo de celular
- Manifest PWA para adicionar na tela inicial do celular

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://127.0.0.1:5000
```

## Coolify

Use **Dockerfile** como Build Pack e porta **5000**.

Variáveis recomendadas:

```env
PORT=5000
DATA_DIR=/app/data
SECRET_KEY=sn-servicos-automotivos
```

Persistent Storage:

```text
/app/data
```

Esse volume preserva o banco SQLite entre deploys.

## Celular

No navegador do celular, abra o endereço do sistema e use a opção **Adicionar à Tela de Início**. Ele abre com aparência de app, menu inferior e botão rápido para nova OS.
