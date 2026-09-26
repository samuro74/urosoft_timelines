import pandas as pd
from pathlib import Path

# ==============================================
# CONFIGURACIÓN (ajusta las rutas según tu caso)
# ==============================================

RUTA_CONSULTAS = "Ingresos_Consultorios.csv"
RUTA_EVOLUCIONES = "medicos_evoluciones.csv"
RUTA_SALIDA = "reporte_productividad_medicos.xlsx"

# ==============================================
# FUNCIONES DE CARGA Y LIMPIEZA
# ==============================================

def cargar_consultas(ruta):
    """Carga el CSV de consultas iniciales (ya filtrado y sin duplicados por ingreso)."""
    df = pd.read_csv(ruta, sep='\t', encoding='latin1')  # ajusta encoding si es necesario
    # Asegurar que fecha_consulta es datetime
    df['fecha_consulta'] = pd.to_datetime(df['fecha_consulta'], errors='coerce')
    # Eliminar filas con fecha nula
    df = df.dropna(subset=['fecha_consulta'])
    # Extraer fecha (sin hora) y hora (0-23)
    df['fecha'] = df['fecha_consulta'].dt.date
    df['hora'] = df['fecha_consulta'].dt.hour
    # Solo nos interesan médico, fecha, hora
    return df[['medico', 'fecha', 'hora']]

def cargar_evoluciones(ruta):
    """Carga el CSV de evoluciones (ya filtrado por especialidad y departamentos)."""
    df = pd.read_csv(ruta, sep='\t', encoding='latin1')
    df['fecha_evolucion'] = pd.to_datetime(df['fecha_evolucion'], errors='coerce')
    df = df.dropna(subset=['fecha_evolucion'])
    df['fecha'] = df['fecha_evolucion'].dt.date
    df['hora'] = df['fecha_evolucion'].dt.hour
    return df[['medico', 'fecha', 'hora']]

# ==============================================
# PROCESAMIENTO PRINCIPAL
# ==============================================

def generar_reporte(ruta_consultas, ruta_evoluciones, ruta_salida):
    # 1. Cargar datos
    print("Cargando consultas iniciales...")
    consultas = cargar_consultas(ruta_consultas)
    print(f"  {len(consultas)} registros cargados.")

    print("Cargando evoluciones...")
    evoluciones = cargar_evoluciones(ruta_evoluciones)
    print(f"  {len(evoluciones)} registros cargados.")

    # 2. Agrupar por médico, fecha, hora
    print("Agrupando consultas...")
    consultas_agg = consultas.groupby(['medico', 'fecha', 'hora']).size().reset_index(name='consultas_iniciales')

    print("Agrupando evoluciones...")
    evoluciones_agg = evoluciones.groupby(['medico', 'fecha', 'hora']).size().reset_index(name='evoluciones')

    # 3. Combinar ambos conteos (left join sobre medico, fecha, hora)
    print("Combinando resultados...")
    reporte = consultas_agg.merge(evoluciones_agg, on=['medico', 'fecha', 'hora'], how='outer')

    # 4. Rellenar NaN con 0
    reporte['consultas_iniciales'] = reporte['consultas_iniciales'].fillna(0).astype(int)
    reporte['evoluciones'] = reporte['evoluciones'].fillna(0).astype(int)

    # 5. Calcular total de atenciones por hora
    reporte['total_atenciones'] = reporte['consultas_iniciales'] + reporte['evoluciones']

    # 6. Ordenar por médico, fecha y hora
    reporte = reporte.sort_values(['medico', 'fecha', 'hora']).reset_index(drop=True)

    # 7. Guardar a Excel (también se puede a CSV con to_csv)
    print(f"Guardando reporte en {ruta_salida}...")
    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        # Hoja resumen con todos los datos
        reporte.to_excel(writer, sheet_name='Resumen diario', index=False)

        # Opcional: una hoja por médico
        for medico in reporte['medico'].unique():
            df_medico = reporte[reporte['medico'] == medico]
            # Limitar nombre de hoja a 31 caracteres (Excel)
            sheet_name = medico[:31]
            df_medico.to_excel(writer, sheet_name=sheet_name, index=False)

    print("¡Reporte generado exitosamente!")

# ==============================================
# EJECUCIÓN
# ==============================================

if __name__ == "__main__":
    # Verificar que los archivos existan
    if not Path(RUTA_CONSULTAS).exists():
        print(f"Error: No se encuentra el archivo {RUTA_CONSULTAS}")
    elif not Path(RUTA_EVOLUCIONES).exists():
        print(f"Error: No se encuentra el archivo {RUTA_EVOLUCIONES}")
    else:
        generar_reporte(RUTA_CONSULTAS, RUTA_EVOLUCIONES, RUTA_SALIDA)
