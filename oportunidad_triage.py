import pandas as pd

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------
VENTANA_MINUTOS = 10   # ventana para considerar médico ocupado

# --------------------------------------------------
# 1. CARGAR TRIAGE
# --------------------------------------------------
triage = pd.read_csv(
    "hora_triage_consulta.csv",
    sep="\t",
    encoding="latin1"
)

columnas = [
    "triage_id","fecha_clasificacion","tiempo_clasificacion",
    "triage_descripcion","profesional_atiende","evolucion_id"
]

triage = triage[columnas]
triage = triage[triage["triage_descripcion"] != "NINGUNO"]
triage = triage.drop_duplicates(subset="triage_id")

triage["fecha_clasificacion"] = pd.to_datetime(triage["fecha_clasificacion"], errors="coerce")
triage["tiempo_clasificacion"] = pd.to_timedelta(triage["tiempo_clasificacion"], errors="coerce")
triage["tiempo_clasificacion_min"] = triage["tiempo_clasificacion"].dt.total_seconds() / 60

# --------------------------------------------------
# 2. CARGAR EVOLUCIONES MÉDICAS
# --------------------------------------------------
evo = pd.read_csv(
    "medicos_evoluciones.csv",
    sep="\t",
    encoding="latin1"
)

evo = evo.drop(columns=["usuario_id"], errors="ignore")

evo = evo[
    (evo["especialidad"] == "MEDICINA GENERAL") &
    (
        (evo["departamento"] == "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS") |
        (evo["departamento"] == "URGENCIAS OBSERVACION ADULTOS") |
        (evo["departamento"] == "URGENCIAS OBSERVACION PEDIATRIA")
    )
]

evo = evo.drop(columns=[
    "hallazgo_subjetivo","hallazgo_objetivo",
    "justificacion_hospitalizacion","descripcion",
    "t_id","id_paciente","nombre_paciente"
], errors="ignore")

evo["fecha_evolucion"] = pd.to_datetime(evo["fecha_evolucion"], errors="coerce")

# --------------------------------------------------
# 3. FUNCIÓN PARA SABER QUÉ HACÍA EL MÉDICO
# --------------------------------------------------
def actividad_medico(fila):

    tiempo = fila["tiempo_clasificacion_min"]

    # si no supera 10 minutos no investigar
    if pd.isna(tiempo) or tiempo <= 10:
        return "OK"

    medico = fila["profesional_atiende"]
    momento_triage = fila["fecha_clasificacion"]

    if pd.isna(momento_triage):
        return "SIN FECHA TRIAGE"

    ventana_inicio = momento_triage - pd.Timedelta(minutes=VENTANA_MINUTOS)
    ventana_fin = momento_triage + pd.Timedelta(minutes=VENTANA_MINUTOS)

    evoluciones_medico = evo[evo["medico"] == medico]

    ocupaciones = evoluciones_medico[
        (evoluciones_medico["fecha_evolucion"] >= ventana_inicio) &
        (evoluciones_medico["fecha_evolucion"] <= ventana_fin)
    ]

    if len(ocupaciones) == 0:
        return "SIN REGISTRO DE ACTIVIDAD"

    # describir qué estaba haciendo
    detalles = ocupaciones.apply(
        lambda r: f"Evolución paciente ingreso {r['ingreso']} ({r['fecha_evolucion']})",
        axis=1
    )

    return " | ".join(detalles)

# --------------------------------------------------
# 4. CREAR NUEVA COLUMNA
# --------------------------------------------------
triage["actividad_medico_si_demora"] = triage.apply(actividad_medico, axis=1)

# --------------------------------------------------
# 5. GUARDAR RESULTADO
# --------------------------------------------------
triage.to_csv("triage_con_actividad_medica.csv", index=False)

print("\nArchivo generado: triage_con_actividad_medica.csv")
print(triage.head())
