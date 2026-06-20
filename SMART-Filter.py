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

# --- COEUR DE MODÉLISATION PHYSIQUE ADAPTÉE AUX CIMENTS ---
class CementFilterSimulation:
    def __init__(self):
        # Paramètres cimenterie
        self.base_concentration = 1200.0  # mg/m^3 (Charge lourde typique d'un four)
        self.nominal_efficiency = 0.9995  # 99.95% (Haute performance avec membrane PTFE)
        self.k_zero = 5.0                 # Gain de base du capteur à 20°C
        self.alpha = 0.15                 # Coefficient du filtre EMA
        self.t_critique_tissu = 240.0     # Limite thermique du Polyimide P84 (°C)

    def generate_data_point(self, t, is_mechanically_damaged, temperature):
        # 1. Calcul de la dégradation (Mécanique ou Thermique si T > T_critique)
        thermal_damage = temperature > self.t_critique_tissu
        
        if is_mechanically_damaged or thermal_damage:
            # Perte d'étanchéité de la membrane
            current_eff = 0.978 
        else:
            current_eff = self.nominal_efficiency
        
        # 2. Concentration d'entrée brute du four (avec fortes variations de process)
        c_in = max(0.0, np.random.normal(self.base_concentration, 60.0))
        
        # 3. Concentration de sortie
        c_out = c_in * (1.0 - current_eff)
        
        # 4. Impact de la température sur le capteur électrostatique
        # La hausse de température dilate les gaz, augmentant la vitesse linéaire (V) du flux.
        # La charge triboélectrique reçue dépend de la vitesse de collision : k augmente avec T.
        facteur_temperature = sqrt_factor = np.sqrt((temperature + 273.15) / 293.15)
        sensor_gain = self.k_zero * facteur_temperature
        
        # 5. Génération du signal brut bruitée
        raw_signal = max(0.0, (c_out * sensor_gain) + np.random.normal(0.0, 2.0))
        
        return raw_signal, current_eff, thermal_damage

# Initialisation
sim = CementFilterSimulation()

# --- ONGLETS ---
tab1, tab2 = st.tabs(["📊 Supervision Process Temps Réel", "🔬 Fiche Technique Tissu & Équations"])

# ==========================================
# ONGLET 1 : SUPERVISION EN TEMPS RÉEL
# ==========================================
with tab1:
    # Barre latérale pour les contrôles industriels
    st.sidebar.header("Paramètres Opérationnels")
    run_simulation = st.sidebar.toggle("Démarrer le monitoring", value=True)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Contrôle du Procédé Four/Broyeur")
    # Curseur de température simulant les gaz du four de cimenterie
    gas_temp = st.sidebar.slider("Température des gaz entrants (°C)", 120, 280, 210)
    trigger_mechanical = st.sidebar.toggle("Simuler une déchirure mécanique", value=False)
    speed = st.sidebar.slider("Fréquence d'échantillonnage (s)", 0.1, 1.0, 0.3)

    # État de la session
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
        st.session_state.raw_signals = []
        st.session_state.filtered_signals = []
        st.session_state.efficiencies = []
        st.session_state.current_step = 0
        st.session_state.ema_state = None

    if st.sidebar.button("Réinitialiser l'historique"):
        st.session_state.time_steps = []
        st.session_state.raw_signals = []
        st.session_state.filtered_signals = []
        st.session_state.efficiencies = []
        st.session_state.current_step = 0
        st.session_state.ema_state = None
        st.rerun()

    placeholder = st.empty()

    if run_simulation:
        while True:
            t = st.session_state.current_step
            raw_sig, true_eff, t_damage = sim.generate_data_point(t, trigger_mechanical, gas_temp)
            
            # Filtre de traitement du signal (EMA)
            if st.session_state.ema_state is None:
                st.session_state.ema_state = raw_sig
            else:
                st.session_state.ema_state = (sim.alpha * raw_sig) + ((1.0 - sim.alpha) * st.session_state.ema_state)
            
            # Recalcul dynamique de l'état du capteur ajusté par la température
            facteur_t = np.sqrt((gas_temp + 273.15) / 293.15)
            dynamic_gain = sim.k_zero * facteur_t
            
            # Calcul inverse pour estimer l'efficacité
            estimated_c_out = st.session_state.ema_state / dynamic_gain
            estimated_eff = 1.0 - (estimated_c_out / sim.base_concentration)
            
            # Historique
            st.session_state.time_steps.append(t)
            st.session_state.raw_signals.append(raw_sig)
            st.session_state.filtered_signals.append(st.session_state.ema_state)
            st.session_state.efficiencies.append(estimated_eff * 100.0)
            
            if len(st.session_state.time_steps) > 100:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_signals.pop(0)
                st.session_state.filtered_signals.pop(0)
                st.session_state.efficiencies.pop(0)
                
            # Graphiques Plotly
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_signals),
                                     name="Signal Brut Triboélectrique (pA)", line=dict(color='rgba(160,160,160,0.4)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_signals),
                                     name="Signal Filtré (EMA)", line=dict(color='#1f77b4', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies),
                                     name="Rendement Estimé (%)", line=dict(color='#2ca02c', width=2.5)), row=2, col=1)
            fig.add_hline(y=99.2, line_dash="dash", line_color="red", annotation_text="Seuil Alarme (99.2%)", row=2, col=1)
            
            fig.update_layout(height=550, showlegend=True, margin=dict(l=20, r=20, t=10, b=10))
            fig.update_yaxes(title_text="Courant Capteur (pA)", row=1, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=2, col=1)
            fig.update_xaxes(title_text="Temps (Itérations)", row=2, col=1)
            
            with placeholder.container():
                # Gestion des diagnostics d'alertes complexes
                if t_damage:
                    st.error(f"🚨 ALARME THERMIQUE : La température du gaz ({gas_temp}°C) dépasse la limite du tissu Polyimide P84 (240°C) ! Destruction thermique des manches en cours.")
                elif estimated_eff < 0.992:
                    st.warning(f"⚠️ ANOMALIE DE FILTRATION : Fuite détectée (Rupture ou usure mécanique). Rendement : {estimated_eff*100:.3f}%")
                else:
                    st.success(f"✅ PROCÉDÉ SÉCURISÉ : Tissu P84 stable à {gas_temp}°C. Filtration nominale : {estimated_eff*100:.3f}%")
                
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)

# ==========================================
# ONGLET 2 : FICHE TECHNIQUE TISSU & ÉQUATIONS
# ==========================================
with tab2:
    st.header("Spécifications Avancées du Filtre - Environnement Cimenterie")
    
    # Présentation des caractéristiques du matériau sous forme de tableau propre
    st.subheader("📋 Caractéristiques du Tissu Sélectionné : Polyimide P84®")
    st.write("Pour résister aux gaz chauds et à l'abrasion sévère des poussières de clinker de ciment, le matériau suivant est implémenté :")
    
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
    
    # Équations physiques révisées avec la température
    st.subheader("🔬 Couplage Thermo-Électrostatique (Équations de Modélisation)")
    
    st.markdown("#### A. Corrélation Température-Vitesse-Charge")
    st.write("Dans une cimenterie, la hausse de température engendre une dilatation thermique des gaz selon la loi des gaz parfaits. À débit massique constant, la vitesse volumique linéaire $V(t)$ du gaz augmente. L'intensité de la charge générée par effet triboélectrique $S_{raw}$ étant corrélée à l'énergie cinétique des chocs des particules sur la sonde, le gain du capteur $k(T)$ s'ajuste dynamiquement via la relation :")
    st.latex(r"k(T) = k_0 \cdot \sqrt{\frac{T_{gaz} + 273.15}{T_{ref} + 273.15}}")
    st.markdown(r"""
    * **$k_0$** : Sensibilité initiale du capteur à température ambiante ($5.0 \text{ pA}/(\text{mg/m}^3)$)
    * **$T_{gaz}$** : Température actuelle lue par le thermocouple de procédé (°C)
    * **$T_{ref}$** : Température de référence d'étalonnage ($20^\circ\text{C} = 293.15\text{ K}$)
    """)

    st.markdown("#### B. Équation Graphique du Signal de Sortie Électrostatique")
    st.latex(r"S_{raw}(t) = k(T) \cdot \Big[ C_{in}(t) \cdot \big(1 - \eta(t, T)\Big] + \epsilon(t)")
    
    st.markdown("#### C. Seuil d'Effondrement Thermique du Matériau")
    st.write("Le rendement réel $\eta$ devient une fonction dépendante du dépassement du seuil thermique maximal du polymère P84 :")
    st.latex(r"\eta(t, T) = \begin{cases} 0.9995 & \text{si } T_{gaz} \le 240^\circ\text{C} \quad \text{(Mode Stable)} \\ 0.9780 & \text{si } T_{gaz} > 240^\circ\text{C} \quad \text{(Fusion / Dégradation Thermique)} \end{cases}")
    
    st.markdown("#### D. Algorithme de Reconstruction du Rendement")
    st.write("Le filtre informatique annule le bruit blanc $\epsilon(t)$ via l'estimateur EMA, puis isole le rendement estimé $\hat{\eta}(t)$ :")
    st.latex(r"\hat{C}_{out}(t) = \frac{S_{filtered}(t)}{k(T)}")
    st.latex(r"\hat{\eta}(t) = 1 - \frac{\hat{C}_{out}(t)}{C_{in, nominal}}")
