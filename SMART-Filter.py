import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io
import datetime
import streamlit.components.v1 as components
# Masquer les éléments du menu supérieur (Share, Star, Edit, etc.)
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stAppDeployButton {display:none;}
            #stDecoration {display:none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)
# Configuration complète de la page de l'application
st.set_page_config(
    page_title="SmartFilter Monitor - Dispositif Expérimental",
    layout="wide"
)

# --- EN-TÊTE RÉGLEMENTAIRE ET RAPPEL DU TITRE EXIGÉ ---
st.title("SmartFilter Monitor")
st.subheader("Plateforme de monitoring d'un filtre à manches-Cas d'une cimenterie ")
st.markdown("### ⚡ Supervision avancée du rendement des filtres à manches.")

# --- COEUR DE MODÉLISATION PHYSIQUE BILATERALE ---
class CementFilterFaradaySimulation:
    def __init__(self):
        # Paramètres procédé - Cimenterie de Lafarge Oggaz
        self.base_concentration = 1200.0  # mg/m^3 (Concentration amont nominale)
        self.nominal_efficiency = 0.9995  # 99.95% de rendement nominal
        self.t_critique_tissu = 240.0     # °C (Seuil thermique P84)
        self.debit_air_nominal = 450000.0 # m^3/h

        # Constante triboélectrique intrinsèque du couple Ciment / P84
        self.k_tribo_base = 17684.0       # nC/g (Charge à saturation)
        
        # --- CARACTÉRISTIQUES GÉOMÉTRIQUES ET ÉLECTRIQUES DE LA CAGE ---
        self.longueur_L = 0.10            # Longueur utile (10 cm)
        self.diametre_int = 60.0          # Ø intérieur électrode de mesure en mm
        self.diametre_ext = 80.0          # Ø extérieur écran de blindage en mm
        self.capacite_faraday = 19.33e-12 # Capacité propre calculée (19.33 pF)
        self.r_shunt = 2.5e6              # Résistance de Shunt de conditionnement (2.5 MΩ)
        
        # Profils de bruit de fond
        self.noise_carcasse_base = 0.5    # Bruit thermique de masse
        self.noise_carcasse_cem = 9.5     # Parasites industriels (moteurs/variateurs) sur la carcasse
        self.noise_faraday_nA = 0.12      # Cage de Faraday blindée (haute immunité)

        self.alpha = 0.15                 # Coefficient de lissage (Filtre EMA)

    def generate_data_point(self, t, is_mechanically_damaged, temperature, cem_parasite_active):
        q_sec = self.debit_air_nominal / 3600.0 # Débit volumique en m3/s (125 m3/s)
        
        # Évaluation des défaillances thermiques ou mécaniques
        t_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or t_damage: 
            current_eff = 0.978  
        else:
            current_eff = self.nominal_efficiency
         
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        c_out = c_in * (1.0 - current_eff)
        masse_fuite_sec = (c_out * q_sec) / 1000.0  # Débit de fuite particulaire en g/s
         
        # Électrisation triboélectrique influencée par la température
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        charge_specifique = self.k_tribo_base * facteur_temperature
        
        # Courant absolu généré par la séparation de charge
        i_généré_abs = masse_fuite_sec * charge_specifique

        # DUALITÉ PHYSIQUE DES POLARITÉS :
        # 1. Carcasse = Évacuation conductive des charges négatives accumulées sur le tissu
        bruit_c = self.noise_carcasse_cem if cem_parasite_active else self.noise_carcasse_base
        raw_carcasse_neg = - (i_généré_abs + np.random.normal(0.0, bruit_c))

        # 2. Cage de Faraday = Induction électrostatique sans contact du flux particulaire positif
        raw_faraday_pos = (i_généré_abs + np.random.normal(0.0, self.noise_faraday_nA))
         
        return raw_carcasse_neg, raw_faraday_pos, current_eff, t_damage, q_sec, masse_fuite_sec

# Instanciation du modèle de simulation
sim = CementFilterFaradaySimulation()

# --- INITIALISATION DES ÉTATS DE SESSION STREAMLIT ---
if 'time_steps' not in st.session_state:
    st.session_state.time_steps = []
if 'timestamps' not in st.session_state:
    st.session_state.timestamps = []
if 'raw_carcasse' not in st.session_state:
    st.session_state.raw_carcasse = []
if 'filtered_carcasse' not in st.session_state:
    st.session_state.filtered_carcasse = []
if 'raw_faraday' not in st.session_state:
    st.session_state.raw_faraday = []
if 'filtered_faraday' not in st.session_state:
    st.session_state.filtered_faraday = []
if 'voltage_faraday' not in st.session_state:
    st.session_state.voltage_faraday = []
if 'charge_acquise_pC' not in st.session_state:
    st.session_state.charge_acquise_pC = []
if 'efficiencies_calculated' not in st.session_state:
    st.session_state.efficiencies_calculated = []
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0
if 'ema_carcasse_state' not in st.session_state:
    st.session_state.ema_carcasse_state = None
if 'ema_faraday_state' not in st.session_state:
    st.session_state.ema_faraday_state = None

# --- CONFIGURATION DU PANNEAU LATÉRAL (SIDEBAR) ---
st.sidebar.header("Paramètres Opérationnels")
run_simulation = st.sidebar.toggle("Activer l'acquisition en direct", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Spécifications Physiques du Capteur")

st.sidebar.markdown(fr"""
* **Longueur utile ($L$) :** {sim.longueur_L * 100:.1f} cm
* **Diamètre Intérieur ($\varnothing_{{int}}$) :** {sim.diametre_int:.1f} mm
* **Diamètre Extérieur ($\varnothing_{{ext}}$) :** {sim.diametre_ext:.1f} mm
* **Capacité de la Cage ($C_{{cage}}$) :** **{sim.capacite_faraday * 1e12:.2f} pF**
* **Résistance Shunt ($R_{{shunt}}$) :** {sim.r_shunt / 1e6:.1f} M$\Omega$
""")

st.sidebar.markdown("---")
st.sidebar.subheader("Contrôle du Procédé")
gas_temp = st.sidebar.slider("Température des Gaz (°C)", 120, 280, 200)
trigger_mechanical = st.sidebar.toggle("Simuler une déchirure de manche", value=False)
trigger_cem_noise = st.sidebar.toggle("Injecter des parasites CEM (Masse)", value=True)
speed = st.sidebar.slider("Intervalle d'échantillonnage (s)", 0.1, 1.0, 0.3)

# --- BLOC D'EXPORTATION EN FICHIER EXCEL (.XLSX) ---
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Exportation des Données")

if len(st.session_state.timestamps) > 0:
    data_dictionnaire = {
        "Horodatage (Temps Réel)": list(st.session_state.timestamps),
        "Courant de Carcasse Filtré (nA)": list(st.session_state.filtered_carcasse),
        "Tension mesurée au Shunt (V)": list(st.session_state.voltage_faraday),
        "Charge Électrostatique Acquise (pC)": list(st.session_state.charge_acquise_pC),
        "Rendement de Filtration Estimé (%)": list(st.session_state.efficiencies_calculated)
    }
    
    df_export = pd.DataFrame(data_dictionnaire)
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Données_Temporelles_EDT')
    processed_data = output_buffer.getvalue()
    
    st.sidebar.download_button(
        label="📥 Télécharger la table Excel (Série Temporelle)",
        data=processed_data,
        file_name="Chronologie_Cage_Faraday_EDT_2026.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.sidebar.info("En attente de relevés temporels pour compiler le tableur Excel.")

# --- DÉFINITION DES TROIS ONGLETS DE L'INTERFACE ---
tab1, tab2, tab3 = st.tabs([
    "📊 Tableau de Bord Temps Réel", 
    "🔬 Rappels Théoriques & Formules", 
    "📐 Dispositif Expérimental"
])

# ===================================================
# ONGLET 1 : AFFICHAGE DU TABLEAU DE BORD TEMPS RÉEL
# ===================================================
with tab1:
    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            v_real_faraday = (st.session_state.ema_faraday_state * 1e-9) * sim.r_shunt
            q_inst_pC = (sim.capacite_faraday * v_real_faraday) * 1e12
            
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            i_max_theorique = ((sim.base_concentration * q_sec) / 1000.0) * (sim.k_tribo_base * facteur_t)
            estimated_eff = 1.0 - (st.session_state.ema_faraday_state / i_max_theorique)
            
            st.session_state.time_steps.append(t)
            st.session_state.timestamps.append(now_str)
            st.session_state.raw_carcasse.append(r_carcasse)
            st.session_state.filtered_carcasse.append(st.session_state.ema_carcasse_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.voltage_faraday.append(v_real_faraday)
            st.session_state.charge_acquise_pC.append(q_inst_pC)
            st.session_state.efficiencies_calculated.append(estimated_eff * 100.0)
             
            if len(st.session_state.time_steps) > 80:
                st.session_state.time_steps.pop(0)
                st.session_state.timestamps.pop(0)
                st.session_state.raw_carcasse.pop(0)
                st.session_state.filtered_carcasse.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.voltage_faraday.pop(0)
                st.session_state.charge_acquise_pC.pop(0)
                st.session_state.efficiencies_calculated.pop(0)
                 
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.09,
                subplot_titles=(
                    "📈 Évolution du Courant de Carcasse (Drainage de Masse Négatif)",
                    "⚛️ Dynamique de la Charge Électrostatique Réelle Acquise (Q)", 
                    "📊 Évolution du Rendement de Filtration Estimé (%)"
                )
            )
            
            fig.add_trace(go.Scatter(x=list(st.session_state.timestamps), y=list(st.session_state.filtered_carcasse),
                                     name="Courant Carcasse (Drainage -)", line=dict(color='#e67e22', width=2.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.timestamps), y=list(st.session_state.charge_acquise_pC),
                                     name="Charge Induite (Q)", line=dict(color='#9b59b6', width=2.5)), row=2, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.timestamps), y=list(st.session_state.efficiencies_calculated),
                                     name="Rendement (%)", line=dict(color='#2ecc71', width=2)), row=3, col=1)
            
            fig.update_layout(height=780, margin=dict(l=30, r=30, t=40, b=10), showlegend=True)
            fig.update_yaxes(title_text="Courant Carcasse (nA)", row=1, col=1)
            fig.update_yaxes(title_text="Charge Q (pC)", row=2, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=3, col=1)
            fig.update_xaxes(title_text="Horodatage de Mesure (Heure:Min:Sec.ms)", row=3, col=1)
            
            with placeholder.container():
                delta_verification = abs(abs(st.session_state.ema_carcasse_state) - st.session_state.ema_faraday_state)
                
                if t_damage:
                    st.error(f"🚨 EXTRUSION THERMIQUE CRITIQUE : Température de {gas_temp}°C supérieure à la limite admissible des manches P84 (240°C).")
                elif delta_verification > 5.0 and trigger_cem_noise:
                    st.warning(f"⚡ PARASITES DE MASSE DÉTECTÉS (CEM) : Écart de {delta_verification:.2f} nA détecté sur la carcasse extérieure.")
                elif estimated_eff < 0.992:
                    st.error(f"📉 CHUTE DU RENDEMENT DE FILTRATION : Fuite détectée par le capteur. Rendement bas : {estimated_eff*100:.3f}%")
                else:
                    st.success(f"✅ SYSTEME EN LIGNE [{now_str}] : Comportement nominal et écoulement stable vers le puits de terre.")

                st.markdown("#### 🎛️ Indicateurs d'Acquisition de l'Interface")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(label="🔏 Courant de Carcasse", value=f"{st.session_state.ema_carcasse_state:.2f} nA", delta="Drainage négatif (-)", delta_color="inverse")
                with col2:
                    st.metric(label="⚛️ Charge Acquise (Q)", value=f"{q_inst_pC:.2f} pC", delta="Charge cumulée")
                with col3:
                    st.metric(label="🔌 Tension du Shunt", value=f"{v_real_faraday:.3f} V", delta=f"Mesure sur {sim.r_shunt/1e6:.1f} MΩ")
                with col4:
                    st.metric(label="📈 Rendement de Filtration", value=f"{estimated_eff * 100.0:.3f} %", delta=f"{m_fuite_sec*1000:.1f} mg/s de fuite", delta_color="inverse" if estimated_eff < 0.995 else "normal")
                
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("⏸️ Système en attente d'acquisition. Activez le commutateur dans le volet latéral gauche pour lancer les captures.")

# ===================================================
# ONGLET 2 : RAPPELS THÉORIQUES ET ÉQUATIONS
# ===================================================
with tab2:
    st.header("Validation Électrotechnique du Capteur Cylindrique")
    st.markdown("### 📐 Équation de Dimensionnement Fondamentale")
    st.write("La capacité géométrique d'une cage de Faraday coaxiale parfaite s'exprime par la relation de Gauss :")
    st.latex(r"\varepsilon_0 \cdot \varepsilon_r \approx 8{,}854 \times 10^{-12} \text{ F/m}")
    
    st.markdown(f"""
    **Application de vos dimensions physiques réelles :**
    * Longueur active du capteur ($L$) = **{sim.longueur_L:.2f} m** (soit 10 cm)
    * Rayon interne de l'électrode active ($R_1$) = **{sim.diametre_int/2:.1f} mm** (Diamètre de 60 mm)
    * Rayon externe de l'écran protecteur ($R_2$) = **{sim.diametre_ext/2:.1f} mm** (Diamètre de 80 mm)
    * Permittivité absolue de l'air sec ($\varepsilon_0 \cdot \varepsilon_r$) = **$8,854 \\times 10^{{-12}}$ F/m**
    
    Le calcul donne la valeur fixe implémentée dans votre programme : **{sim.capacite_faraday * 1e12:.2f} pF**.
    """)
    
    st.markdown("---")
    st.subheader("🔬 Déduction de la Charge Électrostatique Cumulée ($Q$)")
    st.write("La charge instantanée acquise par influence électrostatique pure sur la paroi intérieure reste calculée de manière transparente à partir du Shunt d'adaptation :")
    st.latex(r"Q_{\text{acquise}}(t) = C_{\text{cage}} \times V_{\text{shunt}}(t) = C_{\text{cage}} \times \left( I_{\text{Faraday}}(t) \times R_{\text{shunt}} \right)")

# ===================================================
# ONGLET 3 : DISPOSITIF EXPÉRIMENTAL & INSTRUMENTATION
# ===================================================
# ===================================================
# ONGLET 3 : DISPOSITIF EXPÉRIMENTAL & INSTRUMENTATION
# ===================================================
# ===================================================
# ONGLET 3 : DISPOSITIF EXPÉRIMENTAL & INSTRUMENTATION
# ===================================================
with tab3:
    st.header("📐 Architecture du Dispositif Expérimental")
    
    st.markdown("""
    Cette section détaille la configuration physique et l'interconnexion de l'installation pilote 
    associant le **filtre à manches** industriel et le **capteur d'induction à cage de Faraday**.
    """)
    
    st.subheader("📸 Synoptique Réel de l'Installation")
    
    # Tentative d'affichage de l'image Dispositif.png
    try:
        st.image("Dispositif.png", caption="Synoptique détaillé du dispositif expérimental", use_container_width=True)
    except Exception:
        st.warning("⚠️ L'image 'Dispositif.png' est requise à la racine du projet pour cet affichage.")

    st.subheader("⚙️ Schéma Structurel de la Mesure")
    
    # Votre diagramme SVG pour la partie technique de précision
    svg_dispositif = """
    <svg width="100%" height="300" viewBox="0 0 900 300" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#fcfcfc" rx="10" stroke="#dcdde1" stroke-width="1"/>
      <path d="M 40 150 L 300 150" stroke="#7f8c8d" stroke-width="50" fill="none" opacity="0.25"/>
      <path d="M 40 150 L 260 150" stroke="#e67e22" stroke-width="8" stroke-dasharray="10 5" fill="none"/>
      <polygon points="265,150 255,145 255,155" fill="#e67e22"/>
      <rect x="300" y="70" width="80" height="160" fill="#dcdde1" stroke="#2c3e50" stroke-width="3" rx="4"/>
      <line x1="300" y1="70" x2="380" y2="230" stroke="#7f8c8d" stroke-width="1.5"/>
      <line x1="300" y1="230" x2="380" y2="70" stroke="#7f8c8d" stroke-width="1.5"/>
      <text x="315" y="155" font-family="Arial" font-size="12" fill="#2c3e50" font-weight="bold">Manche</text>
      <text x="325" y="175" font-family="Arial" font-size="12" fill="#2c3e50" font-weight="bold">P84</text>
      <line x1="340" y1="230" x2="340" y2="260" stroke="#c0392b" stroke-width="2.5"/>
      <line x1="325" y1="260" x2="355" y2="260" stroke="#2c3e50" stroke-width="3"/>
      <line x1="330" y1="265" x2="350" y2="265" stroke="#2c3e50" stroke-width="2"/>
      <line x1="335" y1="270" x2="345" y2="270" stroke="#2c3e50" stroke-width="1"/>
      <path d="M 380 150 L 520 150" stroke="#7f8c8d" stroke-width="35" fill="none" opacity="0.2"/>
      <circle cx="420" cy="145" r="3" fill="#e67e22"/>
      <circle cx="450" cy="155" r="4" fill="#e67e22"/>
      <circle cx="480" cy="148" r="3" fill="#e67e22"/>
      <rect x="520" y="75" width="220" height="150" fill="none" stroke="#2c3e50" stroke-width="2"/>
      <rect x="550" y="100" width="160" height="100" fill="none" stroke="#2980b9" stroke-width="3" stroke-dasharray="6 4"/>
      <line x1="630" y1="200" x2="630" y2="240" stroke="#2980b9" stroke-width="2"/>
      <rect x="610" y="240" width="40" height="25" fill="#f5f6fa" stroke="#2c3e50" stroke-width="2"/>
      <text x="620" y="257" font-family="Arial" font-size="12" font-weight="bold" fill="#2c3e50">R_sh</text>
      <line x1="630" y1="265" x2="630" y2="280" stroke="#2c3e50" stroke-width="2"/>
      <text x="50" y="115" font-family="Arial" font-size="12" fill="#e67e22" font-weight="bold">Flux amont chargé (+/-)</text>
      <text x="250" y="45" font-family="Arial" font-size="13" fill="#2c3e50" font-weight="bold">1. Évacuation Triboélectrique</text>
      <text x="365" y="275" font-family="Arial" font-size="11" fill="#c0392b" font-weight="bold">Courant Carcasse (I_carcasse)</text>
      <text x="560" y="45" font-family="Arial" font-size="13" fill="#2980b9" font-weight="bold">2. Capteur à Influence Électrostatique</text>
      <text x="560" y="125" font-family="Arial" font-size="11" fill="#2980b9">Électrode active (Ø 60mm)</text>
      <text x="560" y="215" font-family="Arial" font-size="11" fill="#2c3e50">Blindage de garde (Ø 80mm)</text>
      <text x="665" y="257" font-family="Arial" font-size="11" fill="#2c3e50" font-weight="bold">Shunt 2.5 MΩ</text>
    </svg>
    """
    components.html(svg_dispositif, height=310)
    
    st.divider()
    
    st.subheader("💻 Chaîne d'Acquisition et Connectivité IoT")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("### 1. Conditionnement")
        st.info("Amplificateur de charge (Transimpédance)")
    with col2:
        st.write("### 2. Acquisition (PC)")
        st.success("Numérisation 16-bit")
    with col3:
        st.write("### 3. Couche IoT")
        st.warning("Passerelle MQTT / Modbus")
   
    # Zone d'information mise en page sous forme de colonnes claires
    info_col1, info_col2 = st.columns(2)
    
    with info_col1:
        st.markdown(fr"### 🏭 Spécifications du Filtre à Manches (Média Filtrant)")
        st.markdown(fr"""
        * **Nature du Média :** Fibres polyimides thermostables (Type P84) idéales pour l'industrie du ciment.
        * **Structure Antistatique :** Maillage croisé de fils hautement conducteurs en acier inoxydable ou carbone tricotés à cœur pour évacuer les accumulations de charges par friction (effet triboélectrique).
        * **Évacuation du Courant ($I_{{\text{{carcasse}}}}$) :** Établie par contact direct via le mannequin métallique de support, transitant par la plaque à trous pour finir sa course dans le réseau de terre de l'usine.
        * **Conditions d'utilisation critiques :** * Débit nominal d'air : `{sim.debit_air_nominal:.0f} m³/h`
            * Température maximale tolérée : `{sim.t_critique_tissu:.0f}°C`
        """)
        
    with info_col2:
        st.markdown(fr"### 🔌 Instrumentation & Cage de Faraday Coaxiale")
        st.markdown(fr"""
        * **Architecture du Capteur :** Double cylindre coaxial en alliage d'aluminium à géométrie fixe.
        * **Géométrie de l'électrode utile :** Longueur active $L = {sim.longueur_L*100:.1f}\text{{ cm}}$ | Diamètre intérieur $\varnothing = {sim.diametre_int:.0f}\text{{ mm}}$.
        * **Écran de Blindage externe :** Diamètre $\varnothing = {sim.diametre_ext:.0f}\text{{ mm}}$ raccordé à la masse électronique isolée pour éliminer toute influence électromagnétique ambiante (moteurs, commutateurs industriels).
        * **Étage d'adaptation analogique :**
            * Résistance de Shunt ultra-stable : `{sim.r_shunt/1e6:.1f}\text{{ M}}\Omega`
            * Rôle : Convertisseur Courant-Tension direct ($V = I \cdot R$) permettant de numériser les nano-ampères induits sans saturer l'étage microcontrôleur.
        """)
