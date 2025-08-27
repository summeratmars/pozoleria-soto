#!/usr/bin/env python
from datetime import datetime
import pytz
from models import HorarioSucursal, Sucursal
from extensions import db
from app import app

def verificar_horarios():
    with app.app_context():
        # Verificar hora actual en México
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora_mexico = datetime.now(tz_mexico)
        print(f'Hora actual en México: {ahora_mexico}')
        print(f'Día de la semana: {ahora_mexico.weekday()}')  # 0=Lunes, 6=Domingo
        print(f'Hora actual: {ahora_mexico.time()}')
        print('---')
        
        # Verificar sucursales
        sucursales = Sucursal.query.all()
        for s in sucursales:
            abierta = HorarioSucursal.sucursal_abierta_ahora(s.id)
            print(f'{s.nombre}: {"Abierta" if abierta else "Cerrada"}')
            
            # Mostrar horarios de hoy
            horario_hoy = HorarioSucursal.query.filter_by(
                sucursal_id=s.id,
                dia_semana=ahora_mexico.weekday()
            ).first()
            
            if horario_hoy:
                if horario_hoy.cerrado:
                    print(f'  Horario hoy: Cerrado')
                else:
                    print(f'  Horario hoy: {horario_hoy.hora_apertura} - {horario_hoy.hora_cierre}')
            else:
                print(f'  Sin horario definido para hoy')
            print()

if __name__ == '__main__':
    verificar_horarios()
