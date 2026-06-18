# Tutor IA Anatomía I con VARK — README Técnico

## 1. Descripción general

Sistema web de tutorías para Anatomía I que personaliza rutas de aprendizaje según:
- perfil VARK del estudiante,
- tema seleccionado del libro,
- tiempo disponible,
- temas difíciles,
- proximidad del examen.

El sistema integra LLM para generar rutas, mapas mentales, preguntas, simulacros y recomendaciones. Además, integra generación visual con ComfyUI local usando GPU RTX 3080 Ti para producir láminas anatómicas personalizadas.

## 2. Arquitectura general

Flujo principal:

```text
Usuario
↓
Django Web App
↓
Perfil VARK + Datos académicos + Materiales
↓
LLM textual Gemini / proveedor configurado
↓
Ruta personalizada JSON
↓
Prompts dinámicos por categoría anatómica
↓
Servidor local FastAPI
↓
ComfyUI + RealVisXL en RTX 3080 Ti
↓
Imagen anatómica generada
↓
Django descarga imagen y la guarda como Base64 en plan_json
↓
Interfaz muestra ruta, mapa mental, lámina, modo práctica e historial IA
```

## 3. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend | HTML, CSS, Bootstrap, Django Templates |
| Backend | Python, Django |
| Base de datos | PostgreSQL en Docker / Render |
| LLM textual | Gemini API |
| IA visual local | ComfyUI + RealVisXL |
| Servidor IA local | FastAPI |
| GPU local | NVIDIA RTX 3080 Ti |
| Contenedores | Docker, Docker Compose |
| Túnel para Render | Cloudflare Tunnel |
| Persistencia visual | Base64 dentro de `plan_json` |

## 4. Modos de ejecución

### Modo local completo sin Render

Este modo se usa para defensa o pruebas locales.

```text
Django Docker local
↓
http://host.docker.internal:8090
↓
FastAPI local
↓
ComfyUI local
↓
GPU RTX 3080 Ti
```

Variables importantes en `.env` local:

```env
IMAGE_PROVIDER=local
GENERAR_IMAGENES_RUTA=true
MAX_IMAGENES_RUTA=2
LOCAL_IMAGE_MAX_WAIT=240
LOCAL_IMAGE_POLL_INTERVAL=5
LOCAL_IMAGE_API_URL=http://host.docker.internal:8090/generate-anatomy
LOCAL_IMAGE_JOB_BASE_URL=http://host.docker.internal:8090
```

### Modo Render + PC local

Este modo se usa cuando la app está desplegada en Render y la generación visual corre en la PC local.

```text
Render
↓
Cloudflare Tunnel
↓
FastAPI local
↓
ComfyUI local
↓
GPU RTX 3080 Ti
```

Variables en Render:

```env
IMAGE_PROVIDER=local
GENERAR_IMAGENES_RUTA=true
MAX_IMAGENES_RUTA=10
LOCAL_IMAGE_MAX_WAIT=240
LOCAL_IMAGE_POLL_INTERVAL=5

```

Cada vez que se reinicia Cloudflare Quick Tunnel, la URL cambia y se deben actualizar esas dos variables en Render.

## 5. Levantar entorno local

### 5.1. Iniciar ComfyUI

```bash
cd "C:\Users\denil\Desktop\IA local\ComfyUI"
venv\Scripts\activate
python main.py
```

Debe abrir:

```text
http://127.0.0.1:8188
```

### 5.2. Iniciar servidor local de imágenes

```bash
cd "C:\Users\denil\Desktop\IA local"
venv_api\Scripts\activate
python local_image_server.py
```

Debe abrir:

```text
http://127.0.0.1:8090
```

Prueba:

```text
http://127.0.0.1:8090/
```

### 5.3. Levantar Django con Docker

```bash
docker compose down
docker compose up --build -d
docker compose exec web python manage.py migrate
```

Abrir:

```text
http://localhost:8089/rutas/
```

## 6. Comandos útiles

Verificar Docker:

```bash
docker compose ps
docker compose logs web --tail=80
docker compose exec web python manage.py check
```

Verificar conexión del contenedor con la IA local:

```bash
docker compose exec web python -c "import requests; print(requests.get('http://host.docker.internal:8090/').text)"
```

Cargar dataset de Anatomía I:

```bash
docker compose exec web python manage.py cargar_dataset_anatomia
```

Crear superusuario local:

```bash
docker compose exec web python manage.py createsuperuser
```

## 7. Integración LLM / IA

El sistema usa LLM textual para:
- generar ruta personalizada,
- estructurar mapa mental,
- crear preguntas de práctica,
- generar simulacros,
- adaptar recursos al perfil VARK.

La IA visual usa prompts dinámicos por categoría anatómica:
- óseo,
- articular,
- muscular,
- visceral,
- nervioso,
- vascular,
- linfático,
- perineal.

Esto evita prompts genéricos y reduce errores como generar estructuras no relacionadas con el tema.

## 8. Persistencia de imágenes

Las imágenes generadas por ComfyUI se descargan desde el servidor local y se convierten a:

```text
data:image/png;base64,...
```

Luego se guardan dentro de `plan_json`.  
Esto permite que la imagen siga visible aunque se apague la PC o cambie la URL del túnel.

## 9. Errores comunes

### Error: `password authentication failed for user postgres`

Causa: variables de PostgreSQL no coinciden.

Solución en `.env`:

```env
POSTGRES_DB=tutor_ia_db
POSTGRES_USER=tutor_user
POSTGRES_PASSWORD=tutor_password
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

Si persiste:

```bash
docker compose down -v
docker compose up --build -d
docker compose exec web python manage.py migrate
```

### Error: selector de temas vacío

Causa: base local nueva sin dataset.

Solución:

```bash
docker compose exec web python manage.py cargar_dataset_anatomia
```

### Error: imagen pendiente

Causas posibles:
- ComfyUI apagado,
- FastAPI local apagado,
- URL de Cloudflare vencida,
- timeout de generación,
- `MAX_IMAGENES_RUTA` muy bajo.

### Error: Google Login `invalid_client`

Causa: OAuth local no configurado.

Solución rápida para pruebas:
- crear superusuario,
- entrar por `/admin/`,
- usar login local si está disponible.

## 10. Seguridad

No subir `.env` al repositorio.  
Usar `.env.example` sin claves reales.  
Las claves expuestas deben rotarse después de la demo.

## 11. Repositorio

Repositorio del proyecto:

```text
https://github.com/denilsaa/IA-VARK
```

## 12. Comando de ejecución resumido para defensa

```bash
# 1. ComfyUI
cd "C:\Users\denil\Desktop\IA local\ComfyUI"
venv\Scripts\activate
python main.py

# 2. API local
cd "C:\Users\denil\Desktop\IA local"
venv_api\Scripts\activate
python local_image_server.py

# 3. Django Docker
cd "C:\Users\denil\Desktop\tutor_ia_anatomia_vark"
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py cargar_dataset_anatomia
```
