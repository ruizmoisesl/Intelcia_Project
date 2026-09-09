// update.ts — editar / cambiar estado (con los guards de rol del backend)
// … leer task_id, next; payload con los campos presentes:
//   title/description (si vienen), priority (si es válida), due_date (regex),
//   status (si es válida), assignee_id ("" → null para desasignar, dígitos → número).
//   El backend aplica permisos: empleado solo estado de SUS tareas y solo avanzar.