import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

# 1. Definição de Constantes no topo
DB_FILE = "financas.db"
ANO = 2026
MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

st.set_page_config(page_title="Controle Financeiro 2026", layout="wide")

# 2. Inicialização e Conexão com o SQLite
def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS despesas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        categoria TEXT NOT NULL,
        mes TEXT NOT NULL,
        ano INTEGER NOT NULL,
        valor REAL NOT NULL,
        UNIQUE(categoria, mes, ano)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mes TEXT NOT NULL,
        ano INTEGER NOT NULL,
        valor REAL NOT NULL,
        UNIQUE(mes, ano)
    )
    """)
    conn.commit()
    conn.close()

# Garante a existência das tabelas ao abrir a aplicação
init_db()

# 3. Operações de Dados
def carregar_dados():
    conn = get_connection()
    df_desp = pd.read_sql_query("SELECT categoria, mes, valor FROM despesas WHERE ano = ?", conn, params=(ANO,))
    df_renda = pd.read_sql_query("SELECT mes, valor FROM rendas WHERE ano = ?", conn, params=(ANO,))
    conn.close()

    if df_desp.empty:
        df_pivot = pd.DataFrame(columns=["Despesa"] + MESES)
        totais = [0.0] * 12
    else:
        df_pivot = df_desp.pivot(index="categoria", columns="mes", values="valor").fillna(0.0)
        for m in MESES:
            if m not in df_pivot.columns:
                df_pivot[m] = 0.0
        df_pivot = df_pivot[MESES].reset_index().rename(columns={"categoria": "Despesa"})
        totais = [df_desp[df_desp["mes"] == m]["valor"].sum() for m in MESES]

    rendas_dict = dict(zip(df_renda["mes"], df_renda["valor"])) if not df_renda.empty else {}
    rendas = [rendas_dict.get(m, 0.0) for m in MESES]
    sobras = [r - t for r, t in zip(rendas, totais)]

    df_resumo = pd.DataFrame({
        "Mês": MESES,
        "Total Gasto": totais,
        "Renda": rendas,
        "Sobra": sobras
    })

    return df_pivot, df_resumo

def salvar_gasto(categoria: str, mes: str, valor: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO despesas (categoria, mes, ano, valor)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(categoria, mes, ano) DO UPDATE SET valor = excluded.valor
    """, (categoria, mes, ANO, valor))
    conn.commit()
    conn.close()

def adicionar_categoria(nova_categoria: str):
    conn = get_connection()
    cursor = conn.cursor()
    for m in MESES:
        cursor.execute("""
            INSERT OR IGNORE INTO despesas (categoria, mes, ano, valor)
            VALUES (?, ?, ?, 0.0)
        """, (nova_categoria, m, ANO))
    conn.commit()
    conn.close()

# 4. Interface Web
st.title("Painel Financeiro 2026 (SQLite)")
df_despesas, df_resumo = carregar_dados()

# Barra Lateral
st.sidebar.header("Lançar / Atualizar Gasto")
mes_sel = st.sidebar.selectbox("Selecione o Mês", MESES, index=7) # Default: Agosto

categorias = sorted(df_despesas["Despesa"].tolist()) if not df_despesas.empty else []
if categorias:
    cat_sel = st.sidebar.selectbox("Categoria", categorias)
    val_atual = float(df_despesas.loc[df_despesas["Despesa"] == cat_sel, mes_sel].values[0])
    novo_valor = st.sidebar.number_input("Valor (R$)", value=val_atual, step=10.0, format="%.2f")

    if st.sidebar.button("Salvar Valor"):
        salvar_gasto(cat_sel, mes_sel, novo_valor)
        st.sidebar.success(f"{cat_sel} atualizado para R$ {novo_valor:,.2f} em {mes_sel}!")
        st.rerun()
else:
    st.sidebar.info("Nenhuma despesa cadastrada ainda.")

st.sidebar.divider()
st.sidebar.subheader("Nova Categoria")
nova_cat = st.sidebar.text_input("Nome da nova despesa")
if st.sidebar.button("Adicionar Categoria"):
    if nova_cat.strip() and nova_cat.strip() not in categorias:
        adicionar_categoria(nova_cat.strip())
        st.sidebar.success(f"Categoria '{nova_cat.strip()}' criada!")
        st.rerun()
    elif nova_cat.strip() in categorias:
        st.sidebar.warning("Essa categoria já existe.")

# Painel Principal
st.subheader(f"Indicadores de {mes_sel}")
resumo_mes = df_resumo[df_resumo["Mês"] == mes_sel].iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric("Renda", f"R$ {resumo_mes['Renda']:,.2f}")
c2.metric("Total Gasto", f"R$ {resumo_mes['Total Gasto']:,.2f}")
c3.metric(
    "Sobra", 
    f"R$ {resumo_mes['Sobra']:,.2f}", 
    delta=f"{resumo_mes['Sobra']:,.2f}",
    delta_color="normal"
)

st.divider()

col_graf, col_evol = st.columns([1, 1])

with col_graf:
    st.subheader(f"Gastos em {mes_sel}")
    if not df_despesas.empty:
        df_grafico = df_despesas[["Despesa", mes_sel]].rename(columns={mes_sel: "Valor"})
        df_grafico = df_grafico[df_grafico["Valor"] > 0].sort_values(by="Valor", ascending=True)
        if not df_grafico.empty:
            fig_bar = px.bar(
                df_grafico,
                x="Valor",
                y="Despesa",
                orientation="h",
                text_auto=".2f"
            )
            fig_bar.update_layout(xaxis_tickprefix="R$ ")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Nenhum gasto registrado neste mês.")
    else:
        st.info("Nenhuma categoria disponível.")

with col_evol:
    st.subheader("Evolução Anual (Renda vs Gasto)")
    fig_evol = px.line(
        df_resumo,
        x="Mês",
        y=["Total Gasto", "Renda"],
        markers=True
    )
    fig_evol.update_layout(yaxis_tickprefix="R$ ")
    st.plotly_chart(fig_evol, use_container_width=True)

st.subheader("Matriz Geral de Despesas")
if not df_despesas.empty:
    st.dataframe(df_despesas.style.format({m: "R$ {:,.2f}" for m in MESES}), use_container_width=True)
else:
    st.warning("O banco de dados ainda não possui dados. Execute 'python3 migrate.py' se desejar carregar os dados da planilha.")