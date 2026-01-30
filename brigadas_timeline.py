import pandas as pd
import plotly.express as px
ingresos = pd.read_csv(
    "Ingresos_Consultorios.csv",
    sep="\t",
    encoding="latin1",
    parse_dates=[
        "fechaingreso",
        "fecha_consulta",
        "fechacierre_ingreso"
    ]
)

evoluciones = pd.read_csv(
    "medicos_evoluciones.csv",
    sep="\t",
    encoding="latin1",
    parse_dates=["fecha_evolucion"]
)
ultima_evolucion = (
    evoluciones
    .sort_values("fecha_evolucion", ascending=False)
    .groupby("ingreso", as_index=False)
    .first()
)
df = ingresos.merge(
    ultima_evolucion,
    on="ingreso",
    how="left",
    suffixes=("_ingreso", "_evolucion")
)
df["inicio_consulta"] = df["fecha_consulta"]
df["fin_consulta"] = df["fecha_evolucion"]

df["duracion_min"] = (
    (df["fin_consulta"] - df["inicio_consulta"])
    .dt.total_seconds() / 60
)
df_urgencias = df[
    df["departamento_ingreso"] == "URGENCIAS PRIORITARIA"
].copy()
df_urgencias["ingreso_label"] = (
    df_urgencias["ingreso"].astype(str)
    + " | "
    + df_urgencias["nombre_paciente"]
)
fig = px.timeline(
    df_urgencias,
    x_start="inicio_consulta",
    x_end="fin_consulta",
    y="ingreso_label",
    color="medico_ingreso",
    hover_data={
        "duracion_min": True,
        "especialidad": True,
        "estado_del_paciente": True
    },
    title="URGENCIAS PRIORITARIA – Línea de tiempo de consultas médicas"
)

fig.update_yaxes(autorange="reversed")
fig.update_layout(
    xaxis_title="Hora",
    yaxis_title="Ingreso / Paciente",
    legend_title="Médico",
    height=800
)

fig.show()
