import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from dotenv import load_dotenv
import pandas as pd
import numpy as np

load_dotenv()

app = FastAPI(
    title="Berries Analytics Microservice",
    description="Motor analitico con FastAPI, Pandas y SQLAlchemy para trazabilidad y RH",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("No se encontro DATABASE_URL en el archivo .env")

DATABASE_URL = DATABASE_URL.strip().rstrip(";").replace("&channel_binding=require", "")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

@app.get("/api/analytics/health")
def health_check():
    return {"status": "online", "motor": "FastAPI + Pandas + SQLAlchemy"}

@app.get("/api/analytics/dashboard")
def obtener_metricas_directivas():
    try:
        query_lotes = "SELECT codigo_lote, zona_invernadero, estado_calidad, motivo_rechazo FROM lotes"
        df_lotes = pd.read_sql(query_lotes, engine)

        query_cosecha = """
            SELECT 
                r.id as registro_id,
                r.cantidad_cubetas, 
                r.fecha_hora_escaneo,
                t.nombre as cosechador, 
                t.qr_code_uuid as codigo_qr,
                s.nombre as supervisor,
                l.codigo_lote,
                l.zona_invernadero,
                l.estado_calidad,
                l.motivo_rechazo
            FROM registros_cosecha r
            JOIN trabajadores t ON r.cosechador_id = t.id
            JOIN trabajadores s ON r.supervisor_id = s.id
            JOIN lotes l ON r.lote_id = l.id
        """
        df = pd.read_sql(query_cosecha, engine)

        resumen_lotes = df_lotes['estado_calidad'].value_counts().to_dict() if not df_lotes.empty else {}

        if df.empty:
            return {
                "total_cubetas_dia": 0,
                "total_entregas": 0,
                "promedio_cubetas_por_entrega": 0.0,
                "estado_lotes": resumen_lotes,
                "produccion_por_zona": {},
                "produccion_por_lote": {},
                "ranking_rh_cosechadores": [],
                "alertas_calidad_rechazos": []
            }

        total_cubetas = int(df['cantidad_cubetas'].sum())
        total_entregas = int(len(df))
        promedio_entrega = round(float(np.mean(df['cantidad_cubetas'])), 2)

        por_zona = df.groupby('zona_invernadero')['cantidad_cubetas'].sum().astype(int).to_dict()
        por_lote = df.groupby('codigo_lote')['cantidad_cubetas'].sum().astype(int).to_dict()

        ranking_rh = (
            df.groupby(['cosechador', 'codigo_qr'])
            .agg(
                total_cubetas=('cantidad_cubetas', 'sum'),
                numero_entregas=('registro_id', 'count'),
                ultima_entrega=('fecha_hora_escaneo', 'max')
            )
            .reset_index()
            .sort_values(by='total_cubetas', ascending=False)
        )
        ranking_rh['ultima_entrega'] = ranking_rh['ultima_entrega'].astype(str)

        rechazados = df[df['estado_calidad'] == 'RECHAZADO'].copy()
        alertas = []
        if not rechazados.empty:
            rechazados['fecha_hora_escaneo'] = rechazados['fecha_hora_escaneo'].astype(str)
            alertas = rechazados[[
                'codigo_lote', 'zona_invernadero', 'cosechador', 
                'codigo_qr', 'supervisor', 'cantidad_cubetas', 
                'motivo_rechazo', 'fecha_hora_escaneo'
            ]].to_dict(orient='records')

        return {
            "total_cubetas_dia": total_cubetas,
            "total_entregas": total_entregas,
            "promedio_cubetas_por_entrega": promedio_entrega,
            "estado_lotes": resumen_lotes,
            "produccion_por_zona": por_zona,
            "produccion_por_lote": por_lote,
            "ranking_rh_cosechadores": ranking_rh.to_dict(orient='records'),
            "alertas_calidad_rechazos": alertas
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en motor analítico: {str(e)}")