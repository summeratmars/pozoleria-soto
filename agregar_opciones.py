#!/usr/bin/env python3
"""
Script para agregar opciones predefinidas a los productos de pozole
"""

from flask import Flask
from extensions import db
from models import MenuItem, OpcionPersonalizada, ValorOpcion
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pozoleria_new.db'
db.init_app(app)

def agregar_opciones_pozole():
    """Agrega opciones típicas a los productos de pozole"""
    
    with app.app_context():
        # Obtener todos los productos que contengan "pozole" en su nombre
        productos_pozole = MenuItem.query.filter(MenuItem.nombre.ilike('%pozole%')).all()
        
        print(f"Encontrados {len(productos_pozole)} productos de pozole:")
        for producto in productos_pozole:
            print(f"- {producto.nombre} (ID: {producto.id})")
        
        for producto in productos_pozole:
            print(f"\nAgregando opciones para: {producto.nombre}")
            
            # Limpiar opciones existentes
            OpcionPersonalizada.query.filter_by(menuitem_id=producto.id).delete()
            
            # 1. Opción de Tamaño (Obligatoria)
            opcion_tamaño = OpcionPersonalizada(
                menuitem_id=producto.id,
                titulo="Tamaño",
                tipo="radio",
                obligatorio=True
            )
            db.session.add(opcion_tamaño)
            db.session.flush()  # Para obtener el ID
            
            # Valores para tamaño
            valores_tamaño = [
                {"texto": "Plato", "precio": 0.0},
                {"texto": "Litro", "precio": 20.0},
                {"texto": "Medio Litro", "precio": 10.0}
            ]
            
            for valor in valores_tamaño:
                valor_opcion = ValorOpcion(
                    opcion_id=opcion_tamaño.id,
                    texto=valor["texto"],
                    precio=valor["precio"]
                )
                db.session.add(valor_opcion)
            
            # 2. Tipo de Carne (Obligatoria)
            opcion_carne = OpcionPersonalizada(
                menuitem_id=producto.id,
                titulo="¿Cómo te gusta tu pozole?",
                tipo="radio",
                obligatorio=True
            )
            db.session.add(opcion_carne)
            db.session.flush()
            
            # Valores para carne
            valores_carne = [
                {"texto": "Maciza", "precio": 0.0},
                {"texto": "Mixto (Maciza y Buche)", "precio": 5.0},
                {"texto": "Con Patita", "precio": 8.0},
                {"texto": "Solo Verdura", "precio": -10.0}
            ]
            
            for valor in valores_carne:
                valor_opcion = ValorOpcion(
                    opcion_id=opcion_carne.id,
                    texto=valor["texto"],
                    precio=valor["precio"]
                )
                db.session.add(valor_opcion)
            
            # 3. Picante (Opcional)
            opcion_picante = OpcionPersonalizada(
                menuitem_id=producto.id,
                titulo="Nivel de Picante",
                tipo="radio",
                obligatorio=False
            )
            db.session.add(opcion_picante)
            db.session.flush()
            
            # Valores para picante
            valores_picante = [
                {"texto": "Sin Picante", "precio": 0.0},
                {"texto": "Poco Picante", "precio": 0.0},
                {"texto": "Picante Normal", "precio": 0.0},
                {"texto": "Muy Picante", "precio": 0.0}
            ]
            
            for valor in valores_picante:
                valor_opcion = ValorOpcion(
                    opcion_id=opcion_picante.id,
                    texto=valor["texto"],
                    precio=valor["precio"]
                )
                db.session.add(valor_opcion)
            
            # 4. Extras (Checkbox, Opcional)
            opcion_extras = OpcionPersonalizada(
                menuitem_id=producto.id,
                titulo="Extras",
                tipo="checkbox",
                obligatorio=False
            )
            db.session.add(opcion_extras)
            db.session.flush()
            
            # Valores para extras
            valores_extras = [
                {"texto": "Aguacate Extra", "precio": 15.0},
                {"texto": "Chicharrón Prensado", "precio": 20.0},
                {"texto": "Queso Fresco", "precio": 12.0},
                {"texto": "Limón Extra", "precio": 3.0},
                {"texto": "Orégano", "precio": 0.0},
                {"texto": "Tostadas Extra", "precio": 8.0}
            ]
            
            for valor in valores_extras:
                valor_opcion = ValorOpcion(
                    opcion_id=opcion_extras.id,
                    texto=valor["texto"],
                    precio=valor["precio"]
                )
                db.session.add(valor_opcion)
            
            print(f"✅ Opciones agregadas para {producto.nombre}")
        
        # Confirmar cambios
        db.session.commit()
        print(f"\n🎉 ¡Opciones agregadas exitosamente a {len(productos_pozole)} productos!")
        
        # Mostrar resumen
        print("\n📋 Resumen de opciones agregadas:")
        print("- Tamaño (Obligatorio): Plato, Litro, Medio Litro")
        print("- Tipo de Carne (Obligatorio): Maciza, Mixto, Con Patita, Solo Verdura")
        print("- Nivel de Picante (Opcional): Sin/Poco/Normal/Muy Picante")
        print("- Extras (Opcional): Aguacate, Chicharrón, Queso, Limón, Orégano, Tostadas")

if __name__ == "__main__":
    agregar_opciones_pozole()
