import pandas as pd
import plotly.express as px
from datetime import timedelta

# =========================================
# CARGA
# =========================================

ingresos = pd.read_csv(
    "Ingresos_Consultorios.csv",
    sep="\t",
    encoding="latin1",
    parse_dates=["fechaingreso", "fecha_consulta"]
)

evoluciones = pd.read_csv(
    "medicos_evoluciones.csv",
    sep="\t",
    encoding="latin1",
    parse_dates=["fecha_evolucion"]
)

# =========================================
# FILTRO SERVICIO
# =========================================

ingresos = ingresos[
    ingresos["departamento_ingreso"] == "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS"
].copy()

evoluciones = evoluciones[
    (evoluciones["especialidad"] == "MEDICINA GENERAL") &
    (evoluciones["departamento"] == "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS")
].copy()

# Tratar ingreso como texto
ingresos["ingreso"] = ingresos["ingreso"].astype(str)
evoluciones["ingreso"] = evoluciones["ingreso"].astype(str)

# =========================================
# ÚLTIMA EVOLUCIÓN
# =========================================

ultima_evolucion = (
    evoluciones.sort_values("fecha_evolucion")
    .groupby("ingreso")
    .tail(1)
    .rename(columns={"fecha_evolucion": "fin_atencion"})
)

# =========================================
# CRUCE
# =========================================

df = ingresos.merge(
    ultima_evolucion[["ingreso", "fin_atencion"]],
    on="ingreso",
    how="left"
)

# Si no hay evolución → asumir 20 minutos
df["fin_atencion"] = df.apply(
    lambda row: row["fecha_consulta"] + timedelta(minutes=20)
    if pd.isna(row["fin_atencion"])
    else row["fin_atencion"],
    axis=1
)

df["inicio_atencion"] = df["fecha_consulta"]

# =========================================
# ORDENAR POR MÉDICO Y HORA
# =========================================

df = df.sort_values(["medico", "inicio_atencion"])

# =========================================
# DETECTAR SOLAPAMIENTOS
# =========================================

df["nivel"] = 0

for medico in df["medico"].unique():
    sub = df[df["medico"] == medico]
    niveles_fin = []

    for idx, row in sub.iterrows():
        asignado = False
        for nivel, fin in enumerate(niveles_fin):
            if row["inicio_atencion"] >= fin:
                niveles_fin[nivel] = row["fin_atencion"]
                df.loc[idx, "nivel"] = nivel
                asignado = True
                break
        if not asignado:
            niveles_fin.append(row["fin_atencion"])
            df.loc[idx, "nivel"] = len(niveles_fin) - 1

# Crear eje vertical combinado para separar visualmente
df["medico_nivel"] = df["medico"] + " (slot " + df["nivel"].astype(str) + ")"

# =========================================
# GRAFICAR
# =========================================

fig = px.timeline(
    df,
    x_start="inicio_atencion",
    x_end="fin_atencion",
    y="medico_nivel",
    hover_data=["ingreso"]
)

fig.update_yaxes(autorange="reversed")

fig.update_layout(
    title="Línea de tiempo Médico vs Paciente (Ingreso)",
    xaxis_title="Hora",
    yaxis_title="Médico"
)

fig.show()
