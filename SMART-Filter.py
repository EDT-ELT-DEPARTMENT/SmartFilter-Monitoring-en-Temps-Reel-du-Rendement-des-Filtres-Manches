import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

# Configuration de la page et rappel des spécifications de la plateforme
st.set_page_config(
    page_title="Plateforme de Supervision en temps réel et diagnostic électrostatique du rendement de filtration",
    layout="wide"
)

# En-tête officiel de l'application
st.title("Plateforme de supervision en temps réel et diagnostic électrostatique du rendement de filtration")
st.subheader("Module de Supervision : Monitoring Intelligent du Filtre à Manches")

# --- MODÉLISATION DU SYSTÈME PHYSIQUE ---
class SmartFilterSimulation:
    def __init__(self):
        self.base_concentration = 1000.0  # mg/m^3
        self.nominal_efficiency = 0.999   # 99.9%
        self.sensor_gain = 5.0            # Facteur de conversion pA/(mg/m^3)
        self.alpha = 0.15                 # Coefficient du filtre EMA

    def generate_data_point(self, t, is_damaged):
        # 1. Évolution du rendement réel du filtre
        current_eff = 0.985 if (is_damaged and t >= 50) else self.nominal_efficiency
        
        # 2. Concentration d'entrée bruitée
        c_in = max(0.0, np.random.normal(self.base_concentration, 40.0))
        
        # 3. Concentration de sortie effective
        c_out = c_in * (1.0 - current_eff)
        
        # 4. Signal brut du capteur électrostatique (Charge en pA)
        raw_signal = max(0.0, (c_out * self.sensor_gain) + np.random.normal(0.0, 1.5))
        
        return raw_signal, current_eff

# Initialisation de la simulation
sim = SmartFilterSimulation()

# --- INTERFACE DE CONTRÔLE SUR LA BARRE LATÉRALE ---
st.sidebar.header("Paramètres de Contrôle")
run_simulation = st.sidebar.toggle("Démarrer la simulation en temps réel", value=True)
trigger_anomaly = st.sidebar.toggle("Simuler une rupture de manche (t >= 50)", value=False)
speed = st.sidebar.slider("Délai de rafraîchissement (secondes)", 0.1, 1.0, 0.3)

# --- ESPACES DE STOCKAGE DES DONNÉES (SESSION STATE) ---
if 'time_steps' not in st.session_state:
    st.session_state.time_steps = []
    st.session_state.raw_signals = []
    st.session_state.filtered_signals = []
    st.session_state.efficiencies = []
    st.session_state.current_step = 0
    st.session_state.ema_state = None

# Bouton de réinitialisation
if st.sidebar.button("Réinitialiser les graphiques"):
    st.session_state.time_steps = []
    st.session_state.raw_signals = []
    st.session_state.filtered_signals = []
    st.session_state.efficiencies = []
    st.session_state.current_step = 0
    st.session_state.ema_state = None
    st.rerun()

# --- ZONE D'AFFICHAGE DYNAMIQUE ---
# st.empty() sert de conteneur mis à jour en continu à chaque itération de la boucle
placeholder = st.empty()

if run_simulation:
    while True:
        t = st.session_state.current_step
        
        # Génération du nouveau point physique
        raw_sig, true_eff = sim.generate_data_point(t, trigger_anomaly)
        
        # Application du filtre numérique EMA (Moyenne Mobile Exponentielle)
        if st.session_state.ema_state is None:
            st.session_state.ema_state = raw_sig
        else:
            st.session_state.ema_state = (sim.alpha * raw_sig) + ((1.0 - sim.alpha) * st.session_state.ema_state)
        
        # Déduction du rendement estimé par le Smart Filtre
        estimated_c_out = st.session_state.ema_state / sim.sensor_gain
        estimated_eff = 1.0 - (estimated_c_out / sim.base_concentration)
        
        # Sauvegarde dans l'historique (fenêtre glissante des 100 derniers points)
        st.session_state.time_steps.append(t)
        st.session_state.raw_signals.append(raw_sig)
        st.session_state.filtered_signals.append(st.session_state.ema_state)
        st.session_state.efficiencies.append(estimated_eff * 100.0)
        
        if len(st.session_state.time_steps) > 100:
            st.session_state.time_steps.pop(0)
            st.session_state.raw_signals.pop(0)
            st.session_state.filtered_signals.pop(0)
            st.session_state.efficiencies.pop(0)
            
        # Construction des graphiques avec Plotly
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
        
        # Graphique 1 : Signal Électrostatique (Charge des particules)
        fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.raw_signals),
                                 name="Signal Brut (pA)", line=dict(color='rgba(150,150,150,0.5)', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.filtered_signals),
                                 name="Signal Filtré (EMA)", line=dict(color='#1f77b4', width=2.5)), row=1, col=1)
        
        # Graphique 2 : Rendement mesuré vs Seuil d'alarme
        fig.add_trace(go.Scatter(x=list(st.session_state.time_steps), y=list(st.session_state.efficiencies),
                                 name="Rendement Estimé (%)", line=dict(color='#2ca02c', width=2.5)), row=2, col=1)
        
        # Ligne de seuil critique (99.2%)
        fig.add_hline(y=99.2, line_dash="dash", line_color="red", annotation_text="Seuil Critique (99.2%)", row=2, col=1)
        
        # Mise en forme globale du layout
        fig.update_layout(height=600, showlegend=True, margin=dict(l=20, r=20, t=20, b=20))
        fig.update_yaxes(title_text="Charge Électrostatique (pA)", row=1, col=1)
        fig.update_yaxes(title_text="Rendement (%)", row=2, col=1)
        fig.update_xaxes(title_text="Temps (Itérations)", row=2, col=1)
        
        # Injection du contenu dynamique dans le conteneur principal
        with placeholder.container():
            # Diagnostic d'alarme en temps réel
            if estimated_eff < 0.992:
                st.error(f"⚠️ ALARME CRITIQUE : Chute de rendement détectée ! Rendement actuel : {estimated_eff*100:.3f}%")
            else:
                st.success(f"✅ Système stable : Filtration nominale en cours. Rendement actuel : {estimated_eff*100:.3f}%")
                
            st.plotly_chart(fig, use_container_width=True)
            
        st.session_state.current_step += 1
        time.sleep(speed)
else:
    st.info("Simulation en pause. Activez le bouton dans la barre latérale pour lancer le monitoring.")
