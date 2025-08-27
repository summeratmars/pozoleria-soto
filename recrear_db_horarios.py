#!/usr/bin/env python3
"""
Script para recrear la base de datos con el nuevo modelo de horarios
"""

from app import app
from extensions import db
from models import *
import os

def recrear_database():
    """Recrear la base de datos con las nuevas tablas"""
    
    with app.app_context():
        # Eliminar la base de datos actual si existe
        db_path = os.path.join(os.path.dirname(__file__), 'instance', 'pozoleria_new.db')
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"✅ Base de datos anterior eliminada: {db_path}")
            except Exception as e:
                print(f"❌ Error eliminando base de datos: {e}")
                return False
        
        try:
            # Crear todas las tablas
            db.create_all()
            print("✅ Tablas creadas exitosamente:")
            
            # Listar las tablas creadas
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            for table in tables:
                print(f"   - {table}")
            
            # Crear datos de ejemplo
            crear_datos_ejemplo()
            
            print("✅ Base de datos recreada exitosamente con horarios!")
            return True
            
        except Exception as e:
            print(f"❌ Error creando tablas: {e}")
            return False

def crear_datos_ejemplo():
    """Crear datos de ejemplo incluyendo horarios"""
    try:
        # Crear categorías
        categoria_pozoles = Categoria(nombre="Pozoles")
        categoria_bebidas = Categoria(nombre="Bebidas")
        categoria_antojitos = Categoria(nombre="Antojitos")
        
        db.session.add_all([categoria_pozoles, categoria_bebidas, categoria_antojitos])
        db.session.flush()
        
        # Crear sucursales
        sucursal_centro = Sucursal(
            nombre="Pozolería Centro",
            direccion="Av. Juárez 123, Centro, Ciudad de México",
            telefono="55-1234-5678",
            activa=True
        )
        
        sucursal_roma = Sucursal(
            nombre="Pozolería Roma Norte",
            direccion="Av. Álvaro Obregón 456, Roma Norte, Ciudad de México",
            telefono="55-8765-4321",
            activa=True
        )
        
        sucursal_polanco = Sucursal(
            nombre="Pozolería Polanco",
            direccion="Av. Presidente Masaryk 789, Polanco, Ciudad de México",
            telefono="55-9876-5432",
            activa=False  # Esta estará cerrada temporalmente
        )
        
        db.session.add_all([sucursal_centro, sucursal_roma, sucursal_polanco])
        db.session.flush()
        
        # Crear horarios para Sucursal Centro (Lunes a Domingo 9:00-22:00)
        from datetime import time
        for dia in range(7):
            horario = HorarioSucursal(
                sucursal_id=sucursal_centro.id,
                dia_semana=dia,
                hora_apertura=time(9, 0),
                hora_cierre=time(22, 0),
                cerrado=False
            )
            db.session.add(horario)
        
        # Crear horarios para Sucursal Roma (Lunes a Viernes 10:00-23:00, Sábado y Domingo 12:00-21:00)
        for dia in range(5):  # Lunes a Viernes
            horario = HorarioSucursal(
                sucursal_id=sucursal_roma.id,
                dia_semana=dia,
                hora_apertura=time(10, 0),
                hora_cierre=time(23, 0),
                cerrado=False
            )
            db.session.add(horario)
        
        for dia in range(5, 7):  # Sábado y Domingo
            horario = HorarioSucursal(
                sucursal_id=sucursal_roma.id,
                dia_semana=dia,
                hora_apertura=time(12, 0),
                hora_cierre=time(21, 0),
                cerrado=False
            )
            db.session.add(horario)
        
        # Crear horarios para Sucursal Polanco (Martes a Domingo, lunes cerrado)
        # Lunes cerrado
        horario_lunes = HorarioSucursal(
            sucursal_id=sucursal_polanco.id,
            dia_semana=0,
            cerrado=True
        )
        db.session.add(horario_lunes)
        
        # Martes a Domingo 11:00-22:00
        for dia in range(1, 7):
            horario = HorarioSucursal(
                sucursal_id=sucursal_polanco.id,
                dia_semana=dia,
                hora_apertura=time(11, 0),
                hora_cierre=time(22, 0),
                cerrado=False
            )
            db.session.add(horario)
        
        # Crear productos
        pozole_blanco = MenuItem(
            nombre="Pozole Blanco",
            descripcion="Delicioso pozole tradicional con maíz cacahuazintle, carne de cerdo y pollo",
            precio=85.00,
            categoria_id=categoria_pozoles.id,
            imagen="/static/uploads/POZOLE_BLANCO.png"
        )
        
        pozole_rojo = MenuItem(
            nombre="Pozole Rojo",
            descripcion="Pozole con chile guajillo y ancho, carne de cerdo y verduras frescas",
            precio=90.00,
            categoria_id=categoria_pozoles.id
        )
        
        agua_horchata = MenuItem(
            nombre="Agua de Horchata",
            descripcion="Refrescante agua de horchata casera",
            precio=25.00,
            categoria_id=categoria_bebidas.id
        )
        
        db.session.add_all([pozole_blanco, pozole_rojo, agua_horchata])
        db.session.flush()
        
        # Asignar productos a sucursales
        from models import MenuItemSucursal
        
        # Pozole blanco disponible en todas las sucursales
        for sucursal in [sucursal_centro, sucursal_roma, sucursal_polanco]:
            rel = MenuItemSucursal(
                menuitem_id=pozole_blanco.id,
                sucursal_id=sucursal.id,
                disponible=True
            )
            db.session.add(rel)
        
        # Pozole rojo solo en Centro y Roma
        for sucursal in [sucursal_centro, sucursal_roma]:
            rel = MenuItemSucursal(
                menuitem_id=pozole_rojo.id,
                sucursal_id=sucursal.id,
                disponible=True
            )
            db.session.add(rel)
        
        # Agua de horchata en todas las sucursales
        for sucursal in [sucursal_centro, sucursal_roma, sucursal_polanco]:
            rel = MenuItemSucursal(
                menuitem_id=agua_horchata.id,
                sucursal_id=sucursal.id,
                disponible=True
            )
            db.session.add(rel)
        
        # Crear administrador
        admin = Administrador(
            usuario="summeratmars",
            password="Amoethan1",
            nombre="Administrador Principal"
        )
        db.session.add(admin)
        
        # Guardar todos los cambios
        db.session.commit()
        
        print("✅ Datos de ejemplo creados:")
        print("   - 3 categorías")
        print("   - 3 sucursales con horarios configurados")
        print("   - 3 productos asignados a sucursales")
        print("   - 1 administrador")
        print("   - Horarios completos para cada sucursal")
        
        print("\n📋 Horarios configurados:")
        print("   🏪 Centro: Lunes a Domingo 9:00-22:00")
        print("   🏪 Roma Norte: Lun-Vie 10:00-23:00, Sáb-Dom 12:00-21:00")
        print("   🏪 Polanco: Martes a Domingo 11:00-22:00 (Lunes cerrado)")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creando datos de ejemplo: {e}")
        raise

if __name__ == "__main__":
    print("🔄 Recreando base de datos con sistema de horarios...")
    if recrear_database():
        print("\n🎉 ¡Base de datos lista con sistema de horarios!")
        print("\n📝 Funcionalidades añadidas:")
        print("   ⏰ Gestión de horarios por sucursal")
        print("   🗓️ Configuración día por día")
        print("   🕒 Detección automática de estado (abierto/cerrado)")
        print("   🌍 Zona horaria México City")
        print("   📱 Interfaz móvil para gestión de horarios")
        print("   🔄 Copiar horarios entre sucursales")
        print("\n🎯 Acceso admin: summeratmars / Amoethan1")
    else:
        print("\n💥 Error recreando la base de datos")
