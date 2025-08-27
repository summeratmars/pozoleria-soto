import sys
sys.path.append('.')
from app import app
from models import HorarioSucursal, Sucursal
from datetime import datetime
import pytz

def main():
    with app.app_context():
        # Hora actual
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora_mexico = datetime.now(tz_mexico)
        print(f"=== VERIFICACIÓN DE HORARIOS ===")
        print(f"Fecha y hora actual en México: {ahora_mexico}")
        print(f"Día de la semana: {ahora_mexico.weekday()} (0=Lunes, 6=Domingo)")
        print(f"Hora actual: {ahora_mexico.time()}")
        print()
        
        # Verificar cada sucursal
        sucursales = Sucursal.query.all()
        for sucursal in sucursales:
            print(f"🏪 SUCURSAL: {sucursal.nombre}")
            print(f"   Activa: {sucursal.activa}")
            
            # Verificar si está abierta ahora
            abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(sucursal.id)
            print(f"   Estado actual: {'🟢 ABIERTA' if abierta_ahora else '🔴 CERRADA'}")
            
            # Mostrar horario de hoy
            horario_hoy = HorarioSucursal.query.filter_by(
                sucursal_id=sucursal.id,
                dia_semana=ahora_mexico.weekday()
            ).first()
            
            if horario_hoy:
                if horario_hoy.cerrado:
                    print(f"   Horario hoy: CERRADO")
                else:
                    print(f"   Horario hoy: {horario_hoy.hora_apertura} - {horario_hoy.hora_cierre}")
            else:
                print(f"   Sin horario definido para hoy")
            
            print("-" * 50)

if __name__ == "__main__":
    main()
