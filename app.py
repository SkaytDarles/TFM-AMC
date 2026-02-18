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
from duckduckgo_search import DDGS

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(
    page_title="AMC Intelligence Hub", 
    page_icon="🦅", 
    layout="wide"
)

# --- CREDENCIALES ---
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

# QUERIES
QUERIES_DEPT = {
    "Finanzas y ROI": "industria alimentos finanzas inversión tecnologia",
    "FoodTech and Supply Chain": "FoodTech cadena suministro innovación",
    "Innovación y Tendencias": "tendencias consumo alimentos bebidas 2025 2026",
    "Tecnología e Innovación": "inteligencia artificial industria manufactura software",
    "Legal & Regulatory Affairs / Innovation": "regulación ley alimentos etiquetado tecnología"
}

# ==========================================
# 2. CONEXIÓN FIREBASE & GEMINI
# ==========================================
if not firebase_admin._apps:
    try:
        if "FIREBASE_KEY" in st.secrets:
            key_dict = dict(st.secrets["FIREBASE_KEY"])
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
            
        if "GOOGLE_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
            
    except Exception as e:
        st.error(f"Error Configuración: {e}")
        st.stop()

db = firestore.client()

# ==========================================
# 3. MOTOR DE DATOS (SCRAPER + AI)
# ==========================================

def analizar_con_gemini(texto, titulo, dept):
    """
    MODIFICADO: Ahora pide un PÁRRAFO DE RESUMEN, no una línea.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Como experto en inteligencia competitiva para AMC Global, analiza:
        Titulo: {titulo}
        Contexto: {texto}
        Departamento: {dept}
        
        Output JSON (sin markdown):
        {{
            "titulo_mejorado": "Titulo en español profesional",
            "resumen": "Escribe un párrafo completo (aprox 40-50 palabras) resumiendo los puntos clave de la noticia y por qué es importante.", 
            "accion": "Acción estratégica recomendada.",
            "score": (85-99)
        }}
        """
        response = model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except:
        return {
            "titulo_mejorado": titulo,
            "resumen": f"Se ha detectado contenido relevante sobre {titulo}. {texto[:150]}... Se recomienda revisar la fuente original para más detalles.",
            "accion": "Revisar enlace original.",
            "score": 80
        }

def buscador_inteligente():
    count_news = 0
    ddgs = DDGS()
    
    print("🦅 Iniciando Búsqueda Inteligente...")
    
    for dept, query in QUERIES_DEPT.items():
        resultados = []
        
        # 1. Intentar buscar noticias de HOY
        try:
            gen = ddgs.news(query, region="mx-es", timelimit="d", max_results=2)
            resultados = list(gen)
        except: pass
        
        # 2. Si no hay, buscar de la SEMANA
        if not resultados:
            try:
                gen = ddgs.news(query, region="mx-es", timelimit="w", max_results=2)
                resultados = list(gen)
            except: pass
            
        # 3. Si no hay, buscar GENERAL
        if not resultados:
            try:
                gen = ddgs.text(query, region="mx-es", max_results=2)
                resultados = list(gen)
            except: pass

        for r in resultados:
            titulo = r.get('title', '')
            link = r.get('url', r.get('href', ''))
            body = r.get('body', r.get('snippet', ''))
            
            if not titulo or not link: continue

            # Verificar Duplicados
            docs = db.collection('news_articles')\
                     .where(filter=FieldFilter('title', '==', titulo))\
                     .limit(1).stream()
            if list(docs): continue

            # IA
            analisis = analizar_con_gemini(body, titulo, dept)
            
            # Guardar
            db.collection('news_articles').add({
                "title": analisis.get('titulo_mejorado', titulo),
                "url": link,
                "published_at": datetime.datetime.now(),
                "source": r.get('source', 'Web Search'),
                "analysis": {
                    "departamento": dept,
                    "titulo_traducido": analisis.get('titulo_mejorado', titulo),
                    "resumen_ejecutivo": [analisis.get('resumen')], # Guardamos el párrafo
                    "accion_sugerida": analisis.get('accion'),
                    "relevancia_score": analisis.get('score')
                }
            })
            count_news += 1
            time.sleep(0.5)

    return count_news

# ==========================================
# 4. FUNCIONES UI Y EMAIL
# ==========================================
def enviar_email(num, dest, nombre):
    if num == 0: return
    try:
        msg = MIMEMultipart()
        msg['From'] = REMITENTE_EMAIL
        msg['To'] = dest
        msg['Subject'] = Header(f"🦅 AMC Daily: {num} Hallazgos", 'utf-8')
        html = f"""
        <div style="font-family:sans-serif; padding:20px; background:#f4f4f4;">
            <h2 style="color:#00c1a9;">AMC INTELLIGENCE</h2>
            <p>Hola {nombre}, el sistema ha localizado <b>{num} nuevas oportunidades</b>.</p>
            <a href="https://amc-dashboard.streamlit.app">Ver Dashboard</a>
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

def verificar_ingesta_hoy():
    inicio_hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    docs = db.collection('news_articles').where(filter=FieldFilter('published_at', '>=', inicio_hoy)).limit(1).stream()
    
    if not list(docs):
        placeholder = st.empty()
        with placeholder.container():
            st.warning("⚠️ Sin datos frescos. Iniciando Motor de Búsqueda Inteligente (DuckDuckGo)...")
            bar = st.progress(0)
            n = buscador_inteligente()
            bar.progress(100)
            if n > 0:
                st.success(f"✅ Ingesta completada: {n} noticias.")
                enviar_email(n, st.session_state.get('user_email', REMITENTE_EMAIL), "Usuario")
            else:
                st.error("⚠️ La red está silenciosa hoy.")
            time.sleep(1.5)
        placeholder.empty()
        st.rerun()

# ==========================================
# 5. UI PRINCIPAL
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.markdown("<br><h1 style='text-align:center; color:#00c1a9;'>AMC GLOBAL</h1>", unsafe_allow_html=True)
        email = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("ACCESO SEGURO", use_container_width=True):
            try:
                user_ref = db.collection('users').document(email).get()
                if user_ref.exists and user_ref.to_dict().get('password') == password:
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = email
                    st.rerun()
                else: st.error("Acceso Denegado")
            except: st.error("Error de Sistema")
else:
    # --- LOGIC ---
    verificar_ingesta_hoy()
    
    try: user_data = db.collection('users').document(st.session_state['user_email']).get().to_dict()
    except: user_data = {"nombre": "Admin", "intereses": []}

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("AMC HUB")
        st.caption(f"Operador: {user_data.get('nombre')}")
        st.divider()
        
        filtro_tiempo = st.radio("Rango de Datos:", ["Tiempo Real (Hoy)", "Ayer", "Histórico"], index=0)
        mis_intereses = st.multiselect("Departamentos:", LISTA_DEPARTAMENTOS, default=user_data.get('intereses', [])[:2])
        
        if st.button("💾 Guardar Config"):
            db.collection('users').document(st.session_state['user_email']).update({"intereses": mis_intereses})
            st.rerun()
        
        st.divider()
        if st.button("🚀 Escaneo Manual Profundo"):
            with st.spinner("Ejecutando escaneo en la web profunda..."):
                n = buscador_inteligente()
                st.success(f"Hallazgos: {n}")
                time.sleep(1)
                st.rerun()
        
        if st.button("📧 Enviar Reporte"):
            enviar_email(5, st.session_state['user_email'], "Usuario")
            st.success("Enviado")
                
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

    # --- DASHBOARD ---
    st.title("Centro de Inteligencia Estratégica")
    
    hoy = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    ayer = hoy - datetime.timedelta(days=1)
    
    query = db.collection('news_articles')
    if mis_intereses: query = query.where(filter=FieldFilter('analysis.departamento', 'in', mis_intereses))
    
    if filtro_tiempo == "Tiempo Real (Hoy)":
        query = query.where(filter=FieldFilter('published_at', '>=', hoy))
        st.caption(f"📡 Mostrando inteligencia recolectada HOY ({datetime.datetime.now().strftime('%d-%m-%Y')})")
    elif filtro_tiempo == "Ayer":
        query = query.where(filter=FieldFilter('published_at', '>=', ayer)).where(filter=FieldFilter('published_at', '<', hoy))
    
    tab1, tab2 = st.tabs(["Noticias", "Métricas"])
    
    with tab1:
        docs = query.order_by('published_at', direction=firestore.Query.DESCENDING).limit(20).stream()
        lista = [d.to_dict() for d in docs]
        
        if lista:
            for n in lista:
                a = n.get('analysis', {})
                dept = a.get('departamento', 'General')
                color = COLORES_DEPT.get(dept, '#888')
                fecha = n.get('published_at')
                fecha_str = fecha.strftime("%H:%M") if filtro_tiempo == "Tiempo Real (Hoy)" else fecha.strftime("%d/%m %H:%M")
                
                # MODIFICADO: VISUALIZACIÓN DE PARRAFO
                # Extraemos el resumen, asegurando que sea string
                resumen_texto = a.get('resumen_ejecutivo', ['Sin resumen'])
                if isinstance(resumen_texto, list):
                    resumen_final = resumen_texto[0]
                else:
                    resumen_final = str(resumen_texto)

                st.markdown(f"""
                <div style="background:#161b22; border-left:5px solid {color}; border-radius:8px; padding:20px; margin-bottom:20px; border:1px solid #30363d;">
                    <div style="display:flex; justify-content:space-between; color:{color}; font-weight:bold; font-size:12px; margin-bottom:8px;">
                        <span>{dept.upper()}</span>
                        <span style="color:#666;">{fecha_str}</span>
                    </div>
                    <h3 style="color:#fff; margin:0 0 12px 0; font-size:20px;">{n.get('title')}</h3>
                    
                    <div style="color:#c9d1d9; font-size:15px; line-height:1.6; margin-bottom:15px; text-align: justify;">
                        {resumen_final}
                    </div>
                    
                    <div style="background:rgba(0,193,169,0.1); padding:12px; border-radius:6px; font-size:14px; color:#aaa; border-left: 2px solid #00c1a9;">
                        💡 <b>Acción Sugerida:</b> {a.get('accion_sugerida')}
                    </div>
                    <div style="margin-top:15px; text-align:right;">
                        <a href="{n.get('url')}" target="_blank" style="color:{color}; text-decoration:none; font-weight:bold; font-size:13px;">Leer Fuente Completa 🔗</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            if filtro_tiempo == "Tiempo Real (Hoy)":
                st.info("ℹ️ No hay datos ingestados aún. El crawler automático se ejecutará pronto.")
            else:
                st.warning("Sin datos históricos para este periodo.")

    with tab2:
        all_docs = db.collection('news_articles').limit(100).stream()
        df = pd.DataFrame([d.to_dict()['analysis'] for d in all_docs if 'analysis' in d.to_dict()])
        if not df.empty:
            c1, c2 = st.columns(2)
            with c1: st.plotly_chart(px.pie(df, names='departamento', color='departamento', color_discrete_map=COLORES_DEPT), use_container_width=True)
            with c2: 
                grp = df.groupby('departamento')['relevancia_score'].mean().reset_index()
                st.plotly_chart(px.bar(grp, x='departamento', y='relevancia_score', color='departamento', color_discrete_map=COLORES_DEPT), use_container_width=True)
