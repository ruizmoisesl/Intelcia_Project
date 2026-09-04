"""Integraciones externas (Google Workspace, Jira, etc.).

Cada integración vive en su propio módulo y se consume desde los servicios;
nunca al revés: la lógica de negocio no conoce HTTP del exterior salvo vía
esta capa. Futuras: drive.py, sheets.py, jira.py…
"""