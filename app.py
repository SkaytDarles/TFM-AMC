import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

import pandas as pd
import plotly.express as px
import datetime
import time
import json
import hashlib
import re

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

import google.generativeai as genai
from duckduckgo_search import DDGS

import feedparser
import trafilatura

# =========================================================
# 0) HELPERS DE SECRETS (no hardcode)
# =========================================================
def secret_get(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

# =========================================================
# 1) CONFIGURACIÓN Y ESTILOS (UI/UX)
# =========================================================
st.set_page_config(
    page_title="AMC Intelligence Hub",
    page_icon="🔓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div.stButton > button {
        background-color: #0d1117;
        color: #00c1a9;
        border: 1px solid #00c1a9;
        border-radius: 6px;
        transition: all 0.3s ease;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    div.stButton > button:hover {
        background-color: #00c1a9;
        color: #ffffff;
        box-shadow: 0px 0px 10px rgba(0, 193, 169, 0.5);
        border-color: #00c1a9;
    }
    div.stButton > button:active { transform: scale(0.98); }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: #0d1117; color: #8b949e;
        border: 1px solid #30363d; border-radius: 6px 6px 0px 0px;
        padding: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #161b22 !important; color: #00c1a9 !important;
        border: 1px solid #00c1a9; border-bottom: none;
    }

    h1 { color: #00c1a9 !important; }
    h2, h3 { color: #e6edf3 !important; }
    p, span, div, label { color: #c9d1d9; }

    .stTextInput > div > div > input {
        background-color: #0d1117; color: white; border-color: #30363d;
    }

    .ia-badge {
        background-color: #21262d; padding: 4px 10px; border-radius: 12px;
        font-size: 0.8rem; border: 1px solid #30363d; display: inline-block; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 2) CONFIG MVP (MEJOR DE AMBOS: Web + RSS + IA + Depts)
# =========================================================
MIN_SCORE_IA = 75
MAX_RESULTS_PER_DEPT_WEB = 2          # DDG por dept (barato)
MAX_ITEMS_PER_RSS_SOURCE = 25         # RSS por fuente
MAX_IA_CALLS_PER_RUN = 40             # límite total IA (control costo)
MIN_TEXT_CHARS = 800                  # si no hay texto suficiente, se descarta
SLEEP_BETWEEN_CALLS = 0.35            # suaviza rate

LISTA_DEPARTAMENTOS = [
    "Finanzas y ROI",
    "FoodTech and Supply Chain",
    "Innovación y Tendencias",
    "Tecnología e Innovación",
    "Legal & Regulatory Affairs / Innovation"
]

COLORES_DEPT = {
    "Finanzas y ROI": "#FFD700",
    "FoodTech and Supply Chain": "#00C2FF",
    "Innovación y Tendencias": "#BD00FF",
    "Tecnología e Innovación": "#00E676",
    "Legal & Regulatory Affairs / Innovation": "#FF5252"
}

# Queries por dept para DDG (tu lógica actual, buena para “web abierta”)
QUERIES_DEPT = {
    "Finanzas y ROI": "retorno inversión automatización alimentos",
    "FoodTech and Supply Chain": "tecnología cadena suministro alimentos",
    "Innovación y Tendencias": "tendencias industria alimentos 2025",
    "Tecnología e Innovación": "inteligencia artificial manufactura industrial",
    "Legal & Regulatory Affairs / Innovation": "ley etiquetado alimentos normativa tecnología"
}

# Fuentes RSS/Atom (lo que te recomendé: estable y replicable)
RSS_SOURCES = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "TheVerge", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "Wired_AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "GoogleResearch_Atom", "url": "https://blog.research.google/atom.xml"},
    {"name": "arXiv_csAI", "url": "https://rss.arxiv.org/rss/cs.AI"},
    {"name": "arXiv_csLG", "url": "https://rss.arxiv.org/rss/cs.LG"},
]

# Prefiltro barato (antes de gastar IA)
KEYWORDS_PREFILTER = [
    "ai", "artificial intelligence", "machine learning",
    "generative", "llm", "agent", "rag", "embedding",
    "mlops", "data platform", "governance", "security",
    "automation", "digital transformation", "cloud"
]

TOPICS_MVP = [
    "LLMs & Agents", "RAG & Search", "MLOps & Observability",
    "Data Platforms", "Security & Governance", "Automation",
    "Regulation", "Productivity Tools"
]

# =========================================================
# 3) UTILIDADES (hash, json, url, fecha)
# =========================================================
def hash_pass(password: str) -> str:
    return hashlib.sha256(str.encode(password)).hexdigest()

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

def limpiar_json(texto: str):
    try:
        start = texto.find('{')
        end = texto.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(texto[start:end])
        return None
    except Exception:
        return None

def normalize_url(url: str) -> str:
    url = (url or "").strip()
    url = re.sub(r"[?&](utm_[^=]+=[^&]+)", "", url, flags=re.I)
    url = re.sub(r"[?&]fbclid=[^&]+", "", url, flags=re.I)
    return url.rstrip("?&")

def keyword_prefilter(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in KEYWORDS_PREFILTER)

def safe_time_str(ts) -> str:
    if ts is None:
        return "--:--"
    try:
        if isinstance(ts, datetime.datetime):
            return ts.strftime("%H:%M")
        # si viniera como string
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except Exception:
        return "--:--"

# =========================================================
# 4) FIREBASE (con tu patrón actual)
# =========================================================
@st.cache_resource
def init_connection():
    try:
        if not firebase_admin._apps:
            if "FIREBASE_KEY" in st.secrets:
                key_dict = dict(st.secrets["FIREBASE_KEY"])
                if "private_key" in key_dict:
                    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            else:
                cred = credentials.Certificate("serviceAccountKey.json")
                firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"❌ Error DB: {e}")
        return None

db = init_connection()

# =========================================================
# 5) GEMINI (usa tu lib actual google-generativeai)
# =========================================================
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

@st.cache_resource
def get_gemini_model():
    # puedes cambiar a gemini-1.5-flash / gemini-2.0-flash si lo tienes
    return genai.GenerativeModel("gemini-1.5-flash")

# =========================================================
# 6) PIPELINE: FUENTES + EXTRACCIÓN + IA + FIRESTORE
# =========================================================
def analizar_con_gemini(texto: str, titulo: str, dept_context: str):
    """
    Devuelve análisis en JSON, pero con campos compatibles con tu dashboard actual.
    """
    if "GOOGLE_API_KEY" not in st.secrets:
        return {
            "titulo_mejorado": titulo,
            "resumen": (texto or "")[:200],
            "accion": "Configurar API Key",
            "score": 50,
            "departamento": dept_context,
            "topics": [],
            "confidence": 0.3
        }

    model = get_gemini_model()

    prompt = f"""
Eres un analista de inteligencia competitiva para AMC Global.
Clasifica y resume noticias sobre IA, digitalización y tecnología aplicada al negocio.

CONTEXTO DEPARTAMENTO (si aplica): {dept_context}

Devuelve SOLO JSON válido (sin markdown) con este esquema:
{{
  "titulo_mejorado": "Título breve en español",
  "resumen": "Resumen ejecutivo ~30 palabras",
  "accion": "Sugerencia estratégica concreta (1 frase)",
  "score": 0-100,
  "departamento": one_of({LISTA_DEPARTAMENTOS}),
  "topics": array_from({TOPICS_MVP}) (máx 3),
  "confidence": 0.0-1.0
}}

REGLAS:
- Si es clickbait u opinión vacía -> score bajo.
- Prioriza IA aplicada, automatización, gobernanza, seguridad, regulación, productividad.
- Si dept_context no cuadra, elige el departamento correcto.

NOTICIA:
TÍTULO: {titulo}

TEXTO:
{(texto or "")[:1200]}
""".strip()

    try:
        response = model.generate_content(prompt)
        data = limpiar_json(response.text)
        if data:
            # normaliza campos mínimos
            data.setdefault("titulo_mejorado", titulo)
            data.setdefault("resumen", (texto or "")[:200])
            data.setdefault("accion", "Revisar")
            data.setdefault("score", 50)
            data.setdefault("departamento", dept_context if dept_context in LISTA_DEPARTAMENTOS else LISTA_DEPARTAMENTOS[0])
            data.setdefault("topics", [])
            data.setdefault("confidence", 0.5)
            return data
    except Exception:
        pass

    return {
        "titulo_mejorado": titulo,
        "resumen": "Error IA",
        "accion": "Revisar",
        "score": 50,
        "departamento": dept_context if dept_context in LISTA_DEPARTAMENTOS else LISTA_DEPARTAMENTOS[0],
        "topics": [],
        "confidence": 0.3
    }

def extraer_texto_url(url: str) -> str:
    """
    Extrae texto real del artículo (RSS/DDG) usando trafilatura.
    """
    try:
        downloaded = trafilatura.fetch_url(url, timeout=20)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_tables=False, include_comments=False) or ""
        return text.strip()
    except Exception:
        return ""

def existe_por_url(db, url: str) -> bool:
    """
    Dedup robusto por URL hash (no por título).
    """
    doc_id = sha1(normalize_url(url))
    doc = db.collection("news_articles").document(doc_id).get()
    return doc.exists

def guardar_noticia(db, *, title: str, url: str, source: str, dept_context: str, body_hint: str):
    """
    Analiza con Gemini y guarda en news_articles usando doc_id determinístico.
    """
    url = normalize_url(url)
    doc_id = sha1(url)

    if db.collection("news_articles").document(doc_id).get().exists:
        return False  # ya existe

    # intenta extraer texto real
    full_text = extraer_texto_url(url)
    texto_para_ia = full_text if len(full_text) >= MIN_TEXT_CHARS else (body_hint or "")

    if len(texto_para_ia or "") < 200:
        # no hay material suficiente ni para IA
        return False

    analisis = analizar_con_gemini(texto_para_ia, title, dept_context)
    final_title = analisis.get("titulo_mejorado", title)
    final_dept = analisis.get("departamento", dept_context)
    final_score = int(analisis.get("score", 50) or 50)

    payload = {
        "title": final_title,
        "url": url,
        "published_at": datetime.datetime.now(),
        "source": source,
        "analysis": {
            "departamento": final_dept,
            "resumen_ejecutivo": analisis.get("resumen", ""),
            "accion_sugerida": analisis.get("accion", ""),
            "relevancia_score": final_score,
            "topics": analisis.get("topics", []),
            "confidence": analisis.get("confidence", 0.5),
        }
    }

    db.collection("news_articles").document(doc_id).set(payload, merge=True)
    time.sleep(SLEEP_BETWEEN_CALLS)
    return True

def scan_web_abierta(db, mis_intereses, max_results_per_dept=MAX_RESULTS_PER_DEPT_WEB):
    """
    Escaneo por DDG (tu lógica), pero mejorada:
    - dedup por url hash
    - intenta extraer texto real del link
    """
    ddgs = DDGS()
    count_news = 0

    # si el usuario filtró intereses, escanea solo esos
    deptos_a_escanear = [d for d in QUERIES_DEPT.keys() if (not mis_intereses or d in mis_intereses)]

    progress_text = "🕵️ Iniciando escaneo (Web Abierta)..."
    my_bar = st.progress(0, text=progress_text)
    total_steps = max(1, len(deptos_a_escanear))
    current_step = 0

    calls = 0

    for dept in deptos_a_escanear:
        current_step += 1
        my_bar.progress(int((current_step / total_steps) * 100), text=f"Web Abierta: {dept}")

        query = QUERIES_DEPT.get(dept, "")
        if not query:
            continue

        try:
            resultados = list(ddgs.text(
                f"{query} noticias recientes",
                region="wt-wt",
                timelimit="d",
                max_results=max_results_per_dept
            ))

            for r in resultados:
                if calls >= MAX_IA_CALLS_PER_RUN:
                    break

                titulo = r.get("title")
                link = r.get("href")
                body = r.get("body") or ""

                if not titulo or not link:
                    continue

                if existe_por_url(db, link):
                    continue

                # prefiltro barato
                if not keyword_prefilter(f"{titulo} {body}"):
                    continue

                ok = guardar_noticia(
                    db,
                    title=titulo,
                    url=link,
                    source="Web Abierta",
                    dept_context=dept,
                    body_hint=body
                )
                if ok:
                    count_news += 1
                    calls += 1

        except Exception:
            continue

        if calls >= MAX_IA_CALLS_PER_RUN:
            break

    my_bar.empty()
    return count_news

def scan_rss(db, mis_intereses):
    """
    Escaneo RSS/Atom + extracción real del artículo.
    Department se decide por Gemini (AUTO) para que sea replicable.
    """
    count_news = 0
    calls = 0

    progress_text = "📰 Iniciando escaneo (RSS/Atom)..."
    my_bar = st.progress(0, text=progress_text)

    total_steps = max(1, len(RSS_SOURCES))
    for i, src in enumerate(RSS_SOURCES, start=1):
        my_bar.progress(int((i / total_steps) * 100), text=f"RSS: {src['name']}")

        feed = feedparser.parse(src["url"])
        entries = (feed.entries or [])[:MAX_ITEMS_PER_RSS_SOURCE]

        for e in entries:
            if calls >= MAX_IA_CALLS_PER_RUN:
                break

            url = normalize_url(getattr(e, "link", "") or "")
            if not url:
                continue

            title = (getattr(e, "title", "") or "").strip()
            summary = (getattr(e, "summary", "") or "").strip()

            if not title:
                continue

            if existe_por_url(db, url):
                continue

            # prefiltro barato
            if not keyword_prefilter(f"{title} {summary}"):
                continue

            # dept_context AUTO: Gemini decide el dept final
            ok = guardar_noticia(
                db,
                title=title,
                url=url,
                source=src["name"],
                dept_context="Innovación y Tendencias",  # “seed” seguro; Gemini puede cambiarlo
                body_hint=summary
            )
            if ok:
                count_news += 1
                calls += 1

        if calls >= MAX_IA_CALLS_PER_RUN:
            break

    my_bar.empty()
    return count_news

def buscador_inteligente_maestro(db, mis_intereses, usar_web=True, usar_rss=True):
    """
    Combina lo mejor de ambos mundos:
    - DDG Web Abierta (rápido, flexible)
    - RSS/Atom (estable, replicable)
    """
    total = 0
    if usar_web:
        total += scan_web_abierta(db, mis_intereses)
    if usar_rss:
        total += scan_rss(db, mis_intereses)
    return total

# =========================================================
# 7) EMAIL INTELIGENTE (seguro: lee secrets)
# =========================================================
def enviar_reporte_email(news_list, dest):
    if not news_list:
        return False

    smtp_email = secret_get("SMTP_EMAIL")
    smtp_pass = secret_get("SMTP_APP_PASSWORD")
    smtp_host = secret_get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(secret_get("SMTP_PORT", 587))

    if not smtp_email or not smtp_pass:
        st.error("Faltan SMTP_EMAIL / SMTP_APP_PASSWORD en st.secrets")
        return False

    fecha_str = datetime.datetime.now().strftime("%d %b")
    deptos = list(set([n.get("analysis", {}).get("departamento", "General") for n in news_list]))
    cat_str = deptos[0] if len(deptos) == 1 else "Resumen Ejecutivo"
    subject = f"AMC Daily: {cat_str} - {fecha_str}"

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_email
        msg["To"] = dest
        msg["Subject"] = Header(subject, "utf-8")

        rows = ""
        for n in news_list:
            analisis = n.get("analysis", {})
            dept = analisis.get("departamento", "General")
            color = COLORES_DEPT.get(dept, "#333")
            rows += f"""
            <tr>
                <td style="padding:15px; border-bottom:1px solid #eee;">
                    <span style="color:{color}; font-size:10px; font-weight:bold;">{dept.upper()}</span>
                    <h3 style="margin:5px 0; color:#333;">{n.get('title','')}</h3>
                    <p style="color:#666; font-size:14px;">{analisis.get('resumen_ejecutivo','')}</p>
                    <a href="{n.get('url','')}" style="color:#00c1a9; text-decoration:none; font-size:12px;">🔗 Leer fuente</a>
                </td>
            </tr>
            """

        html = f"""
        <div style="font-family:Helvetica, sans-serif; max-width:600px; margin:0 auto; border:1px solid #e0e0e0;">
            <div style="background:#161b22; padding:20px; text-align:center;">
                <h2 style="color:#00c1a9; margin:0;">AMC INTELLIGENCE</h2>
                <p style="color:#888; font-size:12px;">{fecha_str}</p>
            </div>
            <div style="padding:20px;">
                <p>Hola, aquí tienes la selección de noticias:</p>
                <table style="width:100%; border-collapse:collapse;">{rows}</table>
            </div>
        </div>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_email, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True

    except Exception as e:
        st.error(f"Error enviando a {dest}: {e}")
        return False

# =========================================================
# 8) LOGIN / REGISTRO (tu lógica)
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_info" not in st.session_state:
    st.session_state["user_info"] = {}

def main_login():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><h1 style='text-align:center;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["🔐 INGRESAR", "📝 REGISTRARSE"])

        with tab1:
            with st.form("login_form"):
                email = st.text_input("Usuario (Email)")
                password = st.text_input("Contraseña", type="password")
                if st.form_submit_button("ACCESO"):
                    if not db:
                        st.stop()
                    doc = db.collection("users").document(email).get()
                    if doc.exists:
                        data = doc.to_dict()
                        if data.get("password") == hash_pass(password):
                            st.session_state["logged_in"] = True
                            st.session_state["user_email"] = email
                            st.session_state["user_info"] = data
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
                    else:
                        st.error("Usuario no encontrado.")

        with tab2:
            with st.form("register_form"):
                st.markdown("### Nueva Cuenta")
                new_email = st.text_input("Email Corporativo")
                new_name = st.text_input("Nombre Completo")
                new_pass = st.text_input("Definir Contraseña", type="password")
                st.markdown("**Intereses:**")
                new_intereses = st.multiselect("Departamentos", LISTA_DEPARTAMENTOS, default=LISTA_DEPARTAMENTOS)

                if st.form_submit_button("CREAR CUENTA"):
                    if new_email and new_name and new_pass:
                        if not db.collection("users").document(new_email).get().exists:
                            final_intereses = new_intereses if new_intereses else LISTA_DEPARTAMENTOS
                            db.collection("users").document(new_email).set({
                                "nombre": new_name,
                                "password": hash_pass(new_pass),
                                "intereses": final_intereses,
                                "created_at": datetime.datetime.now()
                            })
                            st.success("Cuenta creada. Ingresa en la pestaña 'INGRESAR'.")
                        else:
                            st.warning("Usuario ya existe.")

# =========================================================
# 9) DASHBOARD PRINCIPAL (tu UI, con “Escanear Maestro”)
# =========================================================
def main_app():
    user = st.session_state["user_info"]
    if "selected_news" not in st.session_state:
        st.session_state["selected_news"] = set()

    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"👤 {user.get('nombre', 'Analista')}")

        if st.button("🚪 Cerrar Sesión"):
            st.session_state["logged_in"] = False
            st.rerun()

        st.divider()
        filtro_tiempo = st.radio("Período:", ["Hoy (Tiempo Real)", "Ayer", "Histórico 7 días"])
        mis_intereses = st.multiselect("Filtro Áreas:", LISTA_DEPARTAMENTOS, default=user.get("intereses", [])[:3])

        st.divider()

        st.markdown("### 🧠 Motor de Escaneo")
        usar_web = st.toggle("Web Abierta (DDG)", value=True)
        usar_rss = st.toggle("RSS/Atom (Estable)", value=True)

        c_scan, c_save = st.columns(2)
        with c_scan:
            if st.button("🔄 Escanear"):
                with st.spinner("Escaneando fuentes..."):
                    n = buscador_inteligente_maestro(db, mis_intereses, usar_web=usar_web, usar_rss=usar_rss)
                    st.toast(f"Escaneo completado: {n} nuevas.", icon="✅")
                    time.sleep(1)
                    st.rerun()

        with c_save:
            if st.button("💾 Guardar"):
                db.collection("users").document(st.session_state["user_email"]).update({"intereses": mis_intereses})
                st.session_state["user_info"]["intereses"] = mis_intereses
                st.toast("Preferencias guardadas")

        st.markdown("---")

        st.markdown("### 📤 Configuración de Envío")
        opcion_destinatario = st.radio(
            "Seleccionar Destinatarios:",
            ["Mi Correo (Usuario Actual)", "Ingresar Correo Manualmente", "Cargar Lista (Excel/CSV)"]
        )

        lista_destinatarios = []

        if opcion_destinatario == "Mi Correo (Usuario Actual)":
            lista_destinatarios = [st.session_state["user_email"]]
            st.info(f"Se enviará a: {st.session_state['user_email']}")

        elif opcion_destinatario == "Ingresar Correo Manualmente":
            email_manual = st.text_input("Escribe el correo destinatario:")
            if email_manual:
                lista_destinatarios = [email_manual]

        elif opcion_destinatario == "Cargar Lista (Excel/CSV)":
            uploaded_file = st.file_uploader("Sube tu archivo", type=["csv", "xlsx"])
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith(".csv"):
                        df_upload = pd.read_csv(uploaded_file)
                    else:
                        df_upload = pd.read_excel(uploaded_file)

                    posibles_cols = [c for c in df_upload.columns if "email" in c.lower() or "correo" in c.lower()]
                    col_email = posibles_cols[0] if posibles_cols else df_upload.columns[0]

                    lista_destinatarios = df_upload[col_email].dropna().astype(str).tolist()
                    st.success(f"Cargados {len(lista_destinatarios)} destinatarios desde columna '{col_email}'.")
                except Exception as e:
                    st.error(f"Error leyendo archivo: {e}")

        st.markdown("---")

        count_sel = len(st.session_state["selected_news"])
        label_email = f"🚀 Enviar ({count_sel})" if count_sel > 0 else "🚀 Enviar Selección"

        if st.button(label_email, disabled=(count_sel == 0)):
            if not lista_destinatarios:
                st.error("⚠️ No hay destinatarios definidos.")
            elif "news_cache" in st.session_state:
                to_send = [n for n in st.session_state["news_cache"] if n.get("title") in st.session_state["selected_news"]]

                my_bar = st.progress(0, text="Enviando reportes...")
                exitos, fallos = 0, 0

                for i, dest in enumerate(lista_destinatarios):
                    progreso = int(((i + 1) / len(lista_destinatarios)) * 100)
                    my_bar.progress(progreso, text=f"Enviando a {dest}...")

                    if enviar_reporte_email(to_send, dest):
                        exitos += 1
                    else:
                        fallos += 1

                my_bar.empty()

                if exitos > 0:
                    st.toast(f"✅ Enviado con éxito a {exitos} destinatarios!", icon="🚀")
                    st.session_state["selected_news"] = set()
                    if fallos > 0:
                        st.warning(f"Hubo {fallos} envíos fallidos.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Falló el envío a todos los destinatarios.")

    # ===========================
    # CONTENIDO CENTRAL
    # ===========================
    st.title("Centro de Inteligencia")

    hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query = db.collection("news_articles")

    # Firestore: 'in' máximo 10 elementos; tu default usa 3 -> ok
    if mis_intereses:
        query = query.where(filter=FieldFilter("analysis.departamento", "in", mis_intereses[:10]))

    if filtro_tiempo == "Hoy (Tiempo Real)":
        query = query.where(filter=FieldFilter("published_at", ">=", hoy))
    elif filtro_tiempo == "Ayer":
        ayer = hoy - datetime.timedelta(days=1)
        query = query.where(filter=FieldFilter("published_at", ">=", ayer)).where(filter=FieldFilter("published_at", "<", hoy))
    elif filtro_tiempo == "Histórico 7 días":
        week = hoy - datetime.timedelta(days=7)
        query = query.where(filter=FieldFilter("published_at", ">=", week))

    docs = query.order_by("published_at", direction=firestore.Query.DESCENDING).limit(50).stream()
    lista_noticias = [d.to_dict() for d in docs]
    st.session_state["news_cache"] = lista_noticias

    tab_news, tab_metrics = st.tabs(["📰 Feed de Noticias", "📊 Métricas"])

    with tab_news:
        if not lista_noticias:
            st.info("📭 Sin noticias. Usa el botón '🔄 Escanear' en la barra lateral.")
        else:
            col_ia_1, col_ia_2 = st.columns([3, 1])
            with col_ia_2:
                if st.button(f"✨ Auto-selección IA (>{MIN_SCORE_IA})"):
                    added = 0
                    for n in lista_noticias:
                        if n.get("analysis", {}).get("relevancia_score", 0) > MIN_SCORE_IA:
                            st.session_state["selected_news"].add(n.get("title"))
                            added += 1
                    st.toast(f"IA seleccionó {added} noticias relevantes.", icon="🤖")
                    time.sleep(0.8)
                    st.rerun()

            for n in lista_noticias:
                title = n.get("title", "Sin título")
                a = n.get("analysis", {})
                dept = a.get("departamento", "General")
                color = COLORES_DEPT.get(dept, "#888")
                score = a.get("relevancia_score", 0)
                published_at = n.get("published_at")

                is_checked = title in st.session_state["selected_news"]

                with st.container():
                    c_chk, c_line, c_content = st.columns([0.2, 0.1, 4])

                    with c_chk:
                        if st.checkbox("", value=is_checked, key=f"chk_{sha1(title)}"):
                            st.session_state["selected_news"].add(title)
                        else:
                            st.session_state["selected_news"].discard(title)

                    with c_line:
                        st.markdown(f"<div style='height:100%; width:4px; background-color:{color}; border-radius:4px;'></div>", unsafe_allow_html=True)

                    with c_content:
                        st.markdown(f"### [{title}]({n.get('url', '')})")
                        st.caption(f"**{dept}** • {safe_time_str(published_at)}")
                        st.markdown(f"{a.get('resumen_ejecutivo', '...')}")

                        badge_color = "#00E676" if score > MIN_SCORE_IA else "#c9d1d9"
                        border_color = "#00E676" if score > MIN_SCORE_IA else "#444"

                        accion = a.get("accion_sugerida", "Revisar")
                        st.markdown(f"""
                        <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
                            <span style="background:rgba(0,193,169,0.1); color:#00c1a9; padding:2px 8px; border-radius:4px; font-size:0.85em;">
                                💡 {accion}
                            </span>
                            <span class="ia-badge" style="color:{badge_color}; border-color:{border_color};">
                                IA Score: {score}/100
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                    st.divider()

    with tab_metrics:
        if lista_noticias:
            df = pd.DataFrame([n.get("analysis", {}) for n in lista_noticias if "analysis" in n])
            if not df.empty and "departamento" in df.columns and "relevancia_score" in df.columns:
                c1, c2 = st.columns(2)
                with c1:
                    st.plotly_chart(
                        px.pie(df, names="departamento", color="departamento",
                               color_discrete_map=COLORES_DEPT, hole=0.4),
                        use_container_width=True
                    )
                with c2:
                    st.plotly_chart(
                        px.bar(df.groupby("departamento")["relevancia_score"].mean().reset_index(),
                               x="departamento", y="relevancia_score", color="departamento",
                               color_discrete_map=COLORES_DEPT),
                        use_container_width=True
                    )

# =========================================================
# 10) ENTRYPOINT
# =========================================================
if __name__ == "__main__":
    if st.session_state["logged_in"]:
        main_app()
    else:
        main_login()
