import pandas as pd
import numpy as np
from datetime import datetime
import os

# ========================
# CONFIGURACIÓN
# ========================
ARCHIVO_INGRESOS = "Ingresos_Consultorios.csv"
ARCHIVO_EVOLUCIONES = "medicos_evoluciones.csv"
ARCHIVO_SALIDA = "informe_productividad_medicos.xlsx"

# Duración en horas de cada turno (ahora 12 horas)
DURACION_TURNO = 12

# ========================
# FUNCIÓN PARA LEER CSV CON FALLBACK DE CODIFICACIÓN
# ========================
def read_csv_fallback(ruta, **kwargs):
    """
    Intenta leer un CSV con varias codificaciones.
    """
    codificaciones = ['cp1252', 'utf-8', 'latin-1']
    for enc in codificaciones:
        try:
            df = pd.read_csv(ruta, delimiter='\t', encoding=enc, **kwargs)
            print(f"  -> Leído con codificación: {enc}")
            return df
        except UnicodeDecodeError:
            continue
    # Si todas fallan, usar 'latin-1' con errors='ignore' como último recurso
    print("  -> Todas las codificaciones fallaron, usando 'latin-1' con errors='ignore'")
    df = pd.read_csv(ruta, delimiter='\t', encoding='latin-1', errors='ignore', **kwargs)
    return df

# ========================
# 1. CARGA Y PROCESAMIENTO DE INGRESOS
# ========================
def procesar_ingresos():
    print("Procesando ingresos...")
    df = read_csv_fallback(ARCHIVO_INGRESOS, dtype=str)
    
    # Convertir fechas
    df['fechaingreso'] = pd.to_datetime(df['fechaingreso'], errors='coerce')
    df['fechacierre_ingreso'] = pd.to_datetime(df['fechacierre_ingreso'], errors='coerce')
    df['fecha_consulta'] = pd.to_datetime(df['fecha_consulta'], errors='coerce')
    
    # Filtro: estacion_enfermeria <> "URGENCIAS PRIORITARIA"
    df = df[df['estacion_enfermeria'] != "URGENCIAS PRIORITARIA"]

    # Eliminar duplicados por ingreso (conservar el primero)
    df = df.drop_duplicates(subset=['ingreso'], keep='first')

    # Seleccionar columnas relevantes
    columnas_ing = ['ingreso', 'medico', 'fecha_consulta', 'hora_consulta']
    for col in columnas_ing:
        if col not in df.columns:
            raise ValueError(f"Columna '{col}' no encontrada en ingresos")
    df_ing = df[columnas_ing].copy()

    # Convertir fecha_consulta a datetime
    df_ing['fecha_consulta'] = pd.to_datetime(df_ing['fecha_consulta'], errors='coerce')

    # Crear una columna datetime unificada: usar fecha_consulta + hora_consulta
    df_ing['fecha'] = df_ing['fecha_consulta'].dt.date

    def combinar_fecha_hora(row):
        if pd.isnull(row['fecha_consulta']) or pd.isnull(row['hora_consulta']):
            return pd.NaT
        try:
            # Si hora_consulta es string, lo parseamos
            if isinstance(row['hora_consulta'], str):
                # Puede tener formato HH:MM:SS o HH:MM
                hora_str = row['hora_consulta'].strip()
                if len(hora_str) == 5:  # HH:MM
                    hora_str += ':00'
                hora_obj = datetime.strptime(hora_str, '%H:%M:%S').time()
            else:
                # Puede ser datetime.time
                hora_obj = row['hora_consulta']
            return datetime.combine(row['fecha'], hora_obj)
        except:
            return pd.NaT

    df_ing['fecha_hora'] = df_ing.apply(combinar_fecha_hora, axis=1)
    # Si falla, usar fecha_consulta directamente (puede contener hora)
    df_ing['fecha_hora'] = df_ing['fecha_hora'].fillna(df_ing['fecha_consulta'])

    # Eliminar filas sin fecha_hora
    df_ing = df_ing.dropna(subset=['fecha_hora'])

    # Agregar columna tipo
    df_ing['tipo'] = 'Ingreso'

    return df_ing[['ingreso', 'medico', 'fecha_hora', 'tipo']]

# ========================
# 2. CARGA Y PROCESAMIENTO DE EVOLUCIONES
# ========================
def procesar_evoluciones():
    print("Procesando evoluciones...")
    df = read_csv_fallback(ARCHIVO_EVOLUCIONES, dtype=str)
    
    # Convertir fecha_evolucion a datetime
    df['fecha_evolucion'] = pd.to_datetime(df['fecha_evolucion'], errors='coerce')
    
    # Filtro departamento
    departamentos_permitidos = [
        "URGENCIAS CONSULTORIOS Y PROCEDIMIENTOS",
        "URGENCIAS GINECOLOGIA",
        "URGENCIAS OBSERVACION ADULTOS",
        "URGENCIAS OBSERVACION PEDIATRICA"
    ]
    df = df[df['departamento'].isin(departamentos_permitidos)]
    
    # Filtro especialidad = MEDICINA GENERAL
    df = df[df['especialidad'] == "MEDICINA GENERAL"]
    
    # Seleccionar columnas
    columnas_ev = ['ingreso', 'medico', 'fecha_evolucion']
    for col in columnas_ev:
        if col not in df.columns:
            raise ValueError(f"Columna '{col}' no encontrada en evoluciones")
    df_ev = df[columnas_ev].copy()
    
    # Renombrar fecha_evolucion a fecha_hora
    df_ev.rename(columns={'fecha_evolucion': 'fecha_hora'}, inplace=True)
    
    # Eliminar filas sin fecha
    df_ev = df_ev.dropna(subset=['fecha_hora'])
    
    df_ev['tipo'] = 'Evolucion'
    
    return df_ev[['ingreso', 'medico', 'fecha_hora', 'tipo']]

# ========================
# 3. COMBINAR DATOS
# ========================
def combinar_datos(df_ing, df_ev):
    print("Combinando datos...")
    df_total = pd.concat([df_ing, df_ev], ignore_index=True)
    # Extraer fecha y hora
    df_total['fecha'] = df_total['fecha_hora'].dt.date
    df_total['hora'] = df_total['fecha_hora'].dt.hour
    df_total['minuto'] = df_total['fecha_hora'].dt.minute

    # Asignar turno (12 horas: día 6-18, noche 18-6)
    def asignar_turno(hora):
        if 6 <= hora < 18:
            return "Día"
        else:
            return "Noche"
    df_total['turno'] = df_total['hora'].apply(asignar_turno)
    return df_total

# ========================
# 4. CÁLCULO DE PRODUCTIVIDAD
# ========================
def calcular_productividad(df_total):
    print("Calculando productividad...")
    # Agrupar por fecha, médico, turno
    resumen_turno = df_total.groupby(['fecha', 'medico', 'turno']).size().reset_index(name='total_atenciones')
    # Calcular atenciones por hora (dividir por duración del turno = 12)
    resumen_turno['atenciones_por_hora'] = resumen_turno['total_atenciones'] / DURACION_TURNO
    # Ordenar
    resumen_turno = resumen_turno.sort_values(['fecha', 'medico', 'turno'])
    
    # Desglose horario (por hora exacta)
    desglose_hora = df_total.groupby(['fecha', 'medico', 'hora', 'tipo']).size().reset_index(name='conteo')
    desglose_hora = desglose_hora.sort_values(['fecha', 'medico', 'hora'])
    
    return resumen_turno, desglose_hora

# ========================
# 5. GUARDAR INFORME
# ========================
def guardar_informe(resumen_turno, desglose_hora):
    print(f"Guardando informe en {ARCHIVO_SALIDA}...")
    with pd.ExcelWriter(ARCHIVO_SALIDA, engine='openpyxl') as writer:
        resumen_turno.to_excel(writer, sheet_name='Resumen diario por turno', index=False)
        desglose_hora.to_excel(writer, sheet_name='Desglose horario', index=False)
    print("¡Informe generado con éxito!")

# ========================
# EJECUCIÓN PRINCIPAL
# ========================
if __name__ == "__main__":
    try:
        df_ing = procesar_ingresos()
        df_ev = procesar_evoluciones()
        df_total = combinar_datos(df_ing, df_ev)
        resumen, desglose = calcular_productividad(df_total)
        guardar_informe(resumen, desglose)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
