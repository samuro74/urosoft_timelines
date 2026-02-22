import pandas as pd
import numpy as np
import os

# =========================================
# CONFIGURACIÓN
# =========================================

MODO_REPORTE = "ANONIMIZADO"
# "ANONIMIZADO"
# "INSTITUCIONAL"

RUTA_INGRESOS = "Ingresos_Consultorios.csv"
RUTA_EVOLUCIONES = "medicos_evoluciones.csv"
RUTA_TRIAGE = "hora_triage_consulta.csv"

CARPETA_SALIDA = "Reportes_Medicos"
os.makedirs(CARPETA_SALIDA, exist_ok=True)

# =========================================
# CARGA
# =========================================

ingresos = pd.read_csv(
    RUTA_INGRESOS,
    sep="\t",
    encoding="latin1",
    parse_dates=["fechaingreso", "fecha_consulta"]
)

evoluciones = pd.read_csv(
    RUTA_EVOLUCIONES,
    sep="\t",
    encoding="latin1",
    parse_dates=["fecha_evolucion"]
)

triage = pd.read_csv(
    RUTA_TRIAGE,
    sep="\t",
    encoding="latin1",
    parse_dates=["fecha_clasificacion"]
)

# =========================================
# PREPARACIÓN
# =========================================

ingresos = ingresos[
    ingresos["departamento_ingreso"] == "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS"
].copy()

triage["tiempo_clasificacion"] = pd.to_timedelta(
    triage["tiempo_clasificacion"].astype(str)
)

triage["fecha_triage"] = (
    triage["fecha_clasificacion"] +
    triage["tiempo_clasificacion"]
)

triage = triage.drop_duplicates(subset=["triage_id"])

ingresos["duracion"] = ingresos["fecha_consulta"] - ingresos["fechaingreso"]
ingresos["minutos_espera"] = ingresos["duracion"].dt.total_seconds() / 60

ingresos["hora_ingreso"] = ingresos["fechaingreso"].dt.hour

ingresos["turno_12h"] = np.where(
    (ingresos["hora_ingreso"] >= 6) & (ingresos["hora_ingreso"] < 18),
    "DIA (06:00 - 18:00)",
    "NOCHE (18:00 - 06:00)"
)

ingresos["fecha"] = ingresos["fechaingreso"].dt.date

# =========================================
# FUNCIÓN ACTIVIDAD
# =========================================

def buscar_actividad(row):

    if row["minutos_espera"] <= 15:
        return pd.Series(["No aplica", "No aplica"])

    inicio = row["fechaingreso"]
    fin = row["fecha_consulta"]
    medico = row["medico"]

    evos = evoluciones[
        (evoluciones["medico"] == medico) &
        (evoluciones["fecha_evolucion"] >= inicio) &
        (evoluciones["fecha_evolucion"] <= fin)
    ]

    tria = triage[
        (triage["profesional_atiende_descripcion"] == medico) &
        (triage["fecha_triage"] >= inicio) &
        (triage["fecha_triage"] <= fin)
    ]

    fechas_evos = "Sin evoluciones" if evos.empty else " | ".join(
        evos["fecha_evolucion"].dt.strftime("%Y-%m-%d %H:%M:%S")
    )

    fechas_tria = "Sin triage" if tria.empty else " | ".join(
        tria["fecha_triage"].dt.strftime("%Y-%m-%d %H:%M:%S")
    )

    return pd.Series([fechas_evos, fechas_tria])

ingresos[[
    "evoluciones_en_espera",
    "triage_en_espera"
]] = ingresos.apply(buscar_actividad, axis=1)

# =========================================
# FUNCIÓN GENERAR EXCEL
# =========================================

def generar_excel(df, nombre_archivo):

    df["fechaingreso"] = df["fechaingreso"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["fecha_consulta"] = df["fecha_consulta"].dt.strftime("%Y-%m-%d %H:%M:%S")

    tabla_final = df[[
        "ingreso","plan_descripcion","medico",
        "fecha","turno_12h",
        "fechaingreso","fecha_consulta",
        "minutos_espera",
        "evoluciones_en_espera",
        "triage_en_espera"
    ]].copy()

    promedio_general = tabla_final["minutos_espera"].mean()

    promedio_por_medico = tabla_final.groupby("medico")["minutos_espera"].mean().reset_index()
    promedio_por_turno = tabla_final.groupby("turno_12h")["minutos_espera"].mean().reset_index()
    promedio_por_dia = tabla_final.groupby("fecha")["minutos_espera"].mean().reset_index()
    promedio_fecha_turno = tabla_final.groupby(["fecha","turno_12h"])["minutos_espera"].mean().reset_index()
    promedio_medico_fecha_turno = tabla_final.groupby(["medico","fecha","turno_12h"])["minutos_espera"].mean().reset_index()

    with pd.ExcelWriter(nombre_archivo, engine="openpyxl") as writer:

        tabla_final.to_excel(writer,"Detalle",index=False)
        promedio_por_medico.to_excel(writer,"Promedio por Medico",index=False)
        promedio_por_turno.to_excel(writer,"Promedio por Turno",index=False)
        promedio_por_dia.to_excel(writer,"Promedio por Dia",index=False)
        promedio_fecha_turno.to_excel(writer,"Fecha vs Turno",index=False)
        promedio_medico_fecha_turno.to_excel(writer,"Medico Fecha Turno",index=False)

        pd.DataFrame({
            "Promedio General":[round(promedio_general,2)]
        }).to_excel(writer,"Promedio General",index=False)

# =========================================
# EJECUCIÓN SEGÚN MODO
# =========================================

if MODO_REPORTE == "INSTITUCIONAL":

    generar_excel(
        ingresos.copy(),
        "Reporte_Ocupacion_Medica_INSTITUCIONAL.xlsx"
    )

elif MODO_REPORTE == "ANONIMIZADO":

    lista_medicos = ingresos["medico"].dropna().unique()

    for medico_visible in lista_medicos:

        df = ingresos.copy()
        otros = df.loc[df["medico"] != medico_visible,"medico"].unique()
        mapa = {m:f"medico{i+1}" for i,m in enumerate(otros)}

        df["medico"] = df["medico"].apply(
            lambda x: x if x==medico_visible else mapa.get(x,x)
        )

        generar_excel(
            df,
            f"{CARPETA_SALIDA}/Reporte_{medico_visible}.xlsx"
        )

print("\nProceso finalizado")
