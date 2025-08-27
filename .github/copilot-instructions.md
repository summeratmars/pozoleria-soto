# Pozolería 2.0 - AI Coding Agent Instructions

## Architecture Overview

This is a multi-location restaurant ordering system built with Flask. The core architecture follows a **location-aware product catalog** pattern where:
- Products (`MenuItem`) can be available at multiple locations (`Sucursal`) through the `MenuItemSucursal` junction table
- Each product has customizable options (`OpcionPersonalizada` with `ValorOpcion` for pricing)
- Orders are location-specific and stored as `PedidoCliente`

### Key Components
- `app.py`: Main Flask app with public routes (catalog, cart, checkout)
- `admin.py`: Blueprint for admin panel with CRUD operations  
- `models.py`: SQLAlchemy models with complex relationships
- `extensions.py`: Database initialization (Flask-SQLAlchemy)
- `telegram_bot.py`: Order notification integration (not fully implemented)

## Critical Data Flow Patterns

### Product Data Transformation
In `app.py`, the `catalogo()` route transforms database models into frontend-ready data:
```python
# Always use p.precio from database, never hardcode prices
productos_data.append({
    "id": p.id,
    "precio": p.precio,  # CRITICAL: Use real DB price
    "opciones": opciones,  # Transformed from OpcionPersonalizada/ValorOpcion
    "sucursales": sucursales_ids  # Available location IDs
})
```

### Location-Aware Product Filtering
Products are filtered by location in JavaScript using `data-sucursales` attributes. The catalog enforces location selection through a modal on first visit only - once selected, the location is stored in localStorage and the modal won't appear again.

### Checkout Process
The checkout automatically uses the selected sucursal from localStorage - no need for user to select again. Address collection includes detailed fields: calle, numero, colonia, entre_calles, referencia (all required).

### Admin Product Management
When editing products in admin panel:
- Use `db.session.flush()` before accessing auto-generated IDs
- Delete and recreate `OpcionPersonalizada` and `ValorOpcion` objects (no update in place)
- Handle file uploads to `static/uploads/` with `secure_filename()`

## Development Workflows

### Database Changes
- No migrations setup - modify `models.py` directly
- Delete `instance/pozoleria.db` to recreate from scratch
- Database auto-creates on first run via SQLAlchemy

### Running the Application
```bash
python app.py  # Starts Flask dev server on http://127.0.0.1:5000
```

### Admin Access
- URL: `/admin/login`
- Hardcoded credentials in `admin.py`: `ADMIN_USER = 'summeratmars'`, `ADMIN_PASS = 'Amoethan1'`
- Alternative: Database-stored admin users in `Administrador` table

## Project-Specific Conventions

### Template Structure
- `base.html`: Main layout with Bootstrap 5 and brand styling
- Admin templates in `templates/admin/` follow CRUD naming: `listar_*.html`, `nuevo_*.html`, `editar_*.html`
- Public templates use responsive design with mobile-first approach

### Model Relationships
- `MenuItem` ↔ `Sucursal` through `MenuItemSucursal` (availability per location)
- `MenuItem` → `OpcionPersonalizada` → `ValorOpcion` (product customization chain)
- Product options support both radio buttons and checkboxes with optional pricing

### Frontend State Management
- Shopping cart stored in localStorage per location: `carritos_por_sucursal`
- Location selection persisted in `localStorage.getItem('sucursal_id')`
- Dynamic product filtering without page reload

### File Upload Pattern
```python
if imagen_file and imagen_file.filename:
    filename = secure_filename(imagen_file.filename)
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    imagen_file.save(filepath)
    imagen_url = url_for('static', filename=f'uploads/{filename}')
```

## Common Issues to Avoid

1. **Price Synchronization**: Always use `p.precio` from database in `catalogo()` route, never hardcode prices
2. **Location Filtering**: Ensure product availability respects `MenuItemSucursal.disponible` flag
3. **Option Management**: When updating product options, delete all existing `OpcionPersonalizada` and `ValorOpcion` first
4. **Session Management**: Admin routes require `@login_required` decorator
5. **File Security**: Always use `secure_filename()` for uploads

## Integration Points

- **Telegram Bot**: Configured but not active (requires token setup in `telegram_bot.py`)
- **Static Files**: Images served from `static/uploads/` with 2MB limit
- **Database**: SQLite at `instance/pozoleria.db` (auto-created)
- **Styling**: Bootstrap 5 with custom CSS variables (`--pozoleria-orange: #e97c1a`)
