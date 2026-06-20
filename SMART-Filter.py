import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import pandas as pd
import io

# Configuration complète de la page Streamlit
st.set_page_config(
    page_title="SmartFilter Monitor - Dualité & Géométrie",
    layout="wide"
)

# --- EN-TÊTE RÉGLEMENTAIRE ET RAPPEL DU TITRE ---
st.title("SmartFilter Monitor")
st.subheader("Plateforme de gestion des EDTs-S2-2026-Département d'Électrotechnique-Faculté de génie électrique-UDL-SBA")
st.markdown("### ⚡ Analyseur Multi-paramètres : Dimensions du Capteur, Drainage (Masse) et Charge Acquise (Faraday)")

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
        self.diametre_int = 0.06          # Ø intérieur électrode de mesure (60 mm)
        self.diametre_ext = 0.08          # Ø extérieur écran de blindage (80 mm)
        self.capacite_faraday = 19.33e-12 # Capacité calculée (19.33 pF)
        self.r_shunt = 2.5e6              # Résistance de Shunt de conditionnement (2.5 MΩ)
        
        # Profils de bruit distincts
        self.noise_carcasse_base = 0.5    # Bruit thermique de masse
        self.noise_carcasse_cem = 9.5     # Parasites VFD moteurs sur la carcasse
        self.noise_faraday_nA = 0.12      # Cage de Faraday blindée immunisée

        self.alpha = 0.15                 # Coefficient du filtre EMA

    def generate_data_point(self, t, is_mechanically_damaged, temperature, cem_parasite_active):
        q_sec = self.debit_air_nominal / 3600.0 # Débit en m3/s (125 m3/s)
        
        # Évaluation des défaillances thermiques ou mécaniques
        t_damage = temperature > self.t_critique_tissu
        if is_mechanically_damaged or t_damage: 
            current_eff = 0.978  
        else:
            current_eff = self.nominal_efficiency
         
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        c_out = c_in * (1.0 - current_eff)
        masse_fuite_sec = (c_out * q_sec) / 1000.0  # Fuite particulaire en g/s
         
        # Triboélectricité en fonction de la température
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        charge_specifique = self.k_tribo_base * facteur_temperature
        
        # Courant absolu généré par la séparation de charge
        i_généré_abs = masse_fuite_sec * charge_specifique

        # DUALITÉ PHYSIQUE :
        # 1. Carcasse = Drainage des électrons excédentaires (charges négatives accumulées)
        bruit_c = self.noise_carcasse_cem if cem_parasite_active else self.noise_carcasse_base
        raw_carcasse_neg = - (i_généré_abs + np.random.normal(0.0, bruit_c))

        # 2. Cage de Faraday = Induction sans contact du flux de poussière positive
        raw_faraday_pos = (i_généré_abs + np.random.normal(0.0, self.noise_faraday_nA))
         
        return raw_carcasse_neg, raw_faraday_pos, current_eff, t_damage, q_sec, masse_fuite_sec

# Instanciation de la simulation
sim = CementFilterFaradaySimulation()

# --- COUPE ET FICHE TECHNIQUE DANS LE VOLET LATÉRAL ---
st.sidebar.header("Paramètres Opérationnels")
run_simulation = st.sidebar.toggle("Activer les acquisitions", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Fiche Technique & Dimensions du Capteur")
with st.sidebar.expander("Afficher les spécifications de la Cage", expanded=True):
    st.markdown(f"""
    * **Longueur active ($L$) :** {sim.longueur_L * 100:.1f} cm
    * **Diamètre Intérieur ($\varnothing_{{\text{{int}}}}$) :** {sim.diametre_int * 1000:.1f} mm
    * **Diamètre Extérieur ($\varnothing_{{\text{{ext}}}}$) :** {sim.diametre_ext * 1000:.1f} mm
    * **Milieu Diélectrique :** Air sec ($\epsilon_r \approx 1$)
    * **Capacité Propre ($C_{{\text{{cage}}}}$) :** **{sim.capacite_faraday * 1e12:.2f} pF**
    * **Shunt d'adaptation ($R_{{\text{{shunt}}}}$) :** {sim.r_shunt / 1e6:.1f} MΩ
    """)

st.sidebar.markdown("---")
st.sidebar.subheader("Contrôle du Procédé")
gas_temp = st.sidebar.slider("Température Processus (°C)", 120, 280, 200)
trigger_mechanical = st.sidebar.toggle("Générer déchirure de manche", value=False)
trigger_cem_noise = st.sidebar.toggle("Activer couplage CEM sur masse", value=True)
speed = st.sidebar.slider("Période d'échantillonnage (s)", 0.1, 1.0, 0.3)

# Navigation par onglets principaux
tab1, tab2 = st.tabs(["📊 Suivi Simultané & Charge Acquise", "🔬 Schéma & Validation Électrotechnique"])

# ==========================================
# ONGLET 1 : AFFICHAGE SIMULTANÉ DES PARAMÈTRES
# ==========================================
with tab1:
    # Initialisation complète des états de session pour éviter les ruptures de flux
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
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

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            r_carcasse, r_faraday, true_eff, t_damage, q_sec, m_fuite_sec = sim.generate_data_point(
                t, trigger_mechanical, gas_temp, trigger_cem_noise
            )
             
            # Filtrage Numérique Exponentiel (EMA) - Courant Carcasse Négatif
            if st.session_state.ema_carcasse_state is None:
                st.session_state.ema_carcasse_state = r_carcasse
            else:
                st.session_state.ema_carcasse_state = (sim.alpha * r_carcasse) + ((1.0 - sim.alpha) * st.session_state.ema_carcasse_state)
             
            # Filtrage Numérique Exponentiel (EMA) - Courant Faraday Positif
            if st.session_state.ema_faraday_state is None:
                st.session_state.ema_faraday_state = r_faraday
            else:
                st.session_state.ema_faraday_state = (sim.alpha * r_faraday) + ((1.0 - sim.alpha) * st.session_state.ema_faraday_state)
             
            # --- CALCUL DE LA TENSION ET DE LA CHARGE ACQUISE ---
            # Tension V = I * R sur le Shunt industriel
            v_real_faraday = (st.session_state.ema_faraday_state * 1e-9) * sim.r_shunt
            
            # Charge instantanée acquise par induction sur la capacité propre du capteur : Q = C * V
            # Multiplié par 1e12 pour l'exprimer directement en PicoCoulombs (pC)
            q_inst_pC = (sim.capacite_faraday * v_real_faraday) * 1e12
            
            # Calcul du rendement instantané via le flux d'induction positif
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            i_max_theorique = ((sim.base_concentration * q_sec) / 1000.0) * (sim.k_tribo_base * facteur_t)
            estimated_eff = 1.0 - (st.session_state.ema_faraday_state / i_max_theorique)
            
            # Enregistrement des valeurs calculées dans les structures glissantes (Historique)
            st.session_state.time_steps.append(t)
            st.session_state.raw_carcasse.append(r_carcasse)
            st.session_state.filtered_carcasse.append(st.session_state.ema_carcasse_state)
            st.session_state.raw_faraday.append(r_faraday)
            st.session_state.filtered_faraday.append(st.session_state.ema_faraday_state)
            st.session_state.voltage_faraday.append(v_real_faraday)
            st.session_state.charge_acquise_pC.append(q_inst_pC)
            st.session_state.efficiencies_calculated.append(estimated_eff * 100.0)
             
            # Limitation stricte de la mémoire glissante à 80 points
            if len(st.session_state.time_steps) > 80:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_carcasse.pop(0)
                st.session_state.filtered_carcasse.pop(0)
                st.session_state.raw_faraday.pop(0)
                st.session_state.filtered_faraday.pop(0)
                st.session_state.voltage_faraday.pop(0)
                st.session_state.charge_acquise_pC.pop(0)
                st.session_state.efficiencies_calculated.pop(0)
                 
            # --- CRÉATION DU SUBPLOT ÉLECTROTECHNIQUE ---
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.08,
                subplot_titles=(
                    "📈 Dynamique des Courants Parallèles (Drainage Masse - vs Induction Faraday +)",
                    "⚡ Évolution de la Charge Électrostatique Acquise sur la Cage (Q en pC)", 
                    "📊 Rendement Électrostatique Global du Filtre (%)"
                )
            )
            
            # Graphe 1 : Courants opposés simultanés
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_carcasse),
                                     name="Courant Carcasse (Drainage -)", line=dict(color='#e67e22', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_faraday),
                                     name="Courant Cage Faraday (Induction +)", line=dict(color='#2980b9', width=2.5)), row=1, col=1)
            
            # Graphe 2 : Charge acquise (pC)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.charge_acquise_pC),
                                     name="Charge Induite (Q)", line=dict(color='#9b59b6', width=2.5)), row=2, col=1)
            
            # Graphe 3 : Rendement de captage
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies_calculated),
                                     name="Rendement (%)", line=dict(color='#2ecc71', width=2)), row=3, col=1)
            
            fig.update_layout(height=750, margin=dict(l=30, r=30, t=40, b=10), showlegend=True)
            fig.update_yaxes(title_text="Courants (nA)", row=1, col=1)
            fig.update_yaxes(title_text="Charge Q (pC)", row=2, col=1)
            fig.update_yaxes(title_text="Efficacité (%)", row=3, col=1)
            fig.update_xaxes(title_text="Temps (Échantillons)", row=3, col=1)
            
            # Injection dynamique dans le conteneur principal
            with placeholder.container():
                delta_verification = abs(abs(st.session_state.ema_carcasse_state) - st.session_state.ema_faraday_state)
                
                if t_damage:
                    st.error(f"🚨 EXTRUSION THERMIQUE CRITIQUE : Température de {gas_temp}°C supérieure à la limite du tissu P84 (240°C).")
                elif delta_verification > 5.0 and trigger_cem_noise:
                    st.warning(f"⚡ DISCORDANCE MAILLE DE TERRE (CEM) : Écart de {delta_verification:.2f} nA. Le courant de carcasse subit les moteurs, la cage de Faraday reste stable.")
                elif estimated_eff < 0.992:
                    st.error(f"📉 PERTE DE RENDEMENT : Fuite particulaire détectée par la cage. Efficacité : {estimated_eff*100:.3f}%")
                else:
                    st.success("✅ EQUILIBRE ÉLECTROSTATIQUE PARFAIT : Drainage de masse et induction en totale cohérence phase/amplitude.")

                # --- PANNEAU DE TOUS LES PARAMÈTRES SIMULTANÉS (5 COLONNES) ---
                st.markdown("#### 🎛️ Indicateurs d'Acquisition en Temps Réel")
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric(
                        label="🔏 Courant Carcasse",
                        value=f"{st.session_state.ema_carcasse_state:.2f} nA",
                        delta="Drainage négatif (-)",
                        delta_color="inverse"
                    )
                with col2:
                    st.metric(
                        label="🌐 Courant Faraday",
                        value=f"{st.session_state.ema_faraday_state:.2f} nA",
                        delta="Induction positive (+)"
                    )
                with col3:
                    st.metric(
                        label="⚛️ Charge Aquise (Cage)",
                        value=f"{q_inst_pC:.2f} pC",
                        delta="Charge Q induite",
                        delta_color="normal"
                    )
                with col4:
                    st.metric(
                        label="🔌 Tension Shunt",
                        value=f"{v_real_faraday:.3f} V",
                        delta=f"Sur {sim.r_shunt/1e6:.1f} MΩ"
                    )
                with col5:
                    st.metric(
                        label="📈 Rendement Estimé",
                        value=f"{estimated_eff * 100.0:.3f} %",
                        delta=f"{m_fuite_sec*1000:.1f} mg/s fuite",
                        delta_color="inverse" if estimated_eff < 0.995 else "normal"
                    )
                
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("Système en pause. Activez le commutateur du volet latéral pour lancer l'affichage simultané.")

# ==========================================
# ONGLET 2 : LOGIQUE DES FLUX ET EQUATIONS
# ==========================================
with tab2:
    st.header("Modélisation Avancée et Spécifications de la Cage Coaxiale")
    
    st.markdown("### 📐 Équation Matricielle de Capacité de votre Prototype")
    st.write("La capacité stationnaire de votre cage de Faraday cylindrique s'exprime rigoureusement par :")
    st.latex(r"C_{\text{cage}} = \frac{2 \pi \cdot \varepsilon_0 \cdot \varepsilon_r \cdot L}{\ln\left(\frac{R_2}{R_1}\right)}")
    
    st.markdown(f"""
    En injectant vos dimensions physiques réelles :
    * Longueur active du cylindre ($L$) = **{sim.longueur_L:.2f} m**
    * Rayon interne de l'électrode de mesure ($R_1 = \varnothing_{{\text{{int}}}} / 2$) = **{sim.diametre_int/2:.3f} m**
    * Rayon externe de l'écran de blindage ($R_2 = \varnothing_{{\text{{ext}}}} / 2$) = **{sim.diametre_ext/2:.3f} m**
    * Permittivité absolue de l'air ($\varepsilon_0 \cdot \varepsilon_r$) = **$8,854 \times 10^{{-12}}\text{ F/m}$**
    
    Le calcul donne immédiatement : **{sim.capacite_faraday * 1e12:.2f} pF**.
    """)
    
    st.markdown("---")
    st.subheader("🔬 Déduction de la Charge Électrostatique Acquise ($Q$)")
    st.write("Grâce à l'implantation de la résistance de Shunt ($R_{\text{shunt}}$), la relation entre le courant mesuré et la charge stockée sur l'électrode active est stabilisée et calculée en temps réel selon l'équation :")
    st.latex(r"Q_{\text{acquise}}(t) = C_{\text{cage}} \times V_{\text{shunt}}(t) = C_{\text{cage}} \times \left( I_{\text{Faraday}}(t) \times R_{\text{shunt}} \right)")
    st.write("Cette architecture évite l'intégration infinie des charges qui faussait les lectures de tension initiales, ramenant le capteur à une échelle de mesure industrielle parfaitement calibrée.")
