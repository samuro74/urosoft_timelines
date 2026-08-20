import pandas as pd
import numpy as np
import plotly.express as px
import ipywidgets as widgets
from IPython.display import display
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 1. CARGA DE DATOS
# ============================================================

agenda_file = "urgencias_consulta_agenda.csv"
ingresos_file = "Ingresos_Consultorios.csv"
evoluciones_file = "medicos_evoluciones.csv"

# Cargar agenda
agenda = pd.read_csv(agenda_file, delimiter='\t', encoding='latin1',
                     dtype={'t_id': str, 'paciente_id': str, 'num_celular': str,
                            'cantidad_citas': 'Int64', 'estado_agenda_d': str,
                            'observacion': str, 'observacion_cancelacion': str,
                            'usuario_agendo': str},
                     parse_dates=['fecha_agendamiento', 'fecha_registro'])

# Cargar ingresos
ingresos = pd.read_csv(ingresos_file, delimiter='\t', encoding='latin1',
                       dtype={'ingreso': 'Int64', 'estado': 'Int64',
                              'numerodecuenta': 'Int64', 'total_cuenta': 'Int64',
                              'estadocuenta': str, 'tipo_id_paciente': str,
                              'paciente_id': str, 'estado_del_paciente': str,
                              'plan_descripcion': str, 'estacion_enfermeria': str,
                              'departamento_actual': str, 'departamento_ingreso': str,
                              'medico': str},
                       parse_dates=['fechaingreso', 'fechacierre_ingreso', 'fecha_consulta'])

# Cargar evoluciones
evoluciones = pd.read_csv(evoluciones_file, delimiter='\t', encoding='latin1',
                          dtype={'evolucion_id': 'Int64', 'usuario_id': 'Int64',
                                 'medico': str, 'departamento': str, 'especialidad': str,
                                 'ingreso': 'Int64', 't_id': str, 'id_paciente': str,
                                 'nombre_paciente': str, 'hallazgo_subjetivo': str,
                                 'hallazgo_objetivo': str,
                                 'justificacion_hospitalizacion': str,
                                 'descripcion': str},
                          parse_dates=['fecha_evolucion'])

# ============================================================
# 2. PROCESAMIENTO DE AGENDA (solo ADMISIONADOS y únicos por paciente)
# ============================================================

agenda_adm = agenda[agenda['estado_agenda_d'] == 'ADMISIONADO'].copy()
agenda_adm.drop_duplicates(subset=['paciente_id'], keep='first', inplace=True)

cols_agenda = ['fecha_agendamiento', 't_id', 'paciente_id', 'nombre_paciente',
               'especialidades', 'nombre_medico', 'plan_descripcion',
               'estado_agenda_d', 'observacion', 'observacion_cancelacion']
agenda_adm = agenda_adm[cols_agenda]

# ============================================================
# 3. PROCESAMIENTO DE INGRESOS (solo URGENCIAS PRIORITARIA y únicos por ingreso)
# ============================================================

ingresos_up = ingresos[ingresos['departamento_ingreso'] == 'URGENCIAS PRIORITARIA'].copy()
ingresos_up.drop_duplicates(subset=['ingreso'], keep='first', inplace=True)

cols_ingresos = ['ingreso', 'estadocuenta', 'fechaingreso', 'tipo_id_paciente',
                 'paciente_id', 'estado_del_paciente', 'estacion_enfermeria',
                 'departamento_actual', 'departamento_ingreso', 'medico',
                 'fecha_consulta', 'hora_consulta']
ingresos_up = ingresos_up[cols_ingresos]

# ============================================================
# 4. CRUCE AGENDA - INGRESOS (Left Join por t_id y paciente_id)
# ============================================================

cruce = pd.merge(agenda_adm, ingresos_up,
                 left_on=['t_id', 'paciente_id'],
                 right_on=['tipo_id_paciente', 'paciente_id'],
                 how='left', suffixes=('_agenda', '_ingreso'))

# ============================================================
# 5. OBTENER ÚLTIMA EVOLUCIÓN POR INGRESO Y ESPECIALIDAD AGENDADA
# ============================================================

# Extraer primera especialidad de la agenda
cruce['especialidad_agenda'] = cruce['especialidades'].fillna('').str.split(',').str[0].str.strip()
cruce['especialidad_agenda'] = cruce['especialidad_agenda'].replace('', np.nan)

# Unir evoluciones
evol_cruce = pd.merge(evoluciones, cruce[['ingreso', 'paciente_id', 'especialidad_agenda']],
                      on='ingreso', how='inner')

# Filtrar solo evoluciones cuya especialidad coincida con la agendada
evol_cruce_filt = evol_cruce[
    (evol_cruce['especialidad'] == evol_cruce['especialidad_agenda']) &
    (evol_cruce['especialidad_agenda'].notna())
]

# Última fecha de evolución por ingreso
ultima_evol = evol_cruce_filt.groupby('ingreso').agg(
    ultima_fecha_evolucion=('fecha_evolucion', 'max')
).reset_index()

# Unir al cruce
cruce_final = pd.merge(cruce, ultima_evol, on='ingreso', how='left')

# ============================================================
# 6. CALCULAR DURACIÓN Y PREPARAR DATOS PARA EL TIMELINE
# ============================================================

# Calcular duración en minutos (desde fecha_consulta hasta última evolución)
cruce_final['inicio_consulta'] = cruce_final['fecha_consulta']
cruce_final['fin_consulta'] = cruce_final['ultima_fecha_evolucion']
cruce_final['duracion_min'] = (cruce_final['fin_consulta'] - cruce_final['inicio_consulta']).dt.total_seconds() / 60

# Eliminar registros sin evolución (duración nula)
df_timeline = cruce_final.dropna(subset=['duracion_min']).copy()

# Crear etiqueta para el eje Y: ingreso + nombre_paciente
df_timeline['ingreso_label'] = df_timeline['ingreso'].astype(str) + ' | ' + df_timeline['nombre_paciente']

# ============================================================
# 7. GRÁFICO INTERACTIVO CON FILTRO POR ESPECIALIDAD
# ============================================================

# Obtener lista de especialidades disponibles (excluyendo NaN)
especialidades = ['Todos'] + sorted(df_timeline['especialidad_agenda'].dropna().unique().tolist())

def update_plot(especialidad):
    # Filtrar datos según especialidad seleccionada
    if especialidad == 'Todos':
        df_filt = df_timeline
    else:
        df_filt = df_timeline[df_timeline['especialidad_agenda'] == especialidad]
    
    if df_filt.empty:
        print("No hay datos para la especialidad seleccionada.")
        return
    
    # Crear el gráfico de líneas de tiempo (Gantt)
    fig = px.timeline(
        df_filt,
        x_start='inicio_consulta',
        x_end='fin_consulta',
        y='ingreso_label',
        color='medico',
        hover_data={
            'duracion_min': ':.1f',
            'especialidad_agenda': True,
            'estado_del_paciente': True,
            'nombre_paciente': True
        },
        title=f'URGENCIAS PRIORITARIA – Línea de tiempo de consultas médicas ({especialidad})'
    )
    
    # Invertir el orden del eje Y (más reciente arriba)
    fig.update_yaxes(autorange='reversed')
    
    # Personalizar layout
    fig.update_layout(
        xaxis_title='Fecha y hora',
        yaxis_title='Ingreso / Paciente',
        legend_title='Médico',
        height=max(600, len(df_filt) * 20),  # Ajuste dinámico de altura
        hoverlabel=dict(bgcolor='white', font_size=12)
    )
    
    fig.show()
    
    # Mostrar estadísticas resumidas
    print(f"\n=== Estadísticas para {especialidad} ===")
    print(f"Total de casos: {len(df_filt)}")
    print(df_filt['duracion_min'].describe().round(2))

# Crear el widget de selección
dropdown = widgets.Dropdown(
    options=especialidades,
    value='Todos',
    description='Especialidad:'
)

interactivo = widgets.interactive(update_plot, especialidad=dropdown)
display(interactivo)

# ============================================================
# 8. GUARDAR RESULTADOS
# ============================================================

# Guardar tabla final para análisis externo
df_timeline.to_csv('lineas_tiempo_resultado.csv', index=False, sep=';', encoding='utf-8-sig')
print("\nTabla final guardada como 'lineas_tiempo_resultado.csv'")

# Resumen por especialidad
resumen_esp = df_timeline.groupby('especialidad_agenda').agg(
    conteo=('duracion_min', 'count'),
    media_min=('duracion_min', 'mean'),
    mediana_min=('duracion_min', 'median'),
    desviacion_min=('duracion_min', 'std'),
    min_min=('duracion_min', 'min'),
    max_min=('duracion_min', 'max')
).reset_index()
resumen_esp.to_csv('resumen_especialidades.csv', index=False, sep=';', encoding='utf-8-sig')
print("Resumen por especialidad guardado como 'resumen_especialidades.csv'")
