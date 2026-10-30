# kai — Análisis inicial

Agente de IA de voz para ayudar en la gestión del ordenador (Linux, Windows, macOS),
con **Gemini 3.8 Live** como modelo conversacional y una estética minimalista.

_Fecha del análisis: 2026-10-30. Fuentes: documentación oficial de Google AI for Developers._

## 1. ¿Es gratuito Gemini 3.8 Live?

**Sí.** En la página oficial de precios, `gemini-3.8-live` y `gemini-3.8-live-extended-thinking`
aparecen como _"Free of charge"_ en entrada y salida dentro del **Free Tier**.

Matices:
- En el nivel gratuito, Google **puede usar los datos** (audio, capturas) para mejorar sus productos.
  En el nivel de pago, no. Hay que avisar de ello en la app.
- Google no publica límites de uso concretos para este modelo. Se ven en AI Studio.
  La app debe gestionar con elegancia los errores de cuota (429).
- Precios de pago (por si el usuario lo activa): audio 3 $/M tokens de entrada y 12 $/M de salida;
  imagen/vídeo 1 $/M de entrada; texto 0,75 $/M de entrada y 4,50 $/M de salida.

## 2. Qué ofrece el modelo (y qué no)

| Capacidad | Estado | Uso en kai |
|---|---|---|
| Audio de entrada/salida en tiempo real (PCM 16 kHz in / 24 kHz out) | ✅ | Conversación por voz, con interrupciones (barge-in) |
| Texto de entrada/salida | ✅ | Chat escrito como alternativa |
| Imágenes / frames de vídeo (JPEG, ≤1 fps) | ✅ | **Visión de pantalla** y webcam |
| Function calling (asíncrono por defecto, `NON_BLOCKING`) | ✅ | **Núcleo del control del ordenador** |
| Google Search (grounding) | ✅ | Responder con información actual |
| Transcripción de entrada y salida | ✅ | Mostrar subtítulos e historial |
| Unos 70 idiomas | ✅ | Español nativo |
| Audio proactivo (siempre activo) | ✅ | El modelo decide cuándo hablar |
| Modelo con razonamiento (`-extended-thinking`) | ✅ | Modo "pensar" para tareas complejas |
| Ejecución de código | ❌ | La sustituimos por herramientas locales propias |
| Salida estructurada, caché, URL context | ❌ | — |

Límites de sesión que condicionan el diseño:
- Sin compresión: **15 min** solo audio y **2 min** con audio+vídeo. Cada conexión dura unos 10 min.
- Con **compresión de contexto** (`contextWindowCompression`) y **reanudación de sesión**
  (`sessionResumption`, handles válidos 2 h), la sesión puede durar indefinidamente.
  Hay que escuchar el mensaje `GoAway` para reconectar sin cortes.

## 3. Funcionalidades propuestas para kai

### Visión
- **Ver la pantalla bajo demanda**: el modelo llama a `capture_screen()` y recibe un JPEG.
  Se ahorran cuotas y se respeta la privacidad.
- **Modo "compartir pantalla"** opcional: frames a ≤1 fps mientras esté activo, con un indicador visible.
- Webcam opcional (más adelante).

### Control del ordenador (mediante function calling)
Por niveles de riesgo:

1. **Solo lectura**: información del sistema (CPU, RAM, disco, batería, red), listar procesos,
   buscar y listar archivos, leer el portapapeles, ventanas abiertas.
2. **Acciones seguras**: abrir aplicaciones, archivos y URLs; volumen y brillo; notificaciones;
   escribir en el portapapeles; enfocar y minimizar ventanas.
3. **Acciones sensibles** (siempre **con confirmación** del usuario): mover, renombrar o borrar archivos,
   cerrar procesos, ejecutar comandos de shell, instalar paquetes.
4. **Control de escritorio** (ratón y teclado): clic, escritura y atajos guiados por la visión.
   Es potente pero frágil. Irá desactivado por defecto, con confirmación y una tecla de parada de emergencia.

### Experiencia de usuario
- Ventana pequeña y minimalista: un orbe o forma que reacciona a la voz, subtítulos opcionales
  y un campo de texto.
- Atajo global para hablar (push-to-talk) o modo de escucha continua.
- Icono en la bandeja del sistema.
- **Configuración de la API key** en el primer arranque, con un asistente que explica cómo
  conseguirla en [Google AI Studio](https://aistudio.google.com/apikey).
  La clave se guarda en el **almacén seguro del sistema** (Keychain, Credential Manager o Secret Service)
  y nunca en texto plano.
- Registro visible de las acciones que ha ejecutado el agente.

## 4. Stack recomendado

**Python 3.12 + PySide6 (Qt)**, empaquetado con PyInstaller para los 3 sistemas.

| Necesidad | Librería |
|---|---|
| Gemini Live | `google-genai` (SDK oficial, soporta Live API) |
| Audio | `sounddevice` |
| Capturas de pantalla | `mss` + `Pillow` |
| Info del sistema / procesos | `psutil` |
| Ratón y teclado | `pynput` / `pyautogui` |
| API key segura | `keyring` |
| UI minimalista | `PySide6` (QML para animaciones suaves) |

Motivos: el SDK oficial de la Live API es de primera clase en Python, las librerías de control del sistema
son maduras y multiplataforma, y Qt permite una UI cuidada y nativa.

La alternativa es Tauri o Electron con TypeScript: la UI web es más vistosa, pero el control del sistema
es más complejo.

Avisos de plataforma: en macOS hacen falta permisos de _Accesibilidad_, _Grabación de pantalla_
y _Micrófono_. En Linux con Wayland, el control de ratón y teclado y las capturas son limitados
(funciona mejor en X11 o con portales).

## 5. Hoja de ruta

1. **MVP**: ventana mínima, gestión de la API key, conversación de voz y texto con Gemini 3.8 Live
   y reconexión robusta.
2. Herramientas de nivel 1 y 2, más la captura de pantalla bajo demanda.
3. Acciones sensibles con confirmación y registro de acciones.
4. Control de ratón y teclado, y modo compartir pantalla.
5. Empaquetado e instaladores para Linux, Windows y macOS.
