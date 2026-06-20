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
st.subheader("Supervision en temps réel et diagnostic électrostatique du rendement de filtration")

# --- COEUR DE MODÉLISATION PHYSIQUE (CLASSES) ---
class SmartFilterSimulation:
    def __init__(self):
        self.base_concentration = 1000.0  # mg/m^3 (C_in nominal)
        self.nominal_efficiency = 0.999   # 99.9% (eta nominal)
        self.sensor_gain = 5.0            # Facteur de conversion k en pA/(mg/m^3)
        self.alpha = 0.15                 # Coefficient de lissage alpha du filtre EMA

    def generate_data_point(self, t, is_damaged):
        # 1. Évolution du rendement réel du filtre eta(t)
        current_eff = 0.985 if (is_damaged and t >= 50) else self.nominal_efficiency
        
        # 2. Concentration d'entrée bruitée C_in(t)
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        
        # 3. Concentration de sortie effective C_out(t)
        c_out = c_in * (1.0 - current_eff)
        
        # 4. Signal brut du capteur électrostatique S_raw(t)
        raw_signal = max(0.0, (c_out * self.sensor_gain) + np.random.normal(0.0, 1.5))
        
        return raw_signal, current_eff

# Initialisation de la simulation
sim = SmartFilterSimulation()

# --- CRÉATION DES ONGLETS DE LA PLATEFORME ---
tab1, tab2 = st.tabs(["📊 Supervision Temps Réel", "🔬 Fondements Théoriques & Équations"])

# ==========================================
# ONGLET 1 : SUPERVISION EN TEMPS RÉEL
# ==========================================
with tab1:
    # Interface de contrôle sur la barre latérale (spécifique à l'onglet de simulation)
    st.sidebar.header("Paramètres de Contrôle")
    run_simulation = st.sidebar.toggle("Démarrer la simulation", value=True)
    trigger_anomaly = st.sidebar.toggle("Simuler une rupture de manche (t >= 50)", value=False)
    speed = st.sidebar.slider("Délai de rafraîchissement (secondes)", 0.1, 1.0, 0.3)

    # Initialisation des variables d'état (Session State)
    if 'time_steps' not in st.session_state:
        st.session_state.time_steps = []
        st.session_state.raw_signals = []
        st.session_state.filtered_signals = []
        st.session_state.efficiencies = []
        st.session_state.current_step = 0
        st.session_state.ema_state = None

    if st.sidebar.button("Réinitialiser les graphiques"):
        st.session_state.time_steps = []
        st.session_state.raw_signals = []
        st.session_state.filtered_signals = []
        st.session_state.efficiencies = []
        st.session_state.current_step = 0
        st.session_state.ema_state = None
        st.rerun()

    placeholder = st.empty()

    if run_simulation:
        # Boucle d'acquisition / simulation continue
        while True:
            t = st.session_state.current_step
            raw_sig, true_eff = sim.generate_data_point(t, trigger_anomaly)
            
            # Application du filtre numérique EMA
            if st.session_state.ema_state is None:
                st.session_state.ema_state = raw_sig
            else:
                st.session_state.ema_state = (sim.alpha * raw_sig) + ((1.0 - sim.alpha) * st.session_state.ema_state)
            
            # Déduction mathématique inverse du rendement estimé
            estimated_c_out = st.session_state.ema_state / sim.sensor_gain
            estimated_eff = 1.0 - (estimated_c_out / sim.base_concentration)
            
            # Stockage des données (Historique glissant)
            st.session_state.time_steps.append(t)
            st.session_state.raw_signals.append(raw_sig)
            st.session_state.filtered_signals.append(st.session_state.ema_state)
            st.session_state.efficiencies.append(estimated_eff * 100.0)
            
            if len(st.session_state.time_steps) > 100:
                st.session_state.time_steps.pop(0)
                st.session_state.raw_signals.pop(0)
                st.session_state.filtered_signals.pop(0)
                st.session_state.efficiencies.pop(0)
                
            # Tracé dynamique Plotly
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_signals),
                                     name="Signal Brut (pA)", line=dict(color='rgba(150,150,150,0.5)', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_signals),
                                     name="Signal Filtré (EMA)", line=dict(color='#1f77b4', width=2.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies),
                                     name="Rendement Estimé (%)", line=dict(color='#2ca02c', width=2.5)), row=2, col=1)
            fig.add_hline(y=99.2, line_dash="dash", line_color="red", annotation_text="Seuil Critique (99.2%)", row=2, col=1)
            
            fig.update_layout(height=550, showlegend=True, margin=dict(l=20, r=20, t=10, b=10))
            fig.update_yaxes(title_text="Charge Électrostatique (pA)", row=1, col=1)
            fig.update_yaxes(title_text="Rendement (%)", row=2, col=1)
            fig.update_xaxes(title_text="Temps (Itérations)", row=2, col=1)
            
            with placeholder.container():
                if estimated_eff < 0.992:
                    st.error(f"⚠️ ALARME CRITIQUE : Chute de rendement détectée ! Rendement estimé : {estimated_eff*100:.3f}%")
                else:
                    st.success(f"✅ Filtration optimale : Mode nominal. Rendement estimé : {estimated_eff*100:.3f}%")
                st.plotly_chart(fig, use_container_width=True)
                
            st.session_state.current_step += 1
            time.sleep(speed)
    else:
        st.info("Simulation en pause. Activez le bouton dans la barre latérale pour lancer le monitoring.")

# ==========================================
# ONGLET 2 : FONDEMENTS THÉORIQUES & ÉQUATIONS
# ==========================================
with tab2:
    st.header("Documentation Scientifique du Modèle Physique")
    st.write("Cette page répertorie l'intégralité des équations physiques et des modèles de traitement du signal codés au sein de la plateforme.")
    
    st.markdown("---")
    
    # 1. Équation du flux de gaz entrant
    st.subheader("1. Modélisation Stochastique du Flux de Gaz")
    st.write("La concentration massique particulaire en amont du filtre $C_{in}(t)$ subit des fluctuations stochastiques naturelles autour d'une valeur moyenne, modélisée par une loi normale (distribution gaussienne) :")
    st.latex(r"C_{in}(t) \sim \mathcal{N}(\mu_{in}, \, \sigma_{in}^2)")
    st.markdown(r"""
    * **$\mu_{in}$** : Concentration de base nominale ($1000.0 \text{ mg/m}^3$)
    * **$\sigma_{in}$** : Écart-type représentant les instabilités du flux aéraulique ($40.0 \text{ mg/m}^3$)
    """)

    st.markdown("---")

    # 2. Rendement et équation du filtre
    st.subheader("2. Dynamique de Filtration & Mode de Défaillance")
    st.write("Le rendement réel du filtre à manches $\eta(t)$ bascule de manière discrète lors de l'apparition d'une anomalie physique (déchirure ou perforation d'une manche) :")
    st.latex(r"\eta(t) = \begin{cases} \eta_{nominal} = 0.999 & \text{si } t < t_{anomalie} \\ \eta_{degrade} = 0.985 & \text{si } t \ge t_{anomalie} \end{cases}")
    
    st.write("La concentration massique de poussière résiduelle s'échappant en aval du filtre $C_{out}(t)$ est régie par la loi de conservation de masse :")
    st.latex(r"C_{out}(t) = C_{in}(t) \cdot \big(1 - \eta(t)\big)")

    st.markdown("---")

    # 3. Capteur électrostatique / triboélectricité
    st.subheader("3. Principe du Capteur Électrostatique (Triboélectricité)")
    st.write("À vitesse de flux constante, l'intensité du signal électrique ou de la charge induite par frottement cinétique des particules (effet triboélectrique) $S_{raw}(t)$ est proportionnelle à la concentration massique de sortie. Le signal subit également un bruit blanc gaussien lié aux interférences électromagnétiques industrielles :")
    st.latex(r"S_{raw}(t) = k \cdot C_{out}(t) + \epsilon(t)")
    st.latex(r"\epsilon(t) \sim \mathcal{N}(0, \, \sigma_{sensor}^2)")
    st.markdown(r"""
    * **$k$** : Facteur d'amplification/calibration du capteur ($5.0 \text{ pA}/(\text{mg/m}^3)$)
    * **$\epsilon(t)$** : Bruit de fond instrumental de l'électronique de mesure ($\sigma_{sensor} = 1.5 \text{ pA}$)
    """)

    st.markdown("---")

    # 4. Traitement du signal / Filtre EMA
    st.subheader("4. Algorithme de Filtrage Numérique : Moyenne Mobile Exponentielle (EMA)")
    st.write("Pour éliminer le bruit haute fréquence du capteur sans saturer la mémoire avec un historique massif, un filtre récurrent passe-bas de type *Exponential Moving Average* (EMA) est implémenté en temps réel :")
    st.latex(r"S_{filtered}(t) = \alpha \cdot S_{raw}(t) + (1 - \alpha) \cdot S_{filtered}(t-1)")
    st.write("Où $\alpha = 0.15$ représente le facteur de lissage. Plus $\alpha$ est petit, plus le filtrage est fort, mais au détriment d'un léger retard de phase (lag).")

    st.markdown("---")

    # 5. Déduction inverse du rendement
    st.subheader("5. Inversion du Modèle et Estimation du Rendement")
    st.write("Le *Smart Monitor* réalise une inversion mathématique continue du modèle du capteur pour reconstituer la concentration de sortie filtrée $\hat{C}_{out}(t)$ :")
    st.latex(r"\hat{C}_{out}(t) = \frac{S_{filtered}(t)}{k}")
    
    st.write("En confrontant cette estimation à la concentration d'entrée de référence, le système calcule le rendement instantané estimé $\hat{\eta}(t)$ :")
    st.latex(r"\hat{\eta}(t) = 1 - \frac{\hat{C}_{out}(t)}{C_{in, nominal}}")
    
    st.write("L'alarme se déclenche automatiquement dès que la condition suivante est vérifiée :")
    st.latex(r"\hat{\eta}(t) < \text{Seuil Critique } (99.2\%)")
