// JS común para panel admin (desktop y mobile)
// Maneja toasts, DataTables genéricas, confirmaciones y utilidades compartidas.
(function(){
  // Toast genérico
  window.showToastGlobal = function(message, type='success'){    
    const containerClass = 'toast-container position-fixed top-0 end-0 p-3';
    let container = document.querySelector('.toast-container');
    if(!container){
      container = document.createElement('div');
      container.className = containerClass;
      document.body.appendChild(container);
    }
    const id = 'toast-'+Date.now();
    const icon = type==='success'?'check':'exclamation-triangle';
    container.insertAdjacentHTML('beforeend', `\n      <div id="${id}" class="toast align-items-center text-white bg-${type} border-0" role="alert">\n        <div class="d-flex">\n          <div class="toast-body"><i class="fas fa-${icon} me-2"></i>${message}</div>\n          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>\n        </div>\n      </div>`);
    const toastEl = document.getElementById(id);
    if(window.bootstrap && bootstrap.Toast){ new bootstrap.Toast(toastEl).show(); }
    toastEl.addEventListener('hidden.bs.toast', ()=> toastEl.remove());
  };

  // Confirm genérico
  window.confirmDeleteGlobal = function(message='¿Estás seguro?'){ return confirm(message); };

  // Auto DataTables para tablas con clase .data-table-auto
  document.addEventListener('DOMContentLoaded', function(){
     if(typeof $ !== 'undefined' && $.fn.DataTable){
        $('.data-table-auto').DataTable({
           language:{ url:'//cdn.datatables.net/plug-ins/1.13.4/i18n/es-ES.json' },
           pageLength:25,
           responsive:true
        });
     }
  });
})();
