import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import pandas as pd
import plotly.express as px
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import time
import json
import hashlib
import google.generativeai as genai
from duckduckgo_search import DDGS

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS (CORREGIDOS PARA DARK MODE)
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="🔓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS PERSONALIZADO ---
# Aquí es donde cambiamos los colores para que coincidan con el tema oscuro
st.markdown("""
<style>
    /* 1. Botones (Estilo Dark/Teal) */
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
    div.stButton > button:active {
        transform: scale(0.98);
    }

    /* 2. Pestañas (Tabs) - CORRECCIÓN DEL FONDO BLANCO */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    
    /* Pestaña NO seleccionada */
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #0d1117; /* Fondo oscuro */
        color: #8b949e; /* Texto gris */
        border: 1px solid #30363d;
        border-radius: 6px 6px 0px 0px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    /* Pestaña SELECCIONADA */
    .stTabs [aria-selected="true"] {
        background-color: #161b22 !important; /* Fondo un poco más claro pero oscuro */
        color: #00c1a9 !important; /* Texto Teal */
        border: 1px solid #00c1a9;
        border-bottom: none;
    }

    /* 3. Ajustes generales del Dashboard */
    h1 { color: #00c1a9 !important; }
    h2, h3 { color: #e6edf3 !important; }
    p, span, div { color: #c9d1d9; }
    
    /* Badges */
    .ia-badge {
        background-color: #21262d;
        color: #00c1a9;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        border: 1px solid #30363d;
        display: inline-block;
        font-weight: bold;
    }
    
    /* Inputs de texto (Login) */
    .stTextInput > div > div > input {
        background-color: #0d1117;
        color: white;
        border-color: #30363d;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
REMITENTE_PASSWORD = "dgwafnrnahcvgpjz" 

LISTA_DEPARTAMENTOS = [
    "Finanzas y ROI", 
    "FoodTech and Supply Chain", 
    "Innovación y Tendencias", 
    "Tecnología e Innovación", 
    "Legal & Regulatory Affairs / Innovation"
]

COLORES_DEPT = {
    "Finanzas y ROI": "#FFD700", "FoodTech and Supply Chain": "#00C2FF",
    "Innovación y Tendencias": "#BD00FF", "Tecnología e Innovación": "#00E676",
    "Legal & Regulatory Affairs / Innovation": "#FF5252"
}

QUERIES_DEPT = {
    "Finanzas y ROI": "retorno inversión automatización alimentos",
    "FoodTech and Supply Chain": "tecnología cadena suministro alimentos",
    "Innovación y Tendencias": "tendencias industria alimentos 2025",
    "Tecnología e Innovación": "inteligencia artificial manufactura industrial",
    "Legal & Regulatory Affairs / Innovation": "ley etiquetado alimentos normativa tecnología"
}

# ==========================================
# 2. UTILIDADES
# ==========================================
def hash_pass(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def limpiar_json(texto):
    try:
        start = texto.find('{')
        end = texto.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(texto[start:end])
        return None
    except: return None

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
                cred = credentials.Certificate('serviceAccountKey.json')
                firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"❌ Error DB: {e}")
        return None

db = init_connection()

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# ==========================================
# 3. LÓGICA DE NEGOCIO
# ==========================================
def analizar_con_gemini(texto, titulo, dept):
    if "GOOGLE_API_KEY" not in st.secrets:
        return {"titulo_mejorado": titulo, "resumen": texto[:200], "accion": "Configurar API Key", "score": 50}

    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Eres un analista de inteligencia competitiva para AMC Global ({dept}).
    Analiza: {titulo}
    Texto: {texto[:800]}...

    Salida JSON:
    {{
        "titulo_mejorado": "Título breve en español",
        "resumen": "Resumen ejecutivo de 30 palabras.",
        "accion": "Sugerencia estratégica.",
        "score": (número entero 0-100)
    }}
    """
    try:
        response = model.generate_content(prompt)
        data = limpiar_json(response.text)
        if data: return data
    except: pass
    
    return {"titulo_mejorado": titulo, "resumen": "Error IA", "accion": "Revisar", "score": 50}

def buscador_inteligente():
    count_news = 0
    ddgs = DDGS()
    news_batch = [] 
    
    progress_text = "Iniciando escaneo de fuentes abiertas..."
    my_bar = st.progress(0, text=progress_text)

    total_steps = len(QUERIES_DEPT)
    current_step = 0
    
    for dept, query in QUERIES_DEPT.items():
        current_step += 1
        my_bar.progress(int((current_step / total_steps) * 100), text=f"Escaneando: {dept}")
        
        try:
            resultados = list(ddgs.text(f"{query} noticias recientes", region="wt-wt", timelimit="d", max_results=2))
            
            for r in resultados:
                titulo = r.get('title')
                link = r.get('href')
                body = r.get('body')

                if not titulo or not link: continue
                
                docs = db.collection('news_articles').where(filter=FieldFilter('title', '==', titulo)).limit(1).stream()
                if list(docs): continue

                analisis = analizar_con_gemini(body, titulo, dept)
                
                doc_data = {
                    "title": analisis.get('titulo_mejorado', titulo),
                    "url": link,
                    "published_at": datetime.datetime.now(),
                    "source": "Web Abierta",
                    "analysis": {
                        "departamento": dept,
                        "resumen_ejecutivo": analisis.get('resumen'),
                        "accion_sugerida": analisis.get('accion'),
                        "relevancia_score": analisis.get('score')
                    }
                }
                
                db.collection('news_articles').add(doc_data)
                news_batch.append(doc_data)
                count_news += 1
                time.sleep(0.5)
                
        except Exception: continue

    my_bar.empty()
    return news_batch

def enviar_reporte_email(news_list, dest, nombre):
    if not news_list: return False
    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = dest
        msg['Subject'] = Header(f"🔓 AMC Daily: {len(news_list)} Nuevos Insights", 'utf-8')

        rows = ""
        for n in news_list:
            analisis = n.get('analysis', {})
            color = COLORES_DEPT.get(analisis.get('departamento'), "#333")
            rows += f"""
            <tr>
                <td style="padding:15px; border-bottom:1px solid #eee;">
                    <span style="color:{color}; font-size:10px; font-weight:bold;">{analisis.get('departamento', '').upper()}</span>
                    <h3 style="margin:5px 0; color:#333;">{n.get('title')}</h3>
                    <p style="color:#666; font-size:14px;">{analisis.get('resumen_ejecutivo')}</p>
                    <a href="{n.get('url')}" style="color:#00c1a9; text-decoration:none; font-size:12px;">🔗 Leer fuente</a>
                </td>
            </tr>
            """

        html = f"""
        <div style="font-family:Helvetica, sans-serif; max-width:600px; margin:0 auto; border:1px solid #e0e0e0;">
            <div style="background:#161b22; padding:20px; text-align:center;">
                <h2 style="color:#00c1a9; margin:0;">AMC INTELLIGENCE</h2>
            </div>
            <div style="padding:20px;">
                <p>Hola {nombre}, resumen de inteligencia:</p>
                <table style="width:100%; border-collapse:collapse;">{rows}</table>
            </div>
        </div>
        """
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(REMITENTE_EMAIL, REMITENTE_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except: return False

# ==========================================
# 4. LOGIN
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = {}

def main_login():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><h1 style='text-align:center;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        # TABS AHORA TENDRÁN EL COLOR OSCURO DEFINIDO EN CSS
        tab1, tab2 = st.tabs(["🔐 INGRESAR", "📝 REGISTRARSE"])
        
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Usuario (Email)")
                password = st.text_input("Contraseña", type="password")
                if st.form_submit_button("ACCESO"):
                    if not db: st.stop()
                    doc = db.collection('users').document(email).get()
                    if doc.exists and (doc.to_dict().get('password') == password or doc.to_dict().get('password') == hash_pass(password)):
                        st.session_state['logged_in'] = True
                        st.session_state['user_email'] = email
                        st.session_state['user_info'] = doc.to_dict()
                        st.rerun()
                    else: st.error("Datos incorrectos.")

        with tab2:
            with st.form("register_form"):
                new_email = st.text_input("Email Corporativo")
                new_name = st.text_input("Nombre Completo")
                new_pass = st.text_input("Definir Contraseña", type="password")
                if st.form_submit_button("CREAR CUENTA"):
                    if new_email and new_name and new_pass:
                        if not db.collection('users').document(new_email).get().exists:
                            db.collection('users').document(new_email).set({
                                "nombre": new_name, "password": hash_pass(new_pass),
                                "intereses": LISTA_DEPARTAMENTOS, "created_at": datetime.datetime.now()
                            })
                            st.success("Cuenta creada. Ingresa en la otra pestaña.")
                        else: st.warning("Usuario ya existe.")

# ==========================================
# 5. DASHBOARD PRINCIPAL
# ==========================================
def main_app():
    user = st.session_state['user_info']
    
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"👤 {user.get('nombre', 'Analista')}")
        
        if st.button("🚪 Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
            
        st.divider()
        filtro_tiempo = st.radio("Período:", ["Hoy (Tiempo Real)", "Ayer", "Histórico 7 días"])
        mis_intereses = st.multiselect("Filtro Áreas:", LISTA_DEPARTAMENTOS, default=user.get('intereses', [])[:3])
        
        st.divider()
        st.markdown("**Acciones Rápidas**")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Escanear"):
                with st.spinner("Buscando..."):
                    buscador_inteligente()
                    st.rerun()
        
        with col_btn2:
            if st.button("💾 Guardar"):
                db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
                st.toast("Preferencias guardadas")

        st.markdown("---")
        if st.button("📧 Enviar Reporte (Email)"):
            hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
            docs = db.collection('news_articles').where(filter=FieldFilter('published_at', '>=', hoy)).stream()
            lista_envio = [d.to_dict() for d in docs]
            
            if lista_envio:
                exito = enviar_reporte_email(lista_envio, st.session_state['user_email'], user.get('nombre'))
                if exito: st.success("✅ Reporte enviado")
                else: st.error("Error al enviar")
            else:
                st.warning("No hay noticias hoy.")

    # --- CONTENIDO ---
    st.title("Centro de Inteligencia")
    
    hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    query = db.collection('news_articles')
    if mis_intereses: query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
    
    if filtro_tiempo == "Hoy (Tiempo Real)": query = query.where(filter=FieldFilter('published_at', '>=', hoy))
    elif filtro_tiempo == "Ayer": 
        ayer = hoy - datetime.timedelta(days=1)
        query = query.where(filter=FieldFilter('published_at', '>=', ayer)).where(filter=FieldFilter('published_at', '<', hoy))
    
    tab_news, tab_metrics = st.tabs(["📰 Feed de Noticias", "📊 Métricas"])
    
    with tab_news:
        docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(30).stream()
        lista_noticias = [d.to_dict() for d in docs]
        
        if not lista_noticias:
            st.info("📭 Sin noticias. Usa el botón '🔄 Escanear' en la barra lateral.")
        
        for n in lista_noticias:
            a = n.get('analysis', {})
            dept = a.get('departamento', 'General')
            color = COLORES_DEPT.get(dept, '#888')
            score = a.get('relevancia_score', 0)
            
            # Tarjeta de Noticia (Estilo Newsletter Dark)
            with st.container():
                cols = st.columns([0.1, 4])
                with cols[0]:
                    st.markdown(f"<div style='height:100%; width:4px; background-color:{color}; border-radius:4px;'></div>", unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(f"### [{n.get('title')}]({n.get('url')})")
                    st.caption(f"**{dept}** • {n.get('published_at').strftime('%H:%M %p')}")
                    st.markdown(f"{a.get('resumen_ejecutivo', '...')}")
                    
                    st.markdown(f"""
                        <div style="margin-top:10px; display:flex; align-items:center; gap:10px;">
                            <span style="background-color:rgba(0,193,169,0.1); color:#00c1a9; padding:4px 8px; border-radius:4px; font-size:0.9em; font-weight:bold;">
                                💡 {a.get('accion_sugerida', 'Revisar')}
                            </span>
                            <span class="ia-badge">
                                IA Score: {score}/100
                            </span>
                        </div>
                    """, unsafe_allow_html=True)
                st.divider()

    with tab_metrics:
        all_docs = db.collection('news_articles').limit(100).stream()
        df = pd.DataFrame([d.to_dict()['analysis'] for d in all_docs if 'analysis' in d.to_dict()])
        if not df.empty:
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.pie(df, names='departamento', color='departamento', color_discrete_map=COLORES_DEPT, hole=0.4), use_container_width=True)
            with c2: st.plotly_chart(px.bar(df.groupby('departamento')['relevancia_score'].mean().reset_index(), x='departamento', y='relevancia_score', color='departamento', color_discrete_map=COLORES_DEPT), use_container_width=True)

if __name__ == "__main__":
    if st.session_state['logged_in']: main_app()
    else: main_login()
