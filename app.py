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
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="🔓", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para limpiar la interfaz
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-top: 2px solid #00c1a9; }
    h1 { color: #00c1a9 !important; }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
# ¡IMPORTANTE!: Asegúrate de que esta clave sea una "App Password" de Google, no tu pass normal
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
# 2. UTILIDADES DE SEGURIDAD & DATOS
# ==========================================
def hash_pass(password):
    """Cifra la contraseña para no guardarla en texto plano (Seguridad Básica)"""
    return hashlib.sha256(str.encode(password)).hexdigest()

def limpiar_json(texto):
    try:
        start = texto.find('{')
        end = texto.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(texto[start:end])
        return None
    except: return None

# ==========================================
# 3. CONEXIÓN FIREBASE & GEMINI (ROBUSTA)
# ==========================================
@st.cache_resource
def init_connection():
    """Conexión Singleton a Firebase para evitar reconexiones múltiples"""
    try:
        if not firebase_admin._apps:
            # Opción A: Streamlit Secrets (Producción)
            if "FIREBASE_KEY" in st.secrets:
                key_dict = dict(st.secrets["FIREBASE_KEY"])
                # FIX CRÍTICO: Reemplazar \\n escapados por saltos de línea reales
                if "private_key" in key_dict:
                    key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
            # Opción B: Archivo Local (Desarrollo)
            else:
                cred = credentials.Certificate('serviceAccountKey.json')
                firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"❌ Error Crítico de Conexión a BD: {e}")
        return None

db = init_connection()

# Configurar Gemini
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# ==========================================
# 4. LÓGICA DE NEGOCIO (BUSCADOR & IA)
# ==========================================
def analizar_con_gemini(texto, titulo, dept):
    if "GOOGLE_API_KEY" not in st.secrets:
        return {"titulo_mejorado": titulo, "resumen": texto[:200], "accion": "Configurar API Key", "score": 50}

    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Eres un analista de inteligencia competitiva para AMC Global ({dept}).
    Analiza: {titulo}
    Texto: {texto[:1000]}...

    Salida JSON estricta:
    {{
        "titulo_mejorado": "Título en español profesional",
        "resumen": "Resumen ejecutivo de 40 palabras máximo.",
        "accion": "Sugerencia estratégica breve.",
        "score": (0-100 relevancia para industria alimentaria)
    }}
    """
    try:
        response = model.generate_content(prompt)
        data = limpiar_json(response.text)
        if data: return data
    except: pass
    
    return {"titulo_mejorado": titulo, "resumen": "Error en análisis IA", "accion": "Revisar manual", "score": 50}

def buscador_inteligente():
    count_news = 0
    ddgs = DDGS()
    news_batch = [] # Acumulamos para enviar email al final

    status_container = st.status("🕵️ Iniciando escaneo de inteligencia...", expanded=True)
    
    for dept, query in QUERIES_DEPT.items():
        status_container.write(f"Buscando: {dept}...")
        try:
            # Busqueda web general para saltar paywalls de noticias específicas
            resultados = list(ddgs.text(f"{query} noticias recientes", region="wt-wt", timelimit="d", max_results=3))
            
            for r in resultados:
                titulo = r.get('title')
                link = r.get('href')
                body = r.get('body')

                if not titulo or not link: continue
                
                # Verificar duplicados en BD
                docs = db.collection('news_articles').where(filter=FieldFilter('title', '==', titulo)).limit(1).stream()
                if list(docs): continue

                # Analizar
                analisis = analizar_con_gemini(body, titulo, dept)
                
                doc_data = {
                    "title": analisis.get('titulo_mejorado', titulo),
                    "url": link,
                    "published_at": datetime.datetime.now(),
                    "source": "Web Abierta / AI Hub",
                    "analysis": {
                        "departamento": dept,
                        "resumen_ejecutivo": analisis.get('resumen'),
                        "accion_sugerida": analisis.get('accion'),
                        "relevancia_score": analisis.get('score')
                    }
                }
                
                db.collection('news_articles').add(doc_data)
                news_batch.append(doc_data) # Guardar para el reporte de email
                count_news += 1
                time.sleep(0.5) # Respetar rate limits
                
        except Exception as e:
            print(f"Error en {dept}: {e}")
            continue

    status_container.update(label="✅ Escaneo completado", state="complete", expanded=False)
    return news_batch

# ==========================================
# 5. SISTEMA DE EMAIL MEJORADO (HTML)
# ==========================================
def enviar_reporte_email(news_list, dest, nombre):
    if not news_list: return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = dest
        msg['Subject'] = Header(f"🔓 AMC Daily: {len(news_list)} Nuevos Insights", 'utf-8')

        # Construir tabla HTML
        rows = ""
        for n in news_list:
            analisis = n.get('analysis', {})
            color = COLORES_DEPT.get(analisis.get('departamento'), "#333")
            rows += f"""
            <tr>
                <td style="padding:15px; border-bottom:1px solid #eee;">
                    <span style="color:{color}; font-size:10px; font-weight:bold;">{analisis.get('departamento', '').upper()}</span>
                    <h3 style="margin:5px 0; color:#333;">{n.get('title')}</h3>
                    <p style="color:#666; font-size:14px; line-height:1.5;">{analisis.get('resumen_ejecutivo')}</p>
                    <a href="{n.get('url')}" style="color:#00c1a9; text-decoration:none; font-size:12px;">🔗 Leer fuente original</a>
                </td>
            </tr>
            """

        html = f"""
        <div style="font-family:Helvetica, sans-serif; max-width:600px; margin:0 auto; border:1px solid #e0e0e0;">
            <div style="background:#161b22; padding:20px; text-align:center;">
                <h2 style="color:#00c1a9; margin:0;">AMC INTELLIGENCE</h2>
            </div>
            <div style="padding:20px;">
                <p>Hola {nombre}, aquí tienes el resumen de inteligencia de hoy:</p>
                <table style="width:100%; border-collapse:collapse;">
                    {rows}
                </table>
                <br>
                <div style="text-align:center;">
                    <a href="https://amc-dashboard.streamlit.app" style="background:#00c1a9; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Ver Dashboard Completo</a>
                </div>
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
    except Exception as e:
        print(f"Error Email: {e}")
        return False

# ==========================================
# 6. GESTIÓN DE SESIÓN Y LOGIN
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = {}

def main_login():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><h1 style='text-align:center;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#666;'>Intelligence Hub Access</p>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔐 INGRESAR", "📝 REGISTRARSE"])
        
        # --- LOGIN ---
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Usuario (Email)")
                password = st.text_input("Contraseña", type="password")
                submitted = st.form_submit_button("ACCESO", use_container_width=True)
                
                if submitted:
                    if not db:
                        st.error("Error de conexión con base de datos.")
                        st.stop()
                        
                    doc_ref = db.collection('users').document(email)
                    doc = doc_ref.get()
                    
                    if doc.exists:
                        user_data = doc.to_dict()
                        # Verificación simple (hash vs hash idealmente, aqui simplificado para compatibilidad)
                        # Si ya tienes usuarios con pass texto plano, esto funcionará. 
                        # Si es nuevo, comparará hashes.
                        stored_pass = user_data.get('password')
                        
                        if stored_pass == password or stored_pass == hash_pass(password):
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = email
                            st.session_state['user_info'] = user_data
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
                    else:
                        st.error("Usuario no encontrado.")

        # --- REGISTRO ---
        with tab2:
            with st.form("register_form"):
                st.write("Solicitud de acceso para nuevos analistas")
                new_email = st.text_input("Email Corporativo")
                new_name = st.text_input("Nombre Completo")
                new_pass = st.text_input("Definir Contraseña", type="password")
                reg_submitted = st.form_submit_button("CREAR CUENTA", use_container_width=True)
                
                if reg_submitted:
                    if new_email and new_name and new_pass:
                        doc_ref = db.collection('users').document(new_email)
                        if doc_ref.get().exists:
                            st.warning("Este usuario ya existe.")
                        else:
                            doc_ref.set({
                                "nombre": new_name,
                                "password": hash_pass(new_pass), # Guardamos con seguridad básica
                                "intereses": LISTA_DEPARTAMENTOS, # Default todos
                                "created_at": datetime.datetime.now()
                            })
                            st.success("Cuenta creada exitosamente. Por favor ingresa en la pestaña 'INGRESAR'.")
                    else:
                        st.warning("Por favor completa todos los campos.")

# ==========================================
# 7. APLICACIÓN PRINCIPAL (DASHBOARD)
# ==========================================
def main_app():
    user = st.session_state['user_info']
    
    # --- SIDEBAR ---
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"👤 {user.get('nombre', 'Analista')}")
        
        if st.button("🚪 Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.session_state['user_info'] = {}
            st.rerun()
            
        st.divider()
        
        filtro_tiempo = st.radio("Período:", ["Hoy (Tiempo Real)", "Ayer", "Histórico 7 días"])
        
        # Guardar preferencias
        mis_intereses = st.multiselect("Filtro por Áreas:", LISTA_DEPARTAMENTOS, default=user.get('intereses', [])[:3])
        if st.button("💾 Actualizar Preferencias"):
            db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
            st.success("Guardado")
            time.sleep(1)
            st.rerun()

        st.divider()
        st.caption("Herramientas Admin")
        if st.button("🚀 Forzar Escaneo Web"):
            news_batch = buscador_inteligente()
            if news_batch:
                st.success(f"{len(news_batch)} noticias nuevas.")
                # Enviar email automático tras escaneo manual
                enviar_reporte_email(news_batch, st.session_state['user_email'], user.get('nombre'))
                time.sleep(1)
                st.rerun()
            else:
                st.warning("No se encontraron novedades recientes.")

    # --- CONTENIDO CENTRAL ---
    st.title("Centro de Inteligencia")
    
    # Lógica de fechas
    hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    query = db.collection('news_articles')
    
    if mis_intereses: 
        query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
        
    if filtro_tiempo == "Hoy (Tiempo Real)":
        query = query.where(filter=FieldFilter('published_at', '>=', hoy))
    elif filtro_tiempo == "Ayer":
        ayer = hoy - datetime.timedelta(days=1)
        query = query.where(filter=FieldFilter('published_at', '>=', ayer)).where(filter=FieldFilter('published_at', '<', hoy))
    else:
        semana = hoy - datetime.timedelta(days=7)
        query = query.where(filter=FieldFilter('published_at', '>=', semana))

    # Tabs de visualización
    tab_news, tab_metrics = st.tabs(["📰 Feed de Noticias", "📊 Métricas de Impacto"])
    
    with tab_news:
        docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(30).stream()
        lista_noticias = [d.to_dict() for d in docs]
        
        if not lista_noticias:
            st.info("📭 No hay noticias para este filtro. Intenta 'Forzar Escaneo Web' en el menú lateral.")
        
        for n in lista_noticias:
            a = n.get('analysis', {})
            dept = a.get('departamento', 'General')
            color = COLORES_DEPT.get(dept, '#888')
            
            with st.container():
                cols = st.columns([0.1, 4])
                with cols[0]:
                    st.markdown(f"<div style='height:100%; width:5px; background-color:{color}; border-radius:5px;'></div>", unsafe_allow_html=True)
                with cols[1]:
                    st.caption(f"{dept} • {n.get('published_at').strftime('%d/%m %H:%M')}")
                    st.markdown(f"### [{n.get('title')}]({n.get('url')})")
                    st.markdown(f"{a.get('resumen_ejecutivo', 'Sin resumen')}")
                    
                    c_act, c_score = st.columns([3, 1])
                    with c_act:
                        st.info(f"💡 **Acción:** {a.get('accion_sugerida', 'Revisar')}")
                    with c_score:
                        score = a.get('relevancia_score', 0)
                        st.metric("Relevancia", f"{score}/100")
                st.divider()

    with tab_metrics:
        # Recuperar más datos para gráficas
        all_query = db.collection('news_articles').order_by('published_at', direction=firestore.Query.DESCENDING).limit(100)
        df_docs = [d.to_dict()['analysis'] for d in all_query.stream() if 'analysis' in d.to_dict()]
        
        if df_docs:
            df = pd.DataFrame(df_docs)
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Distribución por Departamento")
                fig_pie = px.pie(df, names='departamento', color='departamento', color_discrete_map=COLORES_DEPT, hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with col2:
                st.subheader("Relevancia Promedio")
                df_score = df.groupby('departamento')['relevancia_score'].mean().reset_index()
                fig_bar = px.bar(df_score, x='departamento', y='relevancia_score', color='departamento', color_discrete_map=COLORES_DEPT)
                st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("Insuficientes datos para métricas.")

# ==========================================
# 8. EJECUCIÓN
# ==========================================
if __name__ == "__main__":
    if st.session_state['logged_in']:
        main_app()
    else:
        main_login()
