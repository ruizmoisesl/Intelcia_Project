class TestPermissions:
    # 401 sin token · employee POST 403 · employee DELETE 403 ·
    # employee list → solo las suyas · employee detail de otro → 403 · supervisor ve todo
    pass

class TestCreate:
    # 201 con events [CREATED] · con assignee → [CREATED, ASSIGNED] ·
    # título corto 422 · assignee inexistente 404 · assignee inactivo 400 ·
    # audit TASK_CREATED
    pass

class TestUpdate:
    # empleado PENDING→IN_PROGRESS ok (event STATUS_CHANGED) ·
    # empleado IN_PROGRESS→PENDING 403 (no retroceder) ·
    # empleado editando título 403 ·
    # supervisor reasigna (event ASSIGNED "asignada a …") ·
    # supervisor reabre DONE → completed_at None ·
    # completar → completed_at set + is_overdue pasa a false ·
    # due_date: null explícito → "sin fecha límite" (DUE_CHANGED)
    pass

class TestList:
    # envelope {total, today, items} · filtro status · paginación limit/offset ·
    # is_overdue true/false según dates.today()
    pass

class TestDelete:
    # supervisor 204 y desaparece · task_events en cascada (count 0) ·
    # audit TASK_DELETED
    pass