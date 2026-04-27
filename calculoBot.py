import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import traceback


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def conectar_google_sheets():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])

        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        spreadsheet_id = "1QWH5ymxydGafl76tdvK5Uu_F5J0y5Tj2zXl0EEeYDpg"

        client = gspread.service_account_from_dict(
            creds_dict,
            scopes=SCOPES
        )

        planilha = client.open_by_key(spreadsheet_id)
        return planilha

    except Exception:
        erro_completo = traceback.format_exc()
        st.error(f"Erro ao conectar ao Google Sheets:\n{erro_completo}")
        return None


def para_float(valor):
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    valor = str(valor).strip()
    valor = valor.replace("R$", "").replace(" ", "")

    if "," in valor and "." in valor:
        valor = valor.replace(".", "").replace(",", ".")
    else:
        valor = valor.replace(",", ".")

    return float(valor)


def para_int(valor):
    return int(float(para_float(valor)))


def formatar_moeda(valor):
    texto = f"{float(valor):,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def gerar_codigo_orcamento():
    return f"ORC-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def limpar_formulario():
    st.session_state["nome_cliente"] = ""
    st.session_state["nome_revendedor"] = ""
    st.session_state["conexoes"] = 1
    st.session_state["usuarios"] = 1
    st.session_state["instagram"] = False
    st.session_state["facebook"] = False
    st.session_state["telegram"] = False
    st.session_state["meta"] = False
    st.session_state["ultimo_resultado"] = None
    st.session_state["modo_edicao"] = False
    st.session_state["codigo_em_edicao"] = None


def carregar_configuracoes():
    try:
        planilha = conectar_google_sheets()
        if not planilha:
            return None, None, None

        aba_precos = planilha.worksheet("config_precos")
        linhas_precos = aba_precos.get_all_values()

        config_precos = {}
        for linha in linhas_precos[1:]:
            if len(linha) >= 2:
                parametro = str(linha[0]).strip()
                valor = para_float(linha[1])
                config_precos[parametro] = valor

        aba_implantacao = planilha.worksheet("config_implantacao")
        linhas_implantacao = aba_implantacao.get_all_values()

        cabecalho = [c.strip() for c in linhas_implantacao[0]]
        idx_min = cabecalho.index("min_usuarios")
        idx_max = cabecalho.index("max_usuarios")
        idx_valor = cabecalho.index("valor_implantacao")

        faixas_implantacao = []
        for linha in linhas_implantacao[1:]:
            if len(linha) > max(idx_min, idx_max, idx_valor):
                faixas_implantacao.append(
                    {
                        "min_usuarios": para_int(linha[idx_min]),
                        "max_usuarios": para_int(linha[idx_max]),
                        "valor_implantacao": para_float(linha[idx_valor]),
                    }
                )

        return config_precos, faixas_implantacao, planilha

    except Exception:
        erro_completo = traceback.format_exc()
        st.error(f"Erro ao carregar configurações:\n{erro_completo}")
        return None, None, None


def garantir_aba(planilha, nome_aba, colunas):
    try:
        aba = planilha.worksheet(nome_aba)
        valores = aba.get_all_values()
        if not valores:
            aba.update("A1", [colunas])
        return aba
    except Exception:
        aba = planilha.add_worksheet(
            title=nome_aba,
            rows=1000,
            cols=max(20, len(colunas))
        )
        aba.update("A1", [colunas])
        return aba


def ler_aba_dataframe(planilha, nome_aba, colunas=None):
    try:
        planilha_atual = conectar_google_sheets()
        if not planilha_atual:
            if colunas is not None:
                return pd.DataFrame(columns=colunas)
            return pd.DataFrame()

        aba = planilha_atual.worksheet(nome_aba)
        registros = aba.get_all_records()
        return pd.DataFrame(registros)

    except Exception:
        if colunas is not None:
            return pd.DataFrame(columns=colunas)
        return pd.DataFrame()


def salvar_em_aba(planilha, nome_aba, dados, colunas):
    try:
        planilha_atual = conectar_google_sheets()
        if not planilha_atual:
            return False

        aba = garantir_aba(planilha_atual, nome_aba, colunas)
        nova_linha = [dados.get(col, "") for col in colunas]
        aba.append_row(nova_linha)
        return True

    except Exception:
        st.error(f"Erro ao salvar em '{nome_aba}':\n{traceback.format_exc()}")
        return False


def atualizar_linha_orcamento(planilha, nome_aba, codigo, dados, colunas):
    try:
        planilha_atual = conectar_google_sheets()
        if not planilha_atual:
            return False

        aba = planilha_atual.worksheet(nome_aba)
        registros = aba.get_all_values()

        if not registros:
            st.error("A aba está vazia.")
            return False

        cabecalho = registros[0]

        if "codigo" not in cabecalho:
            st.error("A coluna 'codigo' não foi encontrada.")
            return False

        idx_codigo = cabecalho.index("codigo")
        codigo = str(codigo).strip()

        linha_encontrada = None
        for i, linha in enumerate(registros[1:], start=2):
            if len(linha) > idx_codigo and str(linha[idx_codigo]).strip() == codigo:
                linha_encontrada = i
                break

        if linha_encontrada is None:
            st.error("Orçamento não encontrado.")
            return False

        nova_linha = [dados.get(col, "") for col in colunas]
        aba.update(f"A{linha_encontrada}", [nova_linha])

        return True

    except Exception:
        st.error(f"Erro ao atualizar orçamento:\n{traceback.format_exc()}")
        return False


def carregar_orcamento_para_edicao(item):
    st.session_state["modo_edicao"] = True
    st.session_state["codigo_em_edicao"] = str(item.get("codigo", ""))
    st.session_state["nome_cliente"] = str(item.get("nome_cliente", ""))
    st.session_state["nome_revendedor"] = str(item.get("nome_revendedor", ""))
    st.session_state["conexoes"] = para_int(item.get("conexoes", 1))
    st.session_state["usuarios"] = para_int(item.get("usuarios", 1))

    meta_valor = str(item.get("meta", "")).strip().lower()
    st.session_state["meta"] = meta_valor in ["sim", "true", "1", "yes"]

    # A aba orcamentos_revendedor não guarda quais redes foram marcadas.
    # Por isso, ao editar, marque novamente Instagram/Facebook/Telegram se necessário.
    st.session_state["instagram"] = False
    st.session_state["facebook"] = False
    st.session_state["telegram"] = False

    st.session_state["ultimo_resultado"] = None


def calcular_custo(conexoes, usuarios, redes, meta, config_precos, faixas_implantacao):
    if conexoes == 1:
        custo_conexoes = config_precos["valor_primeira_conexao"]
    elif 2 <= conexoes <= 5:
        custo_conexoes = (
            config_precos["valor_primeira_conexao"]
            + (conexoes - 1) * config_precos["valor_conexao_2a_5"]
        )
    elif 6 <= conexoes <= 10:
        custo_conexoes = (
            config_precos["valor_primeira_conexao"]
            + (4 * config_precos["valor_conexao_2a_5"])
            + ((conexoes - 5) * config_precos["valor_conexao_6a_10"])
        )
    else:
        custo_conexoes = (
            config_precos["valor_primeira_conexao"]
            + (4 * config_precos["valor_conexao_2a_5"])
            + (5 * config_precos["valor_conexao_6a_10"])
        )

    if usuarios == 1:
        custo_usuarios = config_precos["valor_basico_primeiro_usuario"]
    elif 2 <= usuarios <= 19:
        custo_usuarios = (
            config_precos["valor_basico_primeiro_usuario"]
            + (usuarios - 1) * config_precos["valor_usuario_2a_19"]
        )
    elif 20 <= usuarios <= 39:
        custo_usuarios = (
            config_precos["valor_basico_primeiro_usuario"]
            + (usuarios - 1) * config_precos["valor_usuario_20a_39"]
        )
    else:
        custo_usuarios = (
            config_precos["valor_basico_primeiro_usuario"]
            + (usuarios - 1) * config_precos["valor_usuario_40_mais"]
        )

    custo_total = custo_conexoes + custo_usuarios

    valor_implantacao = 0.0
    for faixa in faixas_implantacao:
        if faixa["min_usuarios"] <= usuarios <= faixa["max_usuarios"]:
            valor_implantacao = faixa["valor_implantacao"]
            break

    if meta:
        valor_implantacao += config_precos["valor_adicional_meta"]

    qtd_redes = sum([
        redes.get("instagram", False),
        redes.get("facebook", False),
        redes.get("telegram", False)
    ])

    valor_redes_sociais = qtd_redes * config_precos["valor_por_rede_social"]

    custo_revendedor = custo_total * (
        1 + config_precos["percentual_redes_sociais"] * qtd_redes
    )

    valor_sugerido = custo_total * (1 + config_precos["margem_revendedor"])
    valor_cliente = valor_sugerido + valor_redes_sociais

    return {
        "custo_base": custo_total,
        "custo_conexoes": custo_conexoes,
        "custo_usuarios": custo_usuarios,
        "custo_revendedor": custo_revendedor,
        "implantacao": valor_implantacao,
        "redes_sociais": valor_redes_sociais,
        "valor_cliente": valor_cliente,
        "qtd_redes": qtd_redes
    }


def gerar_pdf_orcamento(dados):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4

    y = altura - 60

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "Orçamento de Implantação de Chat Bot")
    y -= 30

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Código do orçamento: {dados['codigo']}")
    y -= 18
    pdf.drawString(50, y, f"Data de emissão: {dados['data_emissao']}")
    y -= 18
    pdf.drawString(50, y, f"Validade: {dados['data_validade']}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, "Dados do orçamento")
    y -= 25

    pdf.setFont("Helvetica", 11)
    linhas = [
        f"Cliente: {dados['nome_cliente']}",
        f"Revendedor: {dados['nome_revendedor']}",
        f"Quantidade de conexões: {dados['conexoes']}",
        f"Quantidade de usuários: {dados['usuarios']}",
        f"Valor revendedor: {dados['valor_revendedor']}",
        f"Sugestão final: {dados['sugestao_final']}",
        f"Valor de implantação: {dados['valor_implantacao']}",
    ]

    for linha in linhas:
        pdf.drawString(50, y, linha)
        y -= 20

    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Observação:")
    y -= 18

    pdf.setFont("Helvetica", 10)
    obs = (
        "Este orçamento é válido por 10 dias corridos a partir da data de emissão. "
        "Após esse período, os valores e condições poderão sofrer alteração."
    )

    palavras = obs.split()
    linha = ""
    for palavra in palavras:
        teste = f"{linha} {palavra}".strip()
        if len(teste) < 95:
            linha = teste
        else:
            pdf.drawString(50, y, linha)
            y -= 16
            linha = palavra

    if linha:
        pdf.drawString(50, y, linha)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


with st.spinner("Conectando ao Google Sheets..."):
    config_precos, faixas_implantacao, planilha = carregar_configuracoes()

if config_precos is None:
    st.stop()

if "ultimo_resultado" not in st.session_state:
    st.session_state["ultimo_resultado"] = None

if "modo_edicao" not in st.session_state:
    st.session_state["modo_edicao"] = False

if "codigo_em_edicao" not in st.session_state:
    st.session_state["codigo_em_edicao"] = None


st.title("🤖 Calculadora de Custos para Chat Bot")
st.markdown("---")

st.subheader("🧾 Dados do orçamento")

col_info1, col_info2 = st.columns(2)
with col_info1:
    nome_cliente = st.text_input("Nome do cliente", key="nome_cliente")
with col_info2:
    nome_revendedor = st.text_input("Nome do revendedor", key="nome_revendedor")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📱 Conexões")
    conexoes = st.number_input(
        "Número de conexões (chips):",
        min_value=1,
        value=1,
        step=1,
        key="conexoes"
    )

with col2:
    st.subheader("👥 Usuários")
    usuarios = st.number_input(
        "Número de usuários:",
        min_value=1,
        value=1,
        step=1,
        key="usuarios"
    )

st.markdown("---")
st.subheader("🌐 Redes Sociais e Opções")

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
with col_r1:
    instagram = st.checkbox("📸 Instagram", key="instagram")
with col_r2:
    facebook = st.checkbox("📘 Facebook", key="facebook")
with col_r3:
    telegram = st.checkbox("💬 Telegram", key="telegram")
with col_r4:
    meta = st.checkbox("⭐ Meta", key="meta")

st.markdown("---")

col_btn1, col_btn2, col_btn3 = st.columns(3)

with col_btn1:
    calcular = st.button(
        "💰 CALCULAR ORÇAMENTO",
        type="primary",
        use_container_width=True,
        key="btn_calcular_orcamento",
        disabled=st.session_state.get("modo_edicao", False)
    )

with col_btn2:
    st.button(
        "🧹 NOVO ORÇAMENTO",
        use_container_width=True,
        on_click=limpar_formulario,
        key="btn_novo_orcamento"
    )

with col_btn3:
    salvar_alteracao = False
    if st.session_state.get("modo_edicao", False):
        salvar_alteracao = st.button(
            "💾 SALVAR ALTERAÇÃO",
            use_container_width=True,
            key="btn_salvar_alteracao"
        )

if st.session_state.get("modo_edicao", False):
    st.info(f"Editando orçamento: {st.session_state.get('codigo_em_edicao')}. Faça as alterações e clique em SALVAR ALTERAÇÃO.")

if calcular:
    if not nome_cliente.strip() or not nome_revendedor.strip():
        st.error("Preencha o nome do cliente e o nome do revendedor.")
    else:
        redes = {
            "instagram": instagram,
            "facebook": facebook,
            "telegram": telegram
        }

        resultado = calcular_custo(
            conexoes=conexoes,
            usuarios=usuarios,
            redes=redes,
            meta=meta,
            config_precos=config_precos,
            faixas_implantacao=faixas_implantacao
        )

        data_emissao_dt = datetime.now()
        data_validade_dt = data_emissao_dt + timedelta(days=10)
        codigo_orcamento = gerar_codigo_orcamento()

        colunas_historico = [
            "data", "codigo", "nome_cliente", "nome_revendedor", "conexoes", "usuarios",
            "instagram", "facebook", "telegram", "meta",
            "custo_base", "custo_revendedor", "implantacao", "redes_sociais", "valor_cliente"
        ]

        dados_historico = {
            "data": data_emissao_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "codigo": codigo_orcamento,
            "nome_cliente": nome_cliente,
            "nome_revendedor": nome_revendedor,
            "conexoes": conexoes,
            "usuarios": usuarios,
            "instagram": instagram,
            "facebook": facebook,
            "telegram": telegram,
            "meta": meta,
            "custo_base": resultado["custo_base"],
            "custo_revendedor": resultado["custo_revendedor"],
            "implantacao": resultado["implantacao"],
            "redes_sociais": resultado["redes_sociais"],
            "valor_cliente": resultado["valor_cliente"]
        }

        salvou_historico = salvar_em_aba(
            planilha,
            "orcamentos_revendedor",
            dados_historico,
            colunas_historico
        )

        colunas_orc = [
            "codigo", "data_emissao", "data_validade", "nome_cliente", "nome_revendedor",
            "conexoes", "usuarios", "valor_revendedor", "sugestao_final",
            "valor_implantacao", "redes_sociais", "meta"
        ]

        dados_orc = {
            "codigo": codigo_orcamento,
            "data_emissao": data_emissao_dt.strftime("%d/%m/%Y"),
            "data_validade": data_validade_dt.strftime("%d/%m/%Y"),
            "nome_cliente": nome_cliente,
            "nome_revendedor": nome_revendedor,
            "conexoes": conexoes,
            "usuarios": usuarios,
            "valor_revendedor": formatar_moeda(resultado["custo_revendedor"]),
            "sugestao_final": formatar_moeda(resultado["valor_cliente"]),
            "valor_implantacao": formatar_moeda(resultado["implantacao"]),
            "redes_sociais": formatar_moeda(resultado["redes_sociais"]),
            "meta": "Sim" if meta else "Não"
        }

        salvou_orc = salvar_em_aba(
            planilha,
            "orcamentos_revendedor",
            dados_orc,
            colunas_orc
        )

        dados_pdf = {
            "codigo": codigo_orcamento,
            "data_emissao": data_emissao_dt.strftime("%d/%m/%Y"),
            "data_validade": data_validade_dt.strftime("%d/%m/%Y"),
            "nome_cliente": nome_cliente,
            "nome_revendedor": nome_revendedor,
            "conexoes": conexoes,
            "usuarios": usuarios,
            "valor_revendedor": formatar_moeda(resultado["custo_revendedor"]),
            "sugestao_final": formatar_moeda(resultado["valor_cliente"]),
            "valor_implantacao": formatar_moeda(resultado["implantacao"]),
        }

        if salvou_historico and salvou_orc:
            st.session_state["ultimo_resultado"] = {
                "codigo": codigo_orcamento,
                "cliente": nome_cliente,
                "revendedor": nome_revendedor,
                "emissao": data_emissao_dt.strftime("%d/%m/%Y"),
                "validade": data_validade_dt.strftime("%d/%m/%Y"),
                "resultado": resultado,
                "pdf": gerar_pdf_orcamento(dados_pdf)
            }

if salvar_alteracao:
    if not nome_cliente.strip() or not nome_revendedor.strip():
        st.error("Preencha o nome do cliente e o nome do revendedor.")
    else:
        redes = {
            "instagram": instagram,
            "facebook": facebook,
            "telegram": telegram
        }

        resultado = calcular_custo(
            conexoes=conexoes,
            usuarios=usuarios,
            redes=redes,
            meta=meta,
            config_precos=config_precos,
            faixas_implantacao=faixas_implantacao
        )

        codigo_orcamento = st.session_state.get("codigo_em_edicao")
        data_emissao_dt = datetime.now()
        data_validade_dt = data_emissao_dt + timedelta(days=10)

        colunas_orc = [
            "codigo", "data_emissao", "data_validade", "nome_cliente", "nome_revendedor",
            "conexoes", "usuarios", "valor_revendedor", "sugestao_final",
            "valor_implantacao", "redes_sociais", "meta"
        ]

        dados_orc = {
            "codigo": codigo_orcamento,
            "data_emissao": data_emissao_dt.strftime("%d/%m/%Y"),
            "data_validade": data_validade_dt.strftime("%d/%m/%Y"),
            "nome_cliente": nome_cliente,
            "nome_revendedor": nome_revendedor,
            "conexoes": conexoes,
            "usuarios": usuarios,
            "valor_revendedor": formatar_moeda(resultado["custo_revendedor"]),
            "sugestao_final": formatar_moeda(resultado["valor_cliente"]),
            "valor_implantacao": formatar_moeda(resultado["implantacao"]),
            "redes_sociais": formatar_moeda(resultado["redes_sociais"]),
            "meta": "Sim" if meta else "Não"
        }

        sucesso = atualizar_linha_orcamento(
            planilha,
            "orcamentos_revendedor",
            codigo_orcamento,
            dados_orc,
            colunas_orc
        )

        if sucesso:
            dados_pdf = {
                "codigo": codigo_orcamento,
                "data_emissao": data_emissao_dt.strftime("%d/%m/%Y"),
                "data_validade": data_validade_dt.strftime("%d/%m/%Y"),
                "nome_cliente": nome_cliente,
                "nome_revendedor": nome_revendedor,
                "conexoes": conexoes,
                "usuarios": usuarios,
                "valor_revendedor": formatar_moeda(resultado["custo_revendedor"]),
                "sugestao_final": formatar_moeda(resultado["valor_cliente"]),
                "valor_implantacao": formatar_moeda(resultado["implantacao"]),
            }

            st.session_state["ultimo_resultado"] = {
                "codigo": codigo_orcamento,
                "cliente": nome_cliente,
                "revendedor": nome_revendedor,
                "emissao": data_emissao_dt.strftime("%d/%m/%Y"),
                "validade": data_validade_dt.strftime("%d/%m/%Y"),
                "resultado": resultado,
                "pdf": gerar_pdf_orcamento(dados_pdf)
            }

            st.session_state["modo_edicao"] = False
            st.session_state["codigo_em_edicao"] = None
            st.success("Orçamento atualizado com sucesso!")


if st.session_state["ultimo_resultado"] is not None:
    ult = st.session_state["ultimo_resultado"]
    resultado = ult["resultado"]

    st.success(f"Orçamento {ult['codigo']} gerado com sucesso.")

    col_res1, col_res2, col_res3 = st.columns(3)
    with col_res1:
        st.metric("💼 Valor Revendedor", formatar_moeda(resultado["custo_revendedor"]))
    with col_res2:
        st.metric("🔧 Implantação", formatar_moeda(resultado["implantacao"]))
    with col_res3:
        st.metric("🎯 Sugestão Final", formatar_moeda(resultado["valor_cliente"]))

    st.markdown("---")
    st.subheader("📋 Detalhamento comercial")
    st.write(f"**Código:** {ult['codigo']}")
    st.write(f"**Cliente:** {ult['cliente']}")
    st.write(f"**Revendedor:** {ult['revendedor']}")
    st.write(f"**Data de emissão:** {ult['emissao']}")
    st.write(f"**Validade:** {ult['validade']}")
    st.write(f"**Conexões:** {st.session_state.get('conexoes', 1)}")
    st.write(f"**Usuários:** {st.session_state.get('usuarios', 1)}")

    st.download_button(
        label="📄 Baixar PDF do orçamento",
        data=ult["pdf"],
        file_name=f"{ult['codigo']}.pdf",
        mime="application/pdf"
    )

st.markdown("---")
st.subheader("🔎 Consulta de orçamentos")

col_f1, col_f2 = st.columns(2)
with col_f1:
    filtro_revendedor = st.text_input("Filtrar por revendedor")
with col_f2:
    filtro_cliente = st.text_input("Filtrar por cliente")

df_orc = ler_aba_dataframe(
    planilha,
    "orcamentos_revendedor",
    [
        "codigo", "data_emissao", "data_validade", "nome_cliente", "nome_revendedor",
        "conexoes", "usuarios", "valor_revendedor", "sugestao_final",
        "valor_implantacao", "redes_sociais", "meta"
    ]
)

if not df_orc.empty:
    df_filtrado = df_orc.copy()

    st.markdown("### ✏️ Editar orçamento existente")

    codigos_orcamento = df_orc["codigo"].astype(str).tolist()
    codigo_editar = st.selectbox(
        "Selecione o orçamento para editar:",
        codigos_orcamento,
        key="select_codigo_editar"
    )

    linha_edicao = df_orc[df_orc["codigo"].astype(str) == str(codigo_editar)]

    if not linha_edicao.empty:
        item_edicao = linha_edicao.iloc[0].to_dict()

        st.button(
            "Carregar orçamento para edição",
            key="btn_carregar_orcamento_edicao",
            on_click=carregar_orcamento_para_edicao,
            args=(item_edicao,),
        )

    if st.session_state.get("modo_edicao", False):
        st.warning("Ao carregar um orçamento, marque novamente Instagram/Facebook/Telegram se esse orçamento tiver redes sociais, pois a aba comercial só guarda o valor total dessas redes.")

    if filtro_revendedor.strip():
        df_filtrado = df_filtrado[
            df_filtrado["nome_revendedor"].astype(str).str.contains(
                filtro_revendedor,
                case=False,
                na=False
            )
        ]

    if filtro_cliente.strip():
        df_filtrado = df_filtrado[
            df_filtrado["nome_cliente"].astype(str).str.contains(
                filtro_cliente,
                case=False,
                na=False
            )
        ]

    st.dataframe(df_filtrado, use_container_width=True)
else:
    st.info("Ainda não há orçamentos cadastrados.")

st.markdown("---")
st.caption("Sistema integrado com Google Sheets")
