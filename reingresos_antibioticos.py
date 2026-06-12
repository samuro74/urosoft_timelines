import pandas as pd
from openpyxl.utils import get_column_letter

# ==========================================
# ANTIBIÓTICOS
# ==========================================

ANTIBIOTICOS = [
    "AMIKACINA",
    "AMPICILINA",
    "AMPICILINA/SULBACTAM",
    "AZITROMICINA",
    "AZTREONAM",
    "CEFADROXILO",
    "CEFALEXINA",
    "CEFALOTINA",
    "CEFAZOLINA",
    "CEFEPIME",
    "CEFOTAXIMA",
    "CEFOXITINA",
    "CEFTAROLINA",
    "CEFTAZIDIMA",
    "CEFTRIAXONA",
    "CIPROFLOXACINA",
    "CLARITROMICINA",
    "CLINDAMICINA",
    "COLISTINA",
    "DAPTOMICINA",
    "DOXICICLINA",
    "ERTAPENEM",
    "FOSFOMICINA",
    "GENTAMICINA",
    "IMIPENEM",
    "LEVOFLOXACINA",
    "LINEZOLID",
    "MEROPENEM",
    "METRONIDAZOL",
    "MOXIFLOXACINA",
    "NITROFURANTOINA",
    "OXACILINA",
    "PIPERACILINA",
    "PIPERACILINA/TAZOBACTAM",
    "POLIMIXINA",
    "RIFAMPICINA",
    "TIGECICLINA",
    "TOBRAMICINA",
    "TRIMETOPRIM",
    "SULFAMETOXAZOL",
    "VANCOMICINA"
]

# ==========================================
# CIRUGÍAS
# ==========================================

cirugias = pd.read_csv(
    "ReporteCirugiaUrosdesde031219.csv",
    sep="\t",
    encoding="latin1",
    low_memory=False
)

cirugias = cirugias.drop_duplicates(subset=["acto_quiru"])

cirugias["fecha_registro"] = pd.to_datetime(
    cirugias["fecha_registro"],
    errors="coerce"
)

cirugias["ID_PACIENTE"] = (
    cirugias["tipo_id_paciente"].astype(str).str.strip()
    + cirugias["paciente_id"].astype(str).str.strip()
)

# ==========================================
# EVOLUCIONES
# ==========================================

evoluciones = pd.read_csv(
    "medicos_evoluciones.csv",
    sep="\t",
    encoding="latin1",
    low_memory=False
)

evoluciones["fecha_evolucion"] = pd.to_datetime(
    evoluciones["fecha_evolucion"],
    errors="coerce"
)

evoluciones["ID_PACIENTE"] = (
    evoluciones["t_id"].astype(str).str.strip()
    + evoluciones["id_paciente"].astype(str).str.strip()
)

evoluciones = evoluciones.sort_values(
    ["ID_PACIENTE", "fecha_evolucion"]
)

evoluciones_por_paciente = {
    p: g for p, g in evoluciones.groupby("ID_PACIENTE")
}

# ==========================================
# SUMINISTROS
# ==========================================

suministros = pd.read_csv(
    "suministro_insumos_y_medicamentos.csv",
    sep="\t",
    encoding="latin1",
    low_memory=False
)

suministros["fecha_registro_control"] = pd.to_datetime(
    suministros["fecha_registro_control"],
    errors="coerce"
)

# Quitar espacios para poder comparar
suministros["ID_PACIENTE"] = (
    suministros["identificacion"]
    .astype(str)
    .str.replace(" ", "", regex=False)
    .str.upper()
)

# Identificar antibióticos
patron_antibioticos = "|".join(ANTIBIOTICOS)

suministros_antibioticos = suministros[
    suministros["medicamento"]
    .astype(str)
    .str.upper()
    .str.contains(
        patron_antibioticos,
        na=False,
        regex=True
    )
].copy()

suministros_por_paciente = {
    p: g
    for p, g in suministros_antibioticos.groupby("ID_PACIENTE")
}

# ==========================================
# REINGRESOS CON ANTIBIÓTICOS
# ==========================================

resultado = []

for _, qx in cirugias.iterrows():

    paciente = qx["ID_PACIENTE"]

    if paciente not in evoluciones_por_paciente:
        continue

    ingreso_qx = qx["ingreso"]
    fecha_qx = qx["fecha_registro"]

    evos = evoluciones_por_paciente[paciente]

    reingresos = evos[
        (evos["fecha_evolucion"] >= fecha_qx)
        & (evos["ingreso"] != ingreso_qx)
    ]

    ingresos_reingreso = (
        reingresos["ingreso"]
        .dropna()
        .unique()
    )

    for ingreso_reingreso in ingresos_reingreso:

        evo_reingreso = (
            reingresos[
                reingresos["ingreso"] == ingreso_reingreso
            ]
            .sort_values("fecha_evolucion")
            .iloc[0]
        )

        fecha_reingreso = evo_reingreso["fecha_evolucion"]

        if paciente not in suministros_por_paciente:
            continue

        meds = suministros_por_paciente[paciente]

        meds_reingreso = meds[
            meds["fecha_registro_control"] >= fecha_reingreso
        ]

        if meds_reingreso.empty:
            continue

        antibioticos_utilizados = (
            meds_reingreso["medicamento"]
            .dropna()
            .astype(str)
            .sort_values()
            .unique()
        )

        resultado.append({
            "acto_quiru": qx["acto_quiru"],
            "ingreso_cirugia": ingreso_qx,
            "fecha_cirugia": fecha_qx,
            "tipo_id_paciente": qx["tipo_id_paciente"],
            "paciente_id": qx["paciente_id"],
            "nombre_paciente":
                f"{qx.get('primer_nombre','')} "
                f"{qx.get('segundo_nombre','')} "
                f"{qx.get('primer_apellido','')} "
                f"{qx.get('segundo_apellido','')}".strip(),
            "ingreso_reingreso": ingreso_reingreso,
            "fecha_reingreso": fecha_reingreso,
            "dias_hasta_reingreso":
                (fecha_reingreso - fecha_qx).days,
            "antibioticos":
                "; ".join(antibioticos_utilizados)
        })

# ==========================================
# RESULTADO
# ==========================================

df_final = pd.DataFrame(resultado)

df_final = df_final.sort_values(
    ["fecha_cirugia", "fecha_reingreso"]
)

# ==========================================
# EXPORTAR A EXCEL
# ==========================================

salida = (
    "reingresos_con_antibioticos.xlsx"
)

with pd.ExcelWriter(
    salida,
    engine="openpyxl"
) as writer:

    df_final.to_excel(
        writer,
        sheet_name="Reingresos",
        index=False
    )

    ws = writer.sheets["Reingresos"]

    for col in ws.columns:
        ancho = max(
            len(str(cell.value))
            if cell.value is not None else 0
            for cell in col
        )
        ws.column_dimensions[
            get_column_letter(col[0].column)
        ].width = min(ancho + 2, 60)

print(f"Reingresos encontrados: {len(df_final):,}")
print(f"Archivo generado: {salida}")
