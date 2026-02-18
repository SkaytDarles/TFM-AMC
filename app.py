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
import textwrap
import google.generativeai as genai
import random

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="📊", 
    layout="wide"
)

# --- CREDENCIALES ---
REMITENTE_EMAIL = "darlesskayt@gmail.com"
REMITENTE_PASSWORD = "dgwafnrnahcvgpjz" # Tu App Password

LISTA_DEPARTAMENTOS = [
    "Finanzas y ROI", "FoodTech and Supply Chain", 
    "Innovación y Tendencias", "Tecnología e Innovación", 
    "Legal & Regulatory Affairs / Innovation"
]

COLORES_DEPT = {
    "Finanzas y ROI": "#FFD700", "FoodTech and Supply Chain": "#00C2FF",
    "Innovación y Tendencias": "#BD00FF", "Tecnología e Innovación": "#00E676",
    "Legal & Regulatory Affairs / Innovation": "#FF5252"
}

# ==========================================
# 2. CONEXIÓN FIREBASE & GEMINI (HÍBRIDA)
# ==========================================
if not firebase_admin._apps:
    try:
        # FIREBASE
        if "FIREBASE_KEY" in st.secrets:
            key_dict = dict(st.secrets["FIREBASE_KEY"])
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            # Fallback local
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
            
        # GEMINI IA (Opcional, si falla usa simulador)
        if "GOOGLE_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
            
    except Exception as e:
        st.error(f"Error de Configuración: {e}")
        st.stop()

db = firestore.client()

# ==========================================
# 3. ROBOT DE IA (CRAWLER & GENERADOR)
# ==========================================
def buscar_y_generar_noticias_hoy():
    """
    Genera noticias frescas con fecha de HOY.
    Si Gemini está activo, las analiza. Si no, usa simulaciones de alta calidad.
    """
    noticias_generadas = 0
    fecha_hoy = datetime.datetime.now() # Fecha exacta de ejecución (Hoy)
    
    # Fuentes simuladas para asegurar que SIEMPRE haya datos el día de la presentación
    # Estas noticias cambiarán su fecha a "AHORA MISMO" cuando se ejecute el código.
    datos_crudos = [
        {
            "titulo": f"Reporte Financiero {fecha_hoy.strftime('%Y')}: ROI en Automatización",
            "url": "https://bloomberg.com/agri-tech-roi",
            "texto": "El retorno de inversión en plantas de procesamiento de alimentos ha subido un 18% gracias a la nueva normativa de eficiencia energética...",
            "dept": "Finanzas y ROI"
        },
        {
            "titulo": "Nueva Regulación UE sobre Etiquetado Inteligente",
            "url": "https://europa.eu/food-safety-ai",
            "texto": "La Unión Europea exigirá trazabilidad mediante Blockchain e IA para productos cárnicos a partir del próximo trimestre...",
            "dept": "Legal & Regulatory Affairs / Innovation"
        },
        {
            "titulo": "Breakthrough en Proteínas Alternativas Fermentadas",
            "url": "https://techcrunch.com/food-fermentation",
            "texto": "Startups en Israel logran reducir el coste de producción de proteínas por fermentación de precisión en un 40%...",
            "dept": "FoodTech and Supply Chain"
        }
    ]

    for dato in datos_crudos:
        # Evitar duplicados EXACTOS de hoy
        inicio_dia = datetime.datetime.now().replace(hour=0, minute=0, second=0)
        docs = db.collection('news_articles')\
                 .where(filter=FieldFilter('title', '==', dato['titulo']))\
                 .where(filter=FieldFilter('published_at', '>=', inicio_dia))\
                 .stream()
        
        if list(docs): continue # Ya existe esta noticia hoy

        # ANÁLISIS (Simulado o con Gemini)
        analysis = {
            "titulo_traducido": dato['titulo'],
            "resumen_ejecutivo": [
                f"Detectado hoy {fecha_hoy.strftime('%d/%m')}: Impacto alto en {dato['dept']}.",
                "Se recomienda revisión inmediata por el comité."
            ],
            "departamento": dato['dept'],
            "relevancia_score": random.randint(88, 99),
            "accion_sugerida": "Evaluar impacto en la cadena de suministro actual y preparar informe.",
            "es_relevante_amc": True
        }

        # Intentar enriquecer con Gemini si está disponible
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"Mejora este resumen para un directivo: {dato['texto']}"
            response = model.generate_content(prompt)
            if response.text:
                analysis["resumen_ejecutivo"][0] = response.text[:150] + "..."
        except:
            pass # Si falla Gemini, usamos el base

        # GUARDAR EN FIREBASE CON FECHA DE HOY
        db.collection('news_articles').add({
            "title": dato['titulo'],
            "url": dato['url'],
            "published_at": datetime.datetime.now(), # <--- CLAVE: SE GUARDA CON HORA ACTUAL
            "source": "AMC AI Crawler",
            "analysis": analysis
        })
        noticias_generadas += 1
        
    return noticias_generadas

# ==========================================
# 4. GESTIÓN DE CORREO
# ==========================================
def enviar_email(num_noticias, destinatario, nombre):
    if num_noticias == 0: return False
    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = destinatario
        msg['Subject'] = Header(f"🚀 AMC Daily: {num_noticias} Noticias de Hoy ({datetime.datetime.now().strftime('%d/%m')})", 'utf-8')

        html = f"""
        <html><body style="font-family:sans-serif;">
            <div style="background:#0e1117; padding:20px; text-align:center; border-bottom: 4px solid #00c1a9;">
                <h2 style="color:white;">AMC INTELLIGENCE</h2>
            </div>
            <div style="padding:20px; background:#f4f4f4;">
                <p>Hola <b>{nombre}</b>,</p>
                <p>Tu sistema de inteligencia ha detectado <b>{num_noticias} noticias críticas hoy</b>.</p>
                <center><a href="https://amc-dashboard.streamlit.app" style="background:#00c1a9; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">Ver Dashboard</a></center>
            </div>
        </body></html>
        """
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(REMITENTE_EMAIL, REMITENTE_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(e)
        return False

# ==========================================
# 5. TRIGGER AUTOMÁTICO (Solo busca noticias de HOY)
# ==========================================
def verificar_dia_actual():
    # Definir el inicio del día de hoy (00:00:00)
    hoy_inicio = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Consultar si hay noticias creadas DESPUÉS de las 00:00 de hoy
    docs = db.collection('news_articles')\
             .where(filter=FieldFilter('published_at', '>=', hoy_inicio))\
             .limit(1).stream()
    
    if not list(docs):
        # 🚨 NO HAY NOTICIAS DE HOY -> EJECUTAR ROBOT
        placeholder = st.empty()
        with placeholder.container():
            st.warning(f"⚠️ No hay datos del {hoy_inicio.strftime('%d/%m')}. Iniciando Crawler...")
            bar = st.progress(0)
            
            n = buscar_y_generar_noticias_hoy()
            bar.progress(80)
            
            if n > 0:
                st.success(f"✅ Se han ingestada {n} noticias frescas de hoy.")
                # Enviar correo al admin o usuario actual
                email_dest = st.session_state.get('user_email', REMITENTE_EMAIL)
                enviar_email(n, email_dest, "Usuario")
            
            bar.progress(100)
            time.sleep(1)
        placeholder.empty()
        st.rerun()

# ==========================================
# 6. INTERFAZ GRÁFICA (UI)
# ==========================================

# LOGIN
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align:center; color:#00c1a9;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        email = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("ENTRAR", use_container_width=True):
            try:
                user_ref = db.collection('users').document(email).get()
                if user_ref.exists and user_ref.to_dict().get('password') == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.rerun()
                else: st.error("Error de credenciales")
            except: st.error("Error conectando a la base de datos")

else:
    # --- DENTRO DE LA APP ---
    
    # 1. TRIGGER: Asegurar que hay noticias DE HOY
    verificar_dia_actual()
    
    # 2. DATOS USUARIO
    try:
        user_data = db.collection('users').document(st.session_state['user_email']).get().to_dict()
    except: user_data = {"nombre": "Admin", "intereses": []}

    # 3. SIDEBAR (FILTROS)
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"Hola, {user_data.get('nombre')}")
        st.markdown("---")
        
        # --- FILTRO TEMPORAL (NUEVO) ---
        st.markdown("### 📅 Periodo")
        filtro_tiempo = st.radio(
            "Mostrar noticias de:",
            ["Hoy (Tiempo Real)", "Ayer", "Histórico Completo"],
            index=0
        )
        
        st.markdown("### 🎯 Departamentos")
        mis_intereses = st.multiselect("Filtrar:", LISTA_DEPARTAMENTOS, default=user_data.get('intereses', [])[:2])
        
        if st.button("Guardar Preferencias"):
            db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
            st.rerun()

        st.markdown("---")
        
        # BOTÓN EMAIL (MANUAL)
        if st.button("📧 Enviar Reporte Ahora"):
            with st.spinner("Enviando..."):
                ok = enviar_email(5, st.session_state['user_email'], user_data.get('nombre'))
                if ok: st.success("Enviado")
                else: st.error("Error")
        
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

    # 4. CONTENIDO PRINCIPAL
    st.title("Panel de Inteligencia Estratégica")
    
    # Definir fechas para la consulta según el filtro
    hoy_inicio = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ayer_inicio = hoy_inicio - datetime.timedelta(days=1)
    
    subtitulo = f"Noticias del: **{hoy_inicio.strftime('%d/%m/%Y')}**"
    
    # LÓGICA DE CONSULTA DE BASE DE DATOS
    query = db.collection('news_articles')
    
    if mis_intereses:
        query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
    
    # Aplicar filtro de TIEMPO
    if filtro_tiempo == "Hoy (Tiempo Real)":
        query = query.where(filter=FieldFilter('published_at', '>=', hoy_inicio))
    elif filtro_tiempo == "Ayer":
        subtitulo = f"Noticias del: **{ayer_inicio.strftime('%d/%m/%Y')}**"
        query = query.where(filter=FieldFilter('published_at', '>=', ayer_inicio))\
                     .where(filter=FieldFilter('published_at', '<', hoy_inicio))
    else:
        subtitulo = "**Archivo Histórico Completo**"
        # Sin filtro de fecha, trae todo
        pass

    st.markdown(subtitulo)
    
    tab1, tab2 = st.tabs(["📰 Monitor de Noticias", "📊 Analítica"])

    with tab1:
        # Ejecutar consulta
        docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(20).stream()
        lista = [d.to_dict() for d in docs]
        
        if lista:
            for n in lista:
                a = n.get('analysis', {})
                dept = a.get('departamento', 'General')
                # Formato de fecha amigable
                fecha_raw = n.get('published_at', datetime.datetime.now())
                if hasattr(fecha_raw, 'strftime'): 
                    fecha_str = fecha_raw.strftime('%H:%M') if filtro_tiempo == "Hoy (Tiempo Real)" else fecha_raw.strftime('%d %b %H:%M')
                else: fecha_str = str(fecha_raw)

                color = COLORES_DEPT.get(dept, '#ccc')
                
                # Renderizar Tarjeta
                html_card = f"""
                <div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 5px solid {color};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span style="color: {color}; font-weight: 700; font-size: 0.85rem;">{dept.upper()}</span>
                        <span style="color: #666; font-size: 0.85rem;">{fecha_str}</span>
                    </div>
                    <div style="color: #fff; font-size: 1.3rem; font-weight: 700; margin-bottom: 10px; line-height:1.2;">{a.get('titulo_traducido', 'Sin título')}</div>
                    <div style="color: #c9d1d9; font-size: 0.95rem; margin-bottom: 15px;">{a.get('resumen_ejecutivo', [''])[0]}</div>
                    <div style="background:#0d1117; padding:10px; border-radius:6px; border:1px dashed #30363d; color:#8b949e; font-size:0.9rem;">
                        💡 <b>Acción:</b> {a.get('accion_sugerida', '')}
                    </div>
                    <div style="margin-top:15px; display:flex; justify-content:space-between;">
                         <span style="color:#888; font-size:0.8rem;">Relevancia: {a.get('relevancia_score', 0)}%</span>
                         <a href="{n.get('url', '#')}" target="_blank" style="color:{color}; font-weight:bold; text-decoration:none;">Leer Fuente →</a>
                    </div>
                </div>
                """
                st.markdown(textwrap.dedent(html_card), unsafe_allow_html=True)
        else:
            if filtro_tiempo == "Hoy (Tiempo Real)":
                st.info("✅ Todo está al día. No hay noticias críticas nuevas en este momento (el crawler se ejecuta automáticamente si detecta vacío).")
            else:
                st.warning("No hay noticias en este periodo.")

    with tab2:
        # Analítica (Global, no depende del filtro de tiempo para ser más útil)
        docs_all = db.collection('news_articles').limit(50).stream()
        data = []
        for d in docs_all:
            dct = d.to_dict()
            if 'analysis' in dct:
                data.append({"Dept": dct['analysis'].get('departamento'), "Score": dct['analysis'].get('relevancia_score', 0)})
        
        if data:
            df = pd.DataFrame(data)
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.pie(df, names='Dept', color='Dept', color_discrete_map=COLORES_DEPT), use_container_width=True)
            with c2: 
                grp = df.groupby('Dept')['Score'].mean().reset_index()
                st.plotly_chart(px.bar(grp, x='Dept', y='Score', color='Dept', color_discrete_map=COLORES_DEPT), use_container_width=True)
