import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# Configuration de la page
st.set_page_config(
    page_title="SmartFilter Monitor",
    layout="wide"
)

# En-tête principal épuré
st.title("SmartFilter Monitor")
st.subheader("Supervision Haute Température & Diagnostic Électrostatique - Application Cimenterie")

# --- COEUR DE MODÉLISATION PHYSIQUE (CHARGE ÉLECTROSTATIQUE) ---
class CementFilterSimulation:
    def __init__(self):
        # Paramètres procédé
        self.base_concentration = 1200.0  # mg/m^3 (Charge lourde du four de cimenterie)
        self.nominal_efficiency = 0.9995  # 99.95% (Haute performance avec membrane PTFE)
        self.k_zero = 5.0                 # Sensibilité de base du capteur en pC/(mg/m^3)
        self.alpha = 0.15                 # Coefficient du filtre lisseur EMA
        self.t_critique_tissu = 240.0     # Limite thermique du Polyimide P84 (°C)

    def generate_data_point(self, t, is_mechanically_damaged, temperature):
        # 1. Calcul de la dégradation (Mécanique ou Thermique si T > T_critique)
        thermal_damage = temperature > self.t_critique_tissu
         
        if is_mechanically_damaged or thermal_damage:
            current_eff = 0.978  # Rupture de l'étanchéité des manches
        else:
            current_eff = self.nominal_efficiency
         
        # 2. Concentration d'entrée brute du four (fluctuations industrielles)
        c_in = max(0.0, np.random.normal(self.base_concentration, 60.0))
         
        # 3. Concentration de sortie effective
        c_out = c_in * (1.0 - current_eff)
         
        # 4. Impact de la température sur la charge induite
        # La température dilate les gaz et augmente la vitesse des chocs particulaires sur la sonde.
        # Plus l'impact est énergétique, plus la charge transférée par triboélectricité augmente.
        facteur_temperature = np.sqrt((temperature + 273.15) / 293.15)
        sensor_gain = self.k_zero * facteur_temperature
         
        # 5. Génération de la charge brute induite (en pC) avec bruit de fond
        raw_charge = max(0.0, (c_out * sensor_gain) + np.random.normal(0.0, 2.0))
         
        return raw_charge, current_eff, thermal_damage

# Initialisation de la simulation
sim = CementFilterSimulation()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["📊 Supervision Process Temps Réel", "🔬 Fiche Technique Tissu & Équations"])

# ==========================================
# ONGLET 1 : SUPERVISION EN TEMPS RÉEL
# ==========================================
with tab1:
    st.sidebar.header("Paramètres Opérationnels")
    run_simulation = st.sidebar.toggle("Démarrer le monitoring", value=True)
     
    st.sidebar.markdown("---")
    st.sidebar.subheader("Contrôle du Procédé Four/Broyeur")
    gas_temp = st.sidebar.slider("Température des gaz entrants (°C)", 120, 280, 210)
    trigger_mechanical = st.sidebar.toggle("Simuler une déchirure mécanique", value=False)
    speed = st.sidebar.slider("Fréquence d'échantillonnage (s)", 0.1, 1.0, 0.3)

    # --- CORRECTION DE L'INITIALISATION VARIABLE PAR VARIABLE ---
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
        
    if 'raw_charges' not in st.session_state:
        st.session_state.raw_charges = []
        
    if 'filtered_charges' not in st.session_state:
        st.session_state.filtered_charges = []
        
    if 'efficiencies' not in st.session_state:
        st.session_state.efficiencies = []
        
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
        
    if 'ema_state' not in st.session_state:
        st.session_state.ema_state = None

    if st.sidebar.button("Réinitialiser l'historique"):
        st.session_state.time_steps = []
        st.session_state.raw_charges = []
        st.session_state.filtered_charges = []
        st.session_state.efficiencies = []
        st.session_state.current_step = 0
        st.session_state.ema_state = None
        st.rerun()

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            raw_chg, true_eff, t_damage = sim.generate_data_point(t, trigger_mechanical, gas_temp)
             
            # Application du filtre numérique EMA sur la charge
            if st.session_state.ema_state is None:
                st.session_state.ema_state = raw_chg
            else:
                st.session_state.ema_state = (sim.alpha * raw_chg) + ((1.0 - sim.alpha) * st.session_state.ema_state)
             
            # Ajustement thermodynamique inverse du gain du capteur
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            dynamic_gain = sim.k_zero * facteur_t
             
            # Inversion mathématique : conversion Charge (pC) -> Concentration -> Rendement
            estimated_c_out = st.session_state.ema_state / dynamic_gain
            estimated_eff = 1.0 - (estimated_c_out / sim.base_concentration)
             
            # Stockage dans l'historique glissant
            st.session_state.time_steps.append(t)
            st.session_state.raw_charges.append(raw_chg)
            st.session_state.filtered_charges.append(st.session_state.ema_state)
            st.session_state.efficiencies.append(estimated_eff * 100.0)
             
            if len(st.session_state.time_steps) > 100:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_charges.pop(0)
                st.session_state.filtered_charges.pop(0)
                st.session_state.efficiencies.pop(0)
                 
            # Tracé dynamique Plotly (Unités mises à jour en pC)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_charges),
                                     name="Charge Brute Induite (pC)", line=dict(color='rgba(160,160,160,0.4)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_charges),
                                     name="Charge Filtrée (EMA)", line=dict(color='#1f77b4', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies),
                                     name="Rendement Estimé (%)", line=dict(color='#2ca02c', width=2.5)), row=2, col=1)
            fig.add_hline(y=99.2, line_dash="dash", line_color="red", annotation_text="Seuil Alarme (99.2%)", row=2, col=1)
             
            fig.update_layout(height=550, showlegend=True, margin=dict(l=20, r=20, t=10, b=10))
            fig.update_yaxes(title_text="Charge Électrostatique (pC)", row=1, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=2, col=1)
            fig.update_xaxes(title_text="Temps (Itérations)", row=2, col=1)
             
            with placeholder.container():
                if t_damage:
                    st.error(f"🚨 ALARME THERMIQUE : Gaz à {gas_temp}°C > Limite du tissu Polyimide P84 (240°C) ! Destruction thermique des manches en cours.")
                elif estimated_eff < 0.992:
                    st.warning(f"⚠️ ANOMALIE DE FILTRATION : Fuite détectée (Rupture ou usure mécanique). Rendement : {estimated_eff*100:.3f}%")
                else:
                    st.success(f"✅ PROCÉDÉ SÉCURISÉ : Tissu P84 stable à {gas_temp}°C. Filtration nominale : {estimated_eff*100:.3f}%")
                 
                st.plotly_chart(fig, use_container_width=True)
                 
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("Simulation en pause. Activez le bouton dans la barre latérale pour lancer le monitoring.")

# ==========================================
# ONGLET 2 : FICHE TECHNIQUE TISSU & ÉQUATIONS
# ==========================================
with tab2:
    st.header("Spécifications Avancées du Filtre - Environnement Cimenterie")
     
    st.subheader("📋 Caractéristiques du Tissu Sélectionné : Polyimide P84®")
    data_tissu = {
        "Propriété Physique": [
            "Composition Chimique", 
            "Structure de la Fibre", 
            "Température Maximale en Continu", 
            "Température Maximale en Pointe (Surge)", 
            "Traitement de Surface Additionnel",
            "Résistance aux Acides / Oxydation",
            "Efficacité Initiale (Particules fines de Ciment)"
        ],
        "Spécification Technique": [
            "Polyimide aromatique haute performance (P84)",
            "Section transversale Trilobale (Augmente la surface active de 80%)",
            "240 °C",
            "260 °C",
            "Lamination d'une membrane microporeuse en PTFE (Téflon)",
            "Excellente résistance aux gaz de combustion acides (SOx, NOx)",
            "> 99.95 %"
        ]
    }
    st.table(data_tissu)
     
    st.markdown("---")
     
    # Équations physiques révisées avec la variable de CHARGE Q(t)
    st.subheader("🔬 Couplage Thermo-Électrostatique (Équations de Modélisation)")
     
    st.markdown("#### A. Corrélation Température-Vitesse-Charge")
    st.write("Le transfert de charges électriques par frottement cinétique (effet triboélectrique) dépend directement de la vitesse spatiale du gaz. La dilatation thermique des gaz modifie le gain de transfert de charge $k(T)$, exprimé en picocoulombs par unité de concentration :")
    st.latex(r"k(T) = k_0 \cdot \sqrt{\frac{T_{gaz} + 273.15}{T_{ref} + 273.15}}")
    st.markdown(r"""
    * **$k_0$** : Sensibilité initiale de transfert de charge à température de référence ($5.0 \text{ pC}/(\text{mg/m}^3)$)
    * **$T_{gaz}$** : Température des gaz du four de cimenterie (°C)
    * **$T_{ref}$** : Température d'étalonnage en laboratoire ($20^\circ\text{C} = 293.15\text{ K}$)
    """)

    st.markdown("#### B. Équation Fondamentale de la Charge Électrostatique Induite")
    st.write("La charge instantanée $Q_{raw}(t)$ captée sur l'électrode est proportionnelle à la concentration massique de poussière en sortie, perturbée par un bruit de mesure d'origine électromagnétique $\epsilon(t)$ :")
    st.latex(r"Q_{raw}(t) = k(T) \cdot \Big[ C_{in}(t) \cdot \big(1 - \eta(t, T)\big)\Big] + \epsilon(t)")
    st.latex(r"\epsilon(t) \sim \mathcal{N}(0, \, \sigma_{sensor}^2)")
    st.write("Où $\sigma_{sensor} = 2.0 \text{ pC}$ représente le niveau de bruit de fond de la chaîne d'acquisition.")
     
    st.markdown("#### C. Équation de Filtrage de la Charge (Filtre Numérique)")
    st.write("Le lissage de la charge s'effectue par une moyenne mobile exponentielle récurrente :")
    st.latex(r"Q_{filtered}(t) = \alpha \cdot Q_{raw}(t) + (1 - \alpha) \cdot Q_{filtered}(t-1)")
     
    st.markdown("#### D. Algorithme d'Estimation du Rendement Industrielle")
    st.write("En mesurant la charge filtrée $Q_{filtered}(t)$, le système remonte au rendement estimé $\hat{\eta}(t)$ :")
    st.latex(r"\hat{C}_{out}(t) = \frac{Q_{filtered}(t)}{k(T)}")
    st.latex(r"\hat{\eta}(t) = 1 - \frac{\hat{C}_{out}(t)}{C_{in, nominal}}")
