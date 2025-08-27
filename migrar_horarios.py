#!/usr/bin/env python3
"""
Script para migrar la base de datos añadiendo la tabla de horarios
"""

from app import app
from extensions import db
from models import *
import sqlite3
import os

def migrar_database():
    """Añadir la tabla de horarios a la base de datos existente"""
    
    with app.app_context():
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'pozoleria_new.db')
        
        try:
            # Crear la nueva tabla de horarios
            print("🔄 Añadiendo tabla de horarios...")
            
            # Crear solo la tabla que necesitamos
            with db.engine.connect() as conn:
                conn.execute(db.text('''
                    CREATE TABLE IF NOT EXISTS horario_sucursal (
                        id INTEGER PRIMARY KEY,
                        sucursal_id INTEGER NOT NULL,
                        dia_semana INTEGER NOT NULL,
                        hora_apertura TIME,
                        hora_cierre TIME,
                        cerrado BOOLEAN DEFAULT 0,
                        FOREIGN KEY (sucursal_id) REFERENCES sucursal (id)
                    )
                '''))
                conn.commit()
            
            print("✅ Tabla horario_sucursal creada exitosamente")
            
            # Crear horarios por defecto para las sucursales existentes
            crear_horarios_por_defecto()
            
            print("✅ Migración completada exitosamente!")
            return True
            
        except Exception as e:
            print(f"❌ Error en la migración: {e}")
            return False

def crear_horarios_por_defecto():
    """Crear horarios por defecto para sucursales existentes"""
    try:
        from datetime import time
        
        sucursales = Sucursal.query.all()
        
        for sucursal in sucursales:
            # Verificar si ya tiene horarios
            horarios_existentes = HorarioSucursal.query.filter_by(sucursal_id=sucursal.id).count()
            
            if horarios_existentes == 0:
                print(f"🏪 Creando horarios por defecto para: {sucursal.nombre}")
                
                # Crear horario por defecto: Lunes a Sábado 9:00-22:00, Domingo cerrado
                for dia in range(6):  # Lunes a Sábado
                    horario = HorarioSucursal(
                        sucursal_id=sucursal.id,
                        dia_semana=dia,
                        hora_apertura=time(9, 0),
                        hora_cierre=time(22, 0),
                        cerrado=False
                    )
                    db.session.add(horario)
                
                # Domingo cerrado
                horario_domingo = HorarioSucursal(
                    sucursal_id=sucursal.id,
                    dia_semana=6,
                    cerrado=True
                )
                db.session.add(horario_domingo)
            else:
                print(f"⏭️ {sucursal.nombre} ya tiene horarios configurados")
        
        db.session.commit()
        print("✅ Horarios por defecto creados para todas las sucursales")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creando horarios por defecto: {e}")
        raise

if __name__ == "__main__":
    print("🔄 Migrando base de datos para añadir sistema de horarios...")
    if migrar_database():
        print("\n🎉 ¡Migración completada exitosamente!")
        print("\n📝 Funcionalidades añadidas:")
        print("   ⏰ Gestión de horarios por sucursal")
        print("   🗓️ Configuración día por día")
        print("   🕒 Detección automática de estado (abierto/cerrado)")
        print("   🌍 Zona horaria México City")
        print("   📱 Interfaz móvil para gestión de horarios")
        print("   🔄 Copiar horarios entre sucursales")
        print("\n📋 Horarios por defecto configurados:")
        print("   🕘 Lunes a Sábado: 9:00 - 22:00")
        print("   🚫 Domingo: Cerrado")
        print("\n🎯 Puedes personalizar los horarios desde /admin/sucursales")
    else:
        print("\n💥 Error en la migración")
