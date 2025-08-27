from app import app
from models import HorarioSucursal

with app.app_context():
    for sucursal_id in [1, 2]:
        abierta = HorarioSucursal.sucursal_abierta_ahora(sucursal_id)
        estado = 'Abierta' if abierta else 'Cerrada'
        print(f'Sucursal {sucursal_id}: {estado}')
