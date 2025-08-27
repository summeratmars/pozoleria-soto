from extensions import db

class Sucursal(db.Model):
    __tablename__ = 'sucursal'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(20))
    activa = db.Column(db.Boolean, default=True)  # Nueva columna para estado de la sucursal
    menuitems = db.relationship('MenuItemSucursal', back_populates='sucursal')
    horarios = db.relationship('HorarioSucursal', backref='sucursal', lazy=True, cascade='all, delete-orphan')

class MenuItem(db.Model):
    __tablename__ = 'menu_item'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    descripcion = db.Column(db.String(200))
    precio = db.Column(db.Float)
    imagen = db.Column(db.String(200))
    sucursales = db.relationship('MenuItemSucursal', back_populates='menuitem')
    extras = db.relationship('Extra', backref='menuitem', lazy=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'))
    categoria = db.relationship('Categoria', backref='productos')
    opciones = db.relationship('OpcionPersonalizada', backref='menuitem', lazy=True)

class MenuItemSucursal(db.Model):
    __tablename__ = 'menuitem_sucursal'
    menuitem_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), primary_key=True)
    disponible = db.Column(db.Boolean, default=True)
    menuitem = db.relationship('MenuItem', back_populates='sucursales')
    sucursal = db.relationship('Sucursal', back_populates='menuitems')

class Pedido(db.Model):
    __tablename__ = 'pedido'
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(100))
    fecha = db.Column(db.DateTime)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    productos = db.Column(db.String(500))  # Puedes guardar como texto o usar una tabla intermedia
    total = db.Column(db.Float)

class Extra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    precio = db.Column(db.Float)
    menuitem_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))

class Administrador(db.Model):
    __tablename__ = 'administrador'
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    nombre = db.Column(db.String(100))
    rol = db.Column(db.String(20), default='empleado')  # 'super' o 'empleado'

# Tabla pivote para relación muchos-a-muchos entre administradores y sucursales
class AdministradorSucursal(db.Model):
    __tablename__ = 'administrador_sucursal'
    administrador_id = db.Column(db.Integer, db.ForeignKey('administrador.id'), primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), primary_key=True)

# Relaciones dinámicas (se definen después de las clases base)
Administrador.sucursales = db.relationship('Sucursal', secondary='administrador_sucursal', backref=db.backref('administradores', lazy='dynamic'))

class PedidoCliente(db.Model):
    __tablename__ = 'pedidocliente'
    id = db.Column(db.Integer, primary_key=True)
    numero_pedido = db.Column(db.String(10), unique=True, nullable=False)  # Número único de pedido
    nombre = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.String(500))  # Dirección completa concatenada
    calle = db.Column(db.String(100))
    numero = db.Column(db.String(20))
    colonia = db.Column(db.String(100))
    entre_calles = db.Column(db.String(200))
    referencia = db.Column(db.String(300))
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'))
    sucursal = db.relationship('Sucursal', backref='pedidos_clientes')
    productos = db.Column(db.String(500))  # Lista de productos y extras en texto
    total = db.Column(db.Float)
    fecha = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default='Pendiente')  # Pendiente, En camino, Entregado
    # Campos de pago
    forma_pago = db.Column(db.String(20), default='efectivo')  # efectivo, transferencia
    cambio_para = db.Column(db.Float, nullable=True)  # Para pago en efectivo
    comprobante_transferencia = db.Column(db.Boolean, default=False)  # Si confirmó enviar comprobante

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)

class OpcionPersonalizada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    menuitem_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    titulo = db.Column(db.String(100))
    obligatorio = db.Column(db.Boolean, default=False)
    tipo = db.Column(db.String(20))  # 'radio' o 'checkbox'

class ValorOpcion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    opcion_id = db.Column(db.Integer, db.ForeignKey('opcion_personalizada.id'))
    texto = db.Column(db.String(100))
    precio = db.Column(db.Float, default=0)

MenuItem.opciones = db.relationship('OpcionPersonalizada', backref='menuitem', lazy=True)
OpcionPersonalizada.valores = db.relationship('ValorOpcion', backref='opcion', lazy=True)

class HorarioSucursal(db.Model):
    __tablename__ = 'horario_sucursal'
    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursal.id'), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Lunes, 1=Martes, ..., 6=Domingo
    hora_apertura = db.Column(db.Time, nullable=True)  # NULL si está cerrado ese día
    hora_cierre = db.Column(db.Time, nullable=True)    # NULL si está cerrado ese día
    cerrado = db.Column(db.Boolean, default=False)     # True si está cerrado ese día
    
    def __repr__(self):
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        if self.cerrado:
            return f'{dias[self.dia_semana]}: Cerrado'
        else:
            return f'{dias[self.dia_semana]}: {self.hora_apertura.strftime("%H:%M")} - {self.hora_cierre.strftime("%H:%M")}'
    
    @staticmethod
    def obtener_dias_semana():
        return [
            (0, 'Lunes'),
            (1, 'Martes'),
            (2, 'Miércoles'),
            (3, 'Jueves'),
            (4, 'Viernes'),
            (5, 'Sábado'),
            (6, 'Domingo')
        ]
    
    def esta_abierto_ahora(self):
        """Verifica si la sucursal está abierta en este momento (horario México City)"""
        from datetime import datetime, time
        import pytz
        
        # Obtener hora actual en México City
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora_mexico = datetime.now(tz_mexico)
        dia_actual = ahora_mexico.weekday()  # 0=Lunes, 6=Domingo
        hora_actual = ahora_mexico.time()
        
        # Si la sucursal está marcada como cerrada este día
        if self.cerrado or self.dia_semana != dia_actual:
            return False
            
        # Si no hay horarios definidos
        if not self.hora_apertura or not self.hora_cierre:
            return False
            
        # Verificar si está dentro del horario
        return self.hora_apertura <= hora_actual <= self.hora_cierre
    
    @classmethod
    def sucursal_abierta_ahora(cls, sucursal_id):
        """Verifica si una sucursal específica está abierta ahora"""
        from datetime import datetime
        import pytz
        
        # Obtener hora actual en México City
        tz_mexico = pytz.timezone('America/Mexico_City')
        ahora_mexico = datetime.now(tz_mexico)
        dia_actual = ahora_mexico.weekday()  # 0=Lunes, 6=Domingo
        hora_actual = ahora_mexico.time()
        
        # Buscar el horario para el día actual
        horario_hoy = cls.query.filter_by(
            sucursal_id=sucursal_id,
            dia_semana=dia_actual
        ).first()
        
        if not horario_hoy:
            return False
            
        if horario_hoy.cerrado:
            return False
            
        if not horario_hoy.hora_apertura or not horario_hoy.hora_cierre:
            return False
            
        return horario_hoy.hora_apertura <= hora_actual <= horario_hoy.hora_cierre
